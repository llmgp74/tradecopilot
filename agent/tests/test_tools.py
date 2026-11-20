"""Tool behavior against a stub data source."""

import asyncio
import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

from tradecopilot_agent.state import EvidenceRecord, ToolOutput
from tradecopilot_agent.store import Store
from tradecopilot_agent.tools import PURPOSE_DESCRIPTION, TradingTools, build_tools

FETCHED = "2026-11-05T14:00:00Z"


def _record(tool: str, source: str, payload: dict) -> EvidenceRecord:
    return EvidenceRecord(
        id=f"ev_{tool}",
        tool=tool,
        args={},
        source=source,
        fetched_at=FETCHED,
        payload=payload,
    )


class FakeSource:
    """A source with fixed account, quotes, and order fills."""

    def __init__(
        self,
        *,
        capabilities: set[str] | None = None,
        cash: float = 100_000.0,
        buying_power: float | None = None,
        prices: dict[str, float] | None = None,
        place_status: str = "filled",
        positions: list[dict] | None = None,
    ) -> None:
        self._capabilities = capabilities or {
            "alpaca",
            "order_execution",
            "edgar",
            "fmp",
            "finnhub",
            "fred",
        }
        self.cash = cash
        self.buying_power = cash if buying_power is None else buying_power
        self.prices = prices or {"AAPL": 1000.0, "NVDA": 1000.0}
        self.place_status = place_status
        self.positions = positions or []
        self.placed: list[tuple[dict, str]] = []
        self.cancelled: list[str] = []

    def capabilities(self) -> set[str]:
        return set(self._capabilities)

    async def quote(self, ticker: str) -> ToolOutput:
        price = self.prices.get(ticker)
        if price is None:
            return ToolOutput(summary="no quote", error="missing")
        return ToolOutput(
            summary=f"{ticker} {price}",
            evidence=[
                _record("get_quote", "alpaca", {"price": price, "ticker": ticker})
            ],
        )

    async def bars(self, ticker: str, period: str, interval: str) -> ToolOutput:
        return ToolOutput(summary="bars")

    async def portfolio(self) -> ToolOutput:
        return ToolOutput(
            summary="account",
            evidence=[
                _record(
                    "get_portfolio",
                    "alpaca",
                    {
                        "equity": 100_000.0,
                        "cash": self.cash,
                        "buying_power": self.buying_power,
                        "positions": self.positions,
                    },
                )
            ],
        )

    async def positions(self) -> ToolOutput:
        return ToolOutput(summary="none")

    async def fundamentals(self, ticker: str) -> ToolOutput:
        return ToolOutput(
            summary="sector",
            evidence=[_record("get_fundamentals", "fmp", {"sector": "Technology"})],
        )

    async def filings(self, ticker: str, limit: int = 10) -> ToolOutput:
        return ToolOutput(summary="filings")

    async def xbrl_fact(
        self, ticker: str, tag: str, period: str, unit: str
    ) -> ToolOutput:
        return ToolOutput(summary="fact")

    async def news(self, ticker: str, limit: int = 10) -> ToolOutput:
        return ToolOutput(summary="news")

    async def macro(self, series: str, period: str) -> ToolOutput:
        return ToolOutput(summary="macro")

    async def place_leg(self, leg: dict, client_order_id: str) -> ToolOutput:
        self.placed.append((leg, client_order_id))
        return ToolOutput(
            summary="placed",
            evidence=[
                _record(
                    "place_leg",
                    "alpaca",
                    {
                        "status": self.place_status,
                        "fill_price": self.prices.get(leg["ticker"]),
                        "fill_at": FETCHED,
                    },
                )
            ],
        )

    async def open_orders(self) -> ToolOutput:
        return ToolOutput(
            summary=json.dumps(
                [
                    {
                        "order_id": "o1",
                        "ticker": "AAPL",
                        "side": "buy",
                        "qty": "1",
                        "status": "accepted",
                    }
                ]
            )
        )

    async def order_history(self, days: int = 7) -> ToolOutput:
        return ToolOutput(
            summary=json.dumps(
                [
                    {
                        "ticker": "AAPL",
                        "side": "buy",
                        "qty": "2",
                        "status": "filled",
                        "filled_at": FETCHED,
                    }
                ]
            )
        )

    async def cancel_order(self, order_id: str) -> ToolOutput:
        self.cancelled.append(order_id)
        return ToolOutput(summary=f"Cancel requested for order {order_id}.")


