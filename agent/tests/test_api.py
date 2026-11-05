"""Contract tests for the REST endpoints."""

import json
import sqlite3
import stat
from collections.abc import AsyncIterator
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
    settings = Settings(db_path=tmp_path / "data.db", agent_model=None)
    factory = (lambda _app: graph) if graph is not None else None
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
            "pending_ticket": pending,
            "verification": [{"scope": "draft", "verdict": "supported", "text": "x"}],
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
    assert part["approval"]["verification"][0]["scope"] == "draft"


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
                "agent_model": "deepseek:deepseek-flash",
                "model_api_key": "secret-model",
                "alpaca_api_key": "secret-alpaca",
                "alpaca_api_secret": "secret-broker",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["model_api_key"] == "secret-model"
        assert body["alpaca_base_url"] == "https://paper-api.alpaca.markets"
        assert response.headers["Cache-Control"] == "no-store"
        assert client.get("/api/health").json()["agent_model"] == (
            "deepseek:deepseek-flash"
        )

        with sqlite3.connect(tmp_path / "data.db") as connection:
            row = connection.execute(
                """
                SELECT model_api_key, alpaca_api_key, alpaca_api_secret
                FROM settings WHERE id = 1
                """
            ).fetchone()

    assert row is not None
    for token in row:
        assert "secret" not in token
        assert token.startswith("gAAAA")
    key_path = tmp_path / "settings.key"
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600


def test_settings_clear_falls_back_to_environment(tmp_path: Path) -> None:
    """Clearing a stored value restores the environment value."""
    settings = Settings(
        db_path=tmp_path / "data.db",
        agent_model="env:model",
        model_api_key=None,
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/settings").json()["agent_model"] == "env:model"

        stored = client.patch(
            "/api/settings", json={"agent_model": "stored:model"}
        ).json()
        assert stored["agent_model"] == "stored:model"

        cleared = client.patch("/api/settings", json={"agent_model": ""}).json()
        assert cleared["agent_model"] == "env:model"


def test_settings_change_discards_the_graph(tmp_path: Path) -> None:
    """Changing the model invalidates the cached graph."""
    graph = StubGraph()
    app = create_app(Settings(db_path=tmp_path / "data.db"), lambda _app: graph)
    with TestClient(app) as client:
        app.state.graph = graph
        client.patch("/api/settings", json={"agent_model": "deepseek:other"})

    assert app.state.graph is None


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
    settings = Settings(
        db_path=tmp_path / "data.db",
        agent_model=None,
        alpaca_api_key=None,
        alpaca_api_secret=None,
    )
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
