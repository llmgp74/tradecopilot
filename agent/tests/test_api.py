"""Contract tests for the REST endpoints."""

import json
import sqlite3
import stat
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langgraph.types import Interrupt
from tradecopilot_agent import Settings
from tradecopilot_agent.models import (
    Account,
    AppSettings,
    DayPnl,
    Portfolio,
)
from tradecopilot_agent.server import create_app


class StubGraph:
    """A graph double returning a fixed snapshot and one text chunk."""

    def __init__(self, snapshot: SimpleNamespace | None = None) -> None:
        self.snapshot = snapshot or SimpleNamespace(
            values={"messages": []}, interrupts=()
        )

    async def aget_state(self, config: Any) -> SimpleNamespace:
        """Return the fixed snapshot."""
        return self.snapshot

    async def astream(
        self, graph_input: Any, config: Any, **kwargs: Any
    ) -> AsyncIterator[tuple[str, Any]]:
        """Stream one text chunk."""
        yield (
            "messages",
            (AIMessageChunk(content="ok", id="a1"), {"langgraph_step": 1}),
        )


def _client(
    tmp_path: Path,
    graph: StubGraph | None = None,
    portfolio_fetcher: Any = None,
) -> TestClient:
    settings = Settings(db_path=tmp_path / "data.db")
    factory = (lambda _app, _reasoning: graph) if graph is not None else None
    return TestClient(create_app(settings, factory, portfolio_fetcher))


def _chat(client: TestClient, text: str) -> None:
    response = client.post(
        "/api/chat",
        json={
            "thread_id": "t1",
            "messages": [
                {"id": "u1", "role": "user", "parts": [{"type": "text", "text": text}]}
            ],
        },
    )
    assert response.status_code == 200


def test_profile_defaults_and_partial_update(tmp_path: Path) -> None:
    """The profile is seeded and PATCH merges only the given fields."""
    with _client(tmp_path) as client:
        initial = client.get("/api/profile").json()
        assert initial["risk_band"] == "moderate"
        assert initial["execution"] == {
            "autonomous": False,
            "max_order_notional": 1000.0,
        }

        updated = client.patch("/api/profile", json={"position_cap_pct": 8.0})
        assert updated.status_code == 200
        assert updated.json()["position_cap_pct"] == 8.0
        assert updated.json()["risk_band"] == "moderate"

        assert client.get("/api/profile").json()["position_cap_pct"] == 8.0


def test_profile_rejects_out_of_range(tmp_path: Path) -> None:
    """A cap outside 0 to 100 is a validation error."""
    with _client(tmp_path) as client:
        response = client.patch("/api/profile", json={"position_cap_pct": 101})
    assert response.status_code == 422


def test_chat_creates_a_listed_thread(tmp_path: Path) -> None:
    """A chat request indexes the thread and the detail returns its messages."""
    snapshot = SimpleNamespace(
        values={
            "messages": [
                HumanMessage(content="hi", id="u1"),
                AIMessage(content="hello", id="a1"),
            ]
        },
        interrupts=(),
    )
    with _client(tmp_path, StubGraph(snapshot)) as client:
        _chat(client, "hi there")

        listing = client.get("/api/threads").json()
        assert listing["total"] == 1
        assert listing["items"][0]["thread_id"] == "t1"
        assert listing["items"][0]["title"] == "hi there"

        detail = client.get("/api/threads/t1").json()
        assert [message["role"] for message in detail["messages"]] == [
            "user",
            "assistant",
        ]
        assert detail["messages"][1]["parts"] == [{"type": "text", "text": "hello"}]


def test_thread_detail_restores_a_pending_approval(tmp_path: Path) -> None:
    """A pending interrupt becomes an approval-requested tool part."""
    tool_call = {
        "name": "execute_ticket",
        "args": {"ticket_id": "t_1"},
        "id": "call_1",
        "type": "tool_call",
    }
    pending = {
        "id": "t_1",
        "legs": [{"ticker": "NVDA", "side": "buy", "qty": 10}],
        "thesis": "add NVDA",
        "horizon": "weeks",
        "created_at": "2026-11-05T14:00:00Z",
    }
    snapshot = SimpleNamespace(
        values={
            "messages": [
                HumanMessage(content="buy", id="u1"),
                AIMessage(content="", id="a1", tool_calls=[tool_call]),
            ],
            "pending_tickets": {
                "t_1": {
                    "ticket": pending,
                    "rationale": "add NVDA",
                    "portfolio_impact": None,
                }
            },
        },
        interrupts=(
            Interrupt(
                id="int-1",
                value={
                    "action_requests": [
                        {
                            "name": "execute_ticket",
                            "args": {"ticket_id": "t_1"},
                            "description": "Review",
                        }
                    ]
                },
            ),
        ),
    )
    with _client(tmp_path, StubGraph(snapshot)) as client:
        _chat(client, "buy")
        detail = client.get("/api/threads/t1").json()

    part = detail["messages"][1]["parts"][0]
    assert part["type"] == "tool-execute_ticket"
    assert part["state"] == "approval-requested"
    assert part["approval"]["id"] == "call_1"
    assert part["approval"]["ticket"] == pending
    assert "verification" not in part["approval"]