def _tools(tmp_path: Path, source: FakeSource) -> tuple[TradingTools, Store]:
    store = Store(tmp_path / "data.db")
    tools = TradingTools(source, store, as_of=date(2026, 11, 5))
    return tools, store


def test_a_proposal_orders_sells_first(tmp_path: Path) -> None:
    """The ticket stores sells before buys, whatever order the model used."""
    source = FakeSource(
        positions=[{"ticker": "NVDA", "qty": 10, "market_value": 10_000.0}]
    )
    tools, _ = _tools(tmp_path, source)

    output = asyncio.run(
        tools.propose(
            [
                {"ticker": "AAPL", "side": "buy", "qty": 5},
                {"ticker": "NVDA", "side": "sell", "qty": 1},
            ],
            "rebalance",
            "weeks",
        )
    )

    assert output.error is None
    assert output.proposal is not None
    assert output.proposal["id"].startswith("t_")
    assert [leg["side"] for leg in output.proposal["legs"]] == ["sell", "buy"]


def test_a_leg_without_a_ticker_is_rejected(tmp_path: Path) -> None:
    """A wrong argument name cannot become an empty-ticker quote."""
    tools, _ = _tools(tmp_path, FakeSource())

    output = asyncio.run(
        tools.propose([{"symbol": "SPY", "side": "buy", "qty": 1}], "buy", "weeks")
    )

    assert output.error == "invalid"
    assert "ticker" in output.summary
    assert output.proposal is None


def test_a_blocked_ticket_is_not_stored(tmp_path: Path) -> None:
    """The position cap blocks the ticket and writes no journal event."""
    tools, store = _tools(tmp_path, FakeSource())

    output = asyncio.run(
        tools.propose(
            [{"ticker": "AAPL", "side": "buy", "qty": 20}], "too big", "weeks"
        )
    )

    assert output.error == "blocked"
    assert output.proposal is None
    assert store.list_journal(page_no=1, page_size=10)[1] == 0


def test_a_twenty_leg_ticket_is_one_ticket(tmp_path: Path) -> None:
    """A basket past ten legs stays in a single approval."""
    source = FakeSource(prices={"NVDA": 1.0}, cash=10_000_000.0)
    tools, _ = _tools(tmp_path, source)
    legs = [{"ticker": "NVDA", "side": "buy", "qty": 1} for _ in range(20)]

    output = asyncio.run(tools.propose(legs, "basket", "weeks"))

    assert output.error is None
    assert output.proposal is not None
    assert len(output.proposal["legs"]) == 20


def test_a_large_ticket_stays_in_one_ticket(tmp_path: Path) -> None:
    """A basket well past the old ten-leg cap is one approval."""
    source = FakeSource(prices={"NVDA": 1.0}, cash=10_000_000.0)
    tools, _ = _tools(tmp_path, source)
    legs = [{"ticker": "NVDA", "side": "buy", "qty": 1} for _ in range(51)]

    output = asyncio.run(tools.propose(legs, "big basket", "weeks"))

    assert output.error is None
    assert output.proposal is not None
    assert len(output.proposal["legs"]) == 51


def test_a_ticket_beyond_one_thousand_legs_is_rejected(tmp_path: Path) -> None:
    """The safety bound refuses an oversized ticket with the limit named."""
    tools, _ = _tools(tmp_path, FakeSource())
    legs = [{"ticker": "NVDA", "side": "buy", "qty": 1} for _ in range(1001)]

    output = asyncio.run(tools.propose(legs, "too many", "weeks"))

    assert output.error == "invalid"
    assert "1000" in output.summary


def test_open_orders_are_listed(tmp_path: Path) -> None:
    """The listing carries the ids the model needs to cancel."""
    tools, _ = _tools(tmp_path, FakeSource())

    output = asyncio.run(tools.open_orders())

    assert output.error is None
    assert json.loads(output.summary)[0]["order_id"] == "o1"


