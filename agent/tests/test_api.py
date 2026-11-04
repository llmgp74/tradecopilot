"""Contract tests for the REST endpoints."""

import json
import sqlite3
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
        "name": "execute_order",
        "args": {"qty": 10},
        "id": "call_1",
        "type": "tool_call",
    }
    snapshot = SimpleNamespace(
        values={
            "messages": [
                HumanMessage(content="buy", id="u1"),
                AIMessage(content="", id="a1", tool_calls=[tool_call]),
            ]
        },
        interrupts=(
            Interrupt(
                id="int-1",
                value={
                    "action_requests": [
                        {
                            "name": "execute_order",
                            "args": {"qty": 10},
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
    assert part["type"] == "tool-execute_order"
    assert part["state"] == "approval-requested"
    assert part["approval"]["id"] == "call_1"
    assert part["approval"]["ticket"] == {"qty": 10}


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
            connection.execute(
                """
                INSERT INTO journal (
                  id, created_at, tickers, side, qty, size_pct, thesis,
                  evidence_ids, status, user_action, rejection_reason,
                  fill_price, fill_at, outcome_note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "e1",
                    "2026-11-04T14:02:11Z",
                    json.dumps(["NVDA"]),
                    "buy",
                    10.0,
                    2.0,
                    "thesis",
                    json.dumps(["ev1"]),
                    "rejected",
                    "reject",
                    "too large",
                    None,
                    None,
                    None,
                ),
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


def test_portfolio_returns_the_injected_snapshot(tmp_path: Path) -> None:
    """The endpoint maps a portfolio snapshot to JSON."""

    async def fetcher(settings: Settings, range_: str) -> Portfolio:
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