def test_unknown_thread_is_404(tmp_path: Path) -> None:
    """A thread without a row does not exist."""
    with _client(tmp_path) as client:
        assert client.get("/api/threads/nope").status_code == 404


def test_journal_filters(tmp_path: Path) -> None:
    """Journal pages filter by status and ticker."""
    with _client(tmp_path) as client:
        empty = client.get("/api/journal").json()
        assert empty["items"] == []
        assert empty["total"] == 0

        with sqlite3.connect(tmp_path / "data.db") as connection:
            payload = {
                "decision_id": "e1",
                "created_at": "2026-11-04T14:02:11Z",
                "legs": [
                    {
                        "ticker": "NVDA",
                        "side": "buy",
                        "qty": 10.0,
                        "notional": 2000.0,
                        "fill_price": None,
                        "fill_at": None,
                        "status": "rejected",
                    }
                ],
                "thesis": "thesis",
                "horizon": "weeks",
                "evidence_ids": ["ev1"],
                "status": "rejected",
                "user_action": "reject",
                "rejection_reason": "too large",
            }
            connection.execute(
                "INSERT INTO journal (event_id, decision_id, created_at, payload) "
                "VALUES (?, ?, ?, ?)",
                ("e1", "e1", "2026-11-04T14:02:11Z", json.dumps(payload)),
            )

        assert (
            client.get("/api/journal", params={"ticker": "nvda"}).json()["total"] == 1
        )
        assert (
            client.get("/api/journal", params={"status": "filled"}).json()["total"] == 0
        )
        entry = client.get("/api/journal").json()["items"][0]
        assert entry["status"] == "rejected"
        assert entry["outcome"] is None


def test_journal_invalid_status_is_422(tmp_path: Path) -> None:
    """An unknown status is rejected by the enum."""
    with _client(tmp_path) as client:
        response = client.get("/api/journal", params={"status": "bogus"})
    assert response.status_code == 422