def test_cancellation_does_not_pause_for_approval(tmp_path: Path, monkeypatch) -> None:
    """The user's cancel request is the approval, so the tool runs directly."""
    from tradecopilot_agent import tools as tools_module

    def fail(_value: object) -> None:
        raise AssertionError("cancellation must not interrupt")

    monkeypatch.setattr(tools_module, "interrupt", fail)
    source = FakeSource()
    tools, _ = _tools(tmp_path, source)

    output = asyncio.run(
        tools.cancel(
            [
                {"order_id": "o1", "ticker": "AAPL", "side": "buy", "qty": "1"},
                {"order_id": "o2", "ticker": "MSFT", "side": "buy", "qty": "1"},
            ]
        )
    )

    assert output.error is None
    assert source.cancelled == ["o1", "o2"]
    assert json.loads(output.summary)["status"] == "cancelled"


def test_cancellation_needs_order_ids(tmp_path: Path) -> None:
    """A call without broker ids is rejected before any approval."""
    tools, _ = _tools(tmp_path, FakeSource())

    output = asyncio.run(tools.cancel([{"ticker": "AAPL", "side": "buy"}]))

    assert output.error == "invalid"


def test_missing_provider_guards_the_tool(tmp_path: Path) -> None:
    """A tool whose provider is not configured returns an error."""
    source = FakeSource(capabilities={"alpaca"})
    tools, _ = _tools(tmp_path, source)

    output = asyncio.run(tools.fundamentals("NVDA"))

    assert output.error == "unavailable"


def test_autonomous_execution_fills_the_ticket(tmp_path: Path) -> None:
    """Autonomous mode places the legs and records the fill."""
    tools, store = _tools(tmp_path, FakeSource())
    store.patch_profile(
        {"execution": {"autonomous": True, "max_order_notional": 100_000.0}}
    )
    proposed = asyncio.run(
        tools.propose([{"ticker": "AAPL", "side": "buy", "qty": 5}], "thesis", "weeks")
    )
    assert proposed.proposal is not None

    output = asyncio.run(
        tools.execute(
            proposed.proposal["id"],
            {
                "pending_tickets": {
                    proposed.proposal["id"]: {"ticket": proposed.proposal}
                }
            },
        )
    )

    assert output.error is None
    assert output.ticket_done is True
    rows, _ = store.list_journal(page_no=1, page_size=10)
    assert rows[0]["status"] == "filled"
    assert rows[0]["legs"][0]["fill_price"] == 1000.0


def test_rejection_is_recorded(tmp_path: Path, monkeypatch) -> None:
    """A rejected interrupt writes a rejected decision."""
    from tradecopilot_agent import tools as tools_module

    monkeypatch.setattr(
        tools_module,
        "interrupt",
        lambda _value: {"decisions": [{"type": "reject", "message": "not now"}]},
    )
    tools, store = _tools(tmp_path, FakeSource())
    proposed = asyncio.run(
        tools.propose([{"ticker": "AAPL", "side": "buy", "qty": 1}], "thesis", "weeks")
    )
    assert proposed.proposal is not None

    output = asyncio.run(
        tools.execute(
            proposed.proposal["id"],
            {
                "pending_tickets": {
                    proposed.proposal["id"]: {"ticket": proposed.proposal}
                }
            },
        )
    )

    assert output.error == "rejected"
    rows, _ = store.list_journal(page_no=1, page_size=10)
    assert rows[0]["status"] == "rejected"
    assert rows[0]["rejection_reason"] == "not now"


def test_rejection_keeps_the_decision_time_and_notional(
    tmp_path: Path, monkeypatch
) -> None:
    """The reject snapshot is dated by the proposal and keeps the leg value."""
    from tradecopilot_agent import tools as tools_module

    monkeypatch.setattr(
        tools_module,
        "interrupt",
        lambda _value: {"decisions": [{"type": "reject", "message": "not now"}]},
    )
    monkeypatch.setattr(tools_module, "now_iso", lambda: "2026-10-01T10:00:00+00:00")
    tools, store = _tools(tmp_path, FakeSource())
    proposed = asyncio.run(
        tools.propose([{"ticker": "AAPL", "side": "buy", "qty": 2}], "thesis", "weeks")
    )
    assert proposed.proposal is not None

    monkeypatch.setattr(tools_module, "now_iso", lambda: "2026-11-15T10:00:00+00:00")
    asyncio.run(
        tools.execute(
            proposed.proposal["id"],
            {
                "pending_tickets": {
                    proposed.proposal["id"]: {"ticket": proposed.proposal}
                }
            },
        )
    )

    row = store.list_journal(page_no=1, page_size=10)[0][0]
    assert row["created_at"] == "2026-10-01T10:00:00+00:00"
    assert row["updated_at"] == "2026-11-15T10:00:00+00:00"
    assert row["legs"][0]["notional"] == 2000.0


def test_unfunded_buy_is_skipped(tmp_path: Path) -> None:
    """A buy without cash is skipped and nothing is placed."""
    source = FakeSource(cash=100.0, buying_power=100_000.0)
    tools, store = _tools(tmp_path, source)
    store.patch_profile(
        {"execution": {"autonomous": True, "max_order_notional": 100_000.0}}
    )
    proposed = asyncio.run(
        tools.propose([{"ticker": "AAPL", "side": "buy", "qty": 1}], "thesis", "weeks")
    )
    assert proposed.proposal is not None, proposed.summary

    output = asyncio.run(
        tools.execute(
            proposed.proposal["id"],
            {
                "pending_tickets": {
                    proposed.proposal["id"]: {"ticket": proposed.proposal}
                }
            },
        )
    )

    assert output.error is None
    assert source.placed == []
    rows, _ = store.list_journal(page_no=1, page_size=10)
    assert rows[0]["status"] == "failed"
    assert rows[0]["legs"][0]["status"] == "skipped_unfunded"


def test_proposal_records_the_entry_price(tmp_path: Path) -> None:
    """The proposal journal row keeps the quote used to size the ticket."""
    source = FakeSource(prices={"AAPL": 100.0})
    tools, store = _tools(tmp_path, source)

    asyncio.run(
        tools.propose([{"ticker": "AAPL", "side": "buy", "qty": 5}], "x", "weeks")
    )

    row = store.list_journal(page_no=1, page_size=10)[0][0]
    assert row["legs"][0]["entry_price"] == 100.0


def test_the_pending_ticket_records_the_entry_price(tmp_path: Path) -> None:
    """Execution snapshots copy the entry price from the pending ticket."""
    source = FakeSource(prices={"AAPL": 100.0})
    tools, _ = _tools(tmp_path, source)

    output = asyncio.run(
        tools.propose([{"ticker": "AAPL", "side": "buy", "qty": 5}], "x", "weeks")
    )

    assert output.proposal is not None
    assert output.proposal["legs"][0]["entry_price"] == 100.0


def test_every_app_tool_exposes_an_optional_purpose() -> None:
    """The model can say why it calls each tool, and the UI can label the row."""
    tools = build_tools(MagicMock(), MagicMock(), None)
    for built in tools:
        schema = built.args["purpose"]
        assert schema["description"] == PURPOSE_DESCRIPTION
        assert "purpose" not in built.args["purpose"].get("required", [])


def test_purpose_is_not_forwarded_to_the_data_source() -> None:
    """The label argument never changes what a tool does."""
    source = FakeSource()
    tools = {tool.name: tool for tool in build_tools(source, MagicMock(), None)}
    output = asyncio.run(
        tools["get_quote"].ainvoke({"ticker": "AAPL", "purpose": "Check the price"})
    )
    assert "AAPL" in str(output)


def test_trade_history_returns_broker_orders(tmp_path: Path) -> None:
    """Past fills come from the broker, not from the current positions."""
    tools = {
        tool.name: tool
        for tool in build_tools(FakeSource(), Store(tmp_path / "data.db"), None)
    }
    output = asyncio.run(tools["get_trade_history"].ainvoke({"days": 5}))
    text = str(output)
    assert "AAPL" in text
    assert "filled" in text


def test_trade_history_needs_the_broker(tmp_path: Path) -> None:
    """Without Alpaca the tool reports the missing capability."""
    source = FakeSource(capabilities={"edgar"})
    tools = {
        tool.name: tool
        for tool in build_tools(source, Store(tmp_path / "data.db"), None)
    }
    output = asyncio.run(tools["get_trade_history"].ainvoke({"days": 5}))
    assert "not configured" in str(output)