def test_settings_store_secrets_encrypted(tmp_path: Path) -> None:
    """Settings return plaintext but store ciphertext in a protected key file."""
    with _client(tmp_path) as client:
        response = client.patch(
            "/api/settings",
            json={
                "alpaca_api_key": "secret-alpaca",
                "alpaca_api_secret": "secret-broker",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["alpaca_api_key"] == "secret-alpaca"
        assert body["alpaca_base_url"] == ""
        assert response.headers["Cache-Control"] == "no-store"

        with sqlite3.connect(tmp_path / "data.db") as connection:
            row = connection.execute(
                "SELECT alpaca_api_key, alpaca_api_secret FROM settings WHERE id = 1"
            ).fetchone()

    assert row is not None
    for token in row:
        assert "secret" not in token
        assert token.startswith("gAAAA")
    key_path = tmp_path / "settings.key"
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600


def test_settings_clear_does_not_fall_back_to_environment(
    tmp_path: Path, monkeypatch
) -> None:
    """Clearing a stored value leaves it empty; the environment is not read."""
    monkeypatch.setenv("ALPACA_API_KEY", "env-alpaca")
    with _client(tmp_path) as client:
        stored = client.patch(
            "/api/settings", json={"alpaca_api_key": "stored-alpaca"}
        ).json()
        assert stored["alpaca_api_key"] == "stored-alpaca"

        cleared = client.patch("/api/settings", json={"alpaca_api_key": ""}).json()
        assert cleared["alpaca_api_key"] == ""


def test_settings_change_discards_the_graph(tmp_path: Path) -> None:
    """Changing the model invalidates the cached graph."""
    graph = StubGraph()
    app = create_app(
        Settings(db_path=tmp_path / "data.db"), lambda _app, _reasoning: graph
    )
    with TestClient(app) as client:
        client.put(
            "/api/providers/openai",
            json={
                "api_key": "k",
                "npm": "@ai-sdk/openai",
                "models": [
                    {"id": "gpt-5", "name": "GPT-5"},
                    {"id": "gpt-4", "name": "GPT-4"},
                ],
            },
        )
        client.patch(
            "/api/settings",
            json={"model_provider": "openai", "model_id": "gpt-5"},
        )
        app.state.graphs[""] = graph
        client.patch("/api/settings", json={"model_id": "gpt-4"})

    assert app.state.graphs == {}


def test_exa_key_change_discards_the_graph(tmp_path: Path) -> None:
    """Changing the Exa key invalidates the search provider in the graph."""
    graph = StubGraph()
    app = create_app(
        Settings(db_path=tmp_path / "data.db"), lambda _app, _reasoning: graph
    )
    with TestClient(app) as client:
        app.state.graphs[""] = graph
        client.patch("/api/settings", json={"exa_api_key": "exa-secret"})

    assert app.state.graphs == {}


def test_portfolio_returns_the_injected_snapshot(tmp_path: Path) -> None:
    """The endpoint maps a portfolio snapshot to JSON."""

    async def fetcher(settings: AppSettings, range_: str) -> Portfolio:
        assert range_ == "1W"
        return Portfolio(
            as_of="2026-11-05T03:00:12Z",
            paper=True,
            account=Account(
                currency="USD",
                equity=100000.0,
                cash=25000.0,
                buying_power=50000.0,
                long_market_value=75000.0,
            ),
            day=DayPnl(pnl=250.0, pnl_pct=0.25),
            positions=[],
            equity_curve=[],
        )

    with _client(tmp_path, portfolio_fetcher=fetcher) as client:
        response = client.get("/api/portfolio", params={"range": "1W"})

    assert response.status_code == 200
    assert response.json()["account"]["equity"] == 100000.0
    assert response.json()["paper"] is True


def test_portfolio_without_broker_is_503(tmp_path: Path) -> None:
    """Missing broker credentials surface as 503."""
    settings = Settings(db_path=tmp_path / "data.db")
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/portfolio")
    assert response.status_code == 503


def test_openapi_lists_every_route(tmp_path: Path) -> None:
    """The generated schema covers the contract and the docs are served."""
    app = create_app(Settings(db_path=tmp_path / "data.db"))
    paths = app.openapi()["paths"]
    assert set(paths) >= {
        "/api/chat",
        "/api/threads",
        "/api/threads/{thread_id}",
        "/api/portfolio",
        "/api/profile",
        "/api/journal",
        "/api/health",
    }

    with TestClient(app) as client:
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200


def test_journal_attaches_an_outcome_without_a_source(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A stored decision gets a measured outcome from local prices."""
    from tradecopilot_agent.outcomes import attach_outcomes

    monkeypatch.setattr(
        "tradecopilot_agent.server.app.attach_outcomes",
        lambda rows, store: attach_outcomes(rows, store, date(2026, 11, 17)),
    )
    app = create_app(Settings(db_path=tmp_path / "data.db"))
    with TestClient(app) as client:
        store = app.state.store
        store.observe_prices(
            [
                ("NVDA", "2026-10-01", 100.0),
                ("NVDA", "2026-10-28", 110.0),
                ("SPY", "2026-10-01", 500.0),
                ("SPY", "2026-10-28", 505.0),
            ]
        )
        store.append_journal(
            {
                "decision_id": "d1",
                "created_at": "2026-10-01T10:00:00+00:00",
                "legs": [
                    {
                        "ticker": "NVDA",
                        "side": "buy",
                        "qty": 10.0,
                        "notional": 1000.0,
                        "entry_price": 100.0,
                        "fill_price": 100.0,
                        "fill_at": "2026-10-01T15:00:00+00:00",
                        "status": "filled",
                    }
                ],
                "thesis": "x",
                "horizon": "weeks",
                "evidence_ids": [],
                "status": "filled",
                "user_action": "approve",
                "rejection_reason": None,
                "updated_at": "2026-10-01T15:00:00+00:00",
            }
        )
        body = client.get("/api/journal").json()

    item = body["items"][0]
    assert item["legs"][0]["entry_price"] == 100.0
    assert item["outcome"]["return_pct"] == 10.0
    assert item["outcome"]["partial"] is False


def _seed_rejections(store: Any) -> None:
    """Seed two size rejections and backdate the profile update."""
    from tradecopilot_agent.store import now_iso

    updated = now_iso()
    for index, reason in enumerate(["Too large for me", "Too big"]):
        store.append_journal(
            {
                "decision_id": f"d{index}",
                "created_at": updated,
                "updated_at": updated,
                "legs": [
                    {
                        "ticker": "NVDA",
                        "side": "buy",
                        "qty": 1.0,
                        "notional": 100.0,
                        "entry_price": 100.0,
                        "fill_price": None,
                        "fill_at": None,
                        "status": "rejected",
                    }
                ],
                "thesis": "x",
                "horizon": "weeks",
                "evidence_ids": [],
                "status": "rejected",
                "user_action": "reject",
                "rejection_reason": reason,
            }
        )
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE profile SET updated_at = ? WHERE id = 1",
            ("2026-10-01T10:00:00+00:00",),
        )


def test_profile_returns_suggestions(tmp_path: Path) -> None:
    """Two size rejections surface a lower cap on the profile."""
    app = create_app(Settings(db_path=tmp_path / "data.db"))
    with TestClient(app) as client:
        _seed_rejections(app.state.store)
        body = client.get("/api/profile").json()

    assert body["suggestions"][0]["key"] == "cap_8"
    assert body["suggestions"][0]["patch"] == {"position_cap_pct": 8.0}


def test_accepting_a_suggestion_removes_it(tmp_path: Path) -> None:
    """Applying the suggested value satisfies the rule."""
    app = create_app(Settings(db_path=tmp_path / "data.db"))
    with TestClient(app) as client:
        _seed_rejections(app.state.store)
        body = client.patch("/api/profile", json={"position_cap_pct": 8.0}).json()

    assert body["suggestions"] == []


def test_dismissing_a_suggestion_removes_it(tmp_path: Path) -> None:
    """A dismissed suggestion is not returned again."""
    app = create_app(Settings(db_path=tmp_path / "data.db"))
    with TestClient(app) as client:
        _seed_rejections(app.state.store)
        response = client.post("/api/profile/suggestions/cap_8/dismiss")
        body = client.get("/api/profile").json()

    assert response.status_code == 204
    assert body["suggestions"] == []


def test_put_provider_rejects_unsupported_npm(tmp_path: Path) -> None:
    """A provider outside the supported integrations is rejected."""
    with _client(tmp_path) as client:
        response = client.put(
            "/api/providers/vendor",
            json={"api_key": "k", "npm": "@ai-sdk/azure", "models": []},
        )
    assert response.status_code == 400
    assert "not supported" in response.json()["detail"]


def test_put_provider_accepts_openrouter(tmp_path: Path) -> None:
    """The OpenRouter client package is a supported integration."""
    with _client(tmp_path) as client:
        response = client.put(
            "/api/providers/openrouter",
            json={
                "api_key": "k",
                "base_url": "https://openrouter.ai/api/v1",
                "npm": "@openrouter/ai-sdk-provider",
                "models": [
                    {"id": "openai/gpt-5.1", "name": "GPT-5.1", "tool_call": True}
                ],
            },
        )
    assert response.status_code == 200


def test_put_provider_rejects_non_tool_model(tmp_path: Path) -> None:
    """A model without tool calls cannot be configured."""
    with _client(tmp_path) as client:
        response = client.put(
            "/api/providers/openai",
            json={
                "api_key": "k",
                "npm": "@ai-sdk/openai",
                "models": [{"id": "embed", "name": "Embed", "tool_call": False}],
            },
        )
    assert response.status_code == 400
    assert "tool" in response.json()["detail"]


def test_put_provider_moves_selection_when_model_removed(tmp_path: Path) -> None:
    """Removing the selected model through the API moves to the first one left."""
    with _client(tmp_path) as client:
        client.put(
            "/api/providers/openai",
            json={
                "api_key": "k",
                "npm": "@ai-sdk/openai",
                "models": [{"id": "gpt-5", "name": "GPT-5"}],
            },
        )
        client.patch(
            "/api/settings",
            json={"model_provider": "openai", "model_id": "gpt-5"},
        )
        client.put(
            "/api/providers/openai",
            json={
                "api_key": "k",
                "npm": "@ai-sdk/openai",
                "models": [{"id": "gpt-4", "name": "GPT-4"}],
            },
        )
        settings = client.get("/api/settings").json()
    assert settings["model_provider"] == "openai"
    assert settings["model_id"] == "gpt-4"


def test_patch_selection_rejects_unconfigured_model(tmp_path: Path) -> None:
    """Selecting a model without a credential row is rejected."""
    with _client(tmp_path) as client:
        response = client.patch(
            "/api/settings", json={"model_provider": "openai", "model_id": "gpt-5"}
        )
    assert response.status_code == 400


def test_settings_ignores_environment_keys(tmp_path: Path, monkeypatch) -> None:
    """Provider keys come from SQLite only."""
    monkeypatch.setenv("OPENAI_API_KEY", "from-env")
    with _client(tmp_path) as client:
        settings = client.get("/api/settings").json()
    assert settings["providers"] == []


def test_health_reports_catalog_ids(tmp_path: Path) -> None:
    """Health exposes the catalog provider and model ids."""
    with _client(tmp_path) as client:
        body = client.get("/api/health").json()
    assert body == {"status": "ok", "model_provider": "", "model_id": ""}


def test_chat_rejects_reasoning_not_in_the_model_options(tmp_path: Path) -> None:
    """An override outside the model's options is a 400."""
    factory = lambda _app, _reasoning: StubGraph()  # noqa: E731
    client = TestClient(create_app(Settings(db_path=tmp_path / "data.db"), factory))
    with client:
        client.put(
            "/api/providers/openai",
            json={
                "api_key": "k",
                "npm": "@ai-sdk/openai",
                "models": [
                    {
                        "id": "gpt-5",
                        "name": "GPT-5",
                        "reasoning_options": [
                            {"type": "effort", "values": ["low", "high"]}
                        ],
                    }
                ],
            },
        )
        client.patch(
            "/api/settings",
            json={"model_provider": "openai", "model_id": "gpt-5"},
        )
        response = client.post(
            "/api/chat",
            json={
                "thread_id": "t1",
                "reasoning": "max",
                "messages": [
                    {
                        "id": "u1",
                        "role": "user",
                        "parts": [{"type": "text", "text": "hi"}],
                    }
                ],
            },
        )
    assert response.status_code == 400
    assert "reasoning" in response.json()["detail"].lower()


def test_graph_is_cached_per_reasoning(tmp_path: Path) -> None:
    """One graph is built per effective reasoning value."""
    seen: list[str] = []
    factory = lambda _app, reasoning: seen.append(reasoning) or StubGraph()  # noqa: E731
    client = TestClient(create_app(Settings(db_path=tmp_path / "data.db"), factory))
    with client:
        client.put(
            "/api/providers/openai",
            json={
                "api_key": "k",
                "npm": "@ai-sdk/openai",
                "models": [
                    {
                        "id": "gpt-5",
                        "name": "GPT-5",
                        "reasoning_options": [
                            {"type": "effort", "values": ["low", "high"]}
                        ],
                    }
                ],
            },
        )
        client.patch(
            "/api/settings",
            json={"model_provider": "openai", "model_id": "gpt-5"},
        )
        message = {
            "id": "u1",
            "role": "user",
            "parts": [{"type": "text", "text": "hi"}],
        }
        client.post("/api/chat", json={"reasoning": "low", "messages": [message]})
        client.post("/api/chat", json={"reasoning": "low", "messages": [message]})
        client.post("/api/chat", json={"reasoning": "high", "messages": [message]})
    assert seen == ["low", "high"]


def test_switching_models_clears_an_incompatible_reasoning_default(
    tmp_path: Path,
) -> None:
    """A default that the next model does not allow is cleared, not rejected."""
    with _client(tmp_path) as client:
        client.put(
            "/api/providers/openai",
            json={
                "api_key": "k",
                "npm": "@ai-sdk/openai",
                "models": [
                    {
                        "id": "gpt-5",
                        "name": "GPT-5",
                        "reasoning_options": [
                            {"type": "effort", "values": ["low", "high"]}
                        ],
                    },
                    {
                        "id": "gpt-4",
                        "name": "GPT-4",
                        "reasoning_options": [{"type": "effort", "values": ["low"]}],
                    },
                ],
            },
        )
        client.patch(
            "/api/settings",
            json={
                "model_provider": "openai",
                "model_id": "gpt-5",
                "reasoning_effort": "high",
            },
        )
        response = client.patch(
            "/api/settings", json={"model_provider": "openai", "model_id": "gpt-4"}
        )

    assert response.status_code == 200
    assert response.json()["reasoning_effort"] == ""
