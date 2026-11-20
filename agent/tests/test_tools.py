"""Tool behavior against a stub data source."""

import asyncio
import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

from tradecopilot_agent.state import EvidenceRecord, ToolOutput
from tradecopilot_agent.store import Store
from tradecopilot_agent.tools import (
    PURPOSE_DESCRIPTION,
    TradingTools,
    build_tools,
    split_orders,
)

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
        open_order_list: list[dict] | None = None,
        shorting_enabled: bool = False,
        fail_intents: set[str] | None = None,
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
        self.open_order_list = open_order_list or []
        self.shorting_enabled = shorting_enabled
        self.fail_intents = fail_intents or set()
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
                        "shorting_enabled": self.shorting_enabled,
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

    async def place_leg(
        self, leg: dict, client_order_id: str, position_intent: str | None = None
    ) -> ToolOutput:
        order = {**leg, "position_intent": position_intent}
        self.placed.append((order, client_order_id))
        if position_intent in self.fail_intents:
            return ToolOutput(summary="order rejected", error="http")
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
        return ToolOutput(summary=json.dumps(self.open_order_list))

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
    order = {
        "order_id": "o1",
        "ticker": "AAPL",
        "side": "buy",
        "qty": "1",
        "status": "accepted",
    }
    tools, _ = _tools(tmp_path, FakeSource(open_order_list=[order]))

    output = asyncio.run(tools.open_orders())

    assert output.error is None
    assert json.loads(output.summary)[0]["order_id"] == "o1"


def test_a_second_proposal_is_refused_while_one_waits(tmp_path: Path) -> None:
    """One ticket waiting for approval blocks the next proposal."""
    tools, _ = _tools(tmp_path, FakeSource())
    state = {"pending_tickets": {"t_1": {"ticket": {"id": "t_1"}}}}

    output = asyncio.run(
        tools.propose(
            [{"ticker": "AAPL", "side": "buy", "qty": 1}], "x", "weeks", state
        )
    )

    assert output.error == "ticket_pending"


def test_an_open_ticket_does_not_block_another_conversation(tmp_path: Path) -> None:
    """A reservation belongs to its thread, not to the shared tool instance."""
    tools, _ = _tools(tmp_path, FakeSource())
    first = asyncio.run(
        tools.propose(
            [{"ticker": "AAPL", "side": "buy", "qty": 1}], "a", "weeks", {}, "thread-a"
        )
    )
    assert first.proposal is not None, first.summary

    second = asyncio.run(
        tools.propose(
            [{"ticker": "AAPL", "side": "buy", "qty": 1}], "b", "weeks", {}, "thread-b"
        )
    )

    assert second.error is None
    assert second.proposal is not None


def test_parallel_proposals_leave_one_ticket(tmp_path: Path) -> None:
    """Two proposals in one model step cannot both become tickets."""
    tools, _ = _tools(tmp_path, FakeSource())

    async def propose_twice() -> list[ToolOutput]:
        return await asyncio.gather(
            tools.propose(
                [{"ticker": "AAPL", "side": "buy", "qty": 1}], "a", "weeks", {}
            ),
            tools.propose(
                [{"ticker": "AAPL", "side": "buy", "qty": 1}], "b", "weeks", {}
            ),
        )

    outputs = asyncio.run(propose_twice())

    errors = [output.error for output in outputs if output.error]
    proposals = [output for output in outputs if output.proposal is not None]
    assert errors == ["ticket_pending"]
    assert len(proposals) == 1


def test_execution_releases_the_proposal_slot(tmp_path: Path) -> None:
    """After a ticket resolves, the next proposal is allowed."""
    source = FakeSource()
    tools, store = _tools(tmp_path, source)
    store.patch_profile(
        {"execution": {"autonomous": True, "max_order_notional": 100_000.0}}
    )
    first = asyncio.run(
        tools.propose([{"ticker": "AAPL", "side": "buy", "qty": 1}], "a", "weeks")
    )
    assert first.proposal is not None, first.summary
    pending = {first.proposal["id"]: {"ticket": first.proposal}}
    asyncio.run(tools.execute(first.proposal["id"], {"pending_tickets": pending}))

    second = asyncio.run(
        tools.propose([{"ticker": "AAPL", "side": "buy", "qty": 1}], "b", "weeks")
    )

    assert second.error is None
    assert second.proposal is not None


def test_a_proposal_is_refused_while_orders_work(tmp_path: Path) -> None:
    """Working broker orders block a new ticket, closing the split bypass."""
    source = FakeSource(
        open_order_list=[{"order_id": "o1", "ticker": "XOM", "status": "new"}]
    )
    tools, _ = _tools(tmp_path, source)

    output = asyncio.run(
        tools.propose([{"ticker": "AAPL", "side": "buy", "qty": 1}], "x", "weeks")
    )

    assert output.error == "ticket_working"
    assert source.placed == []


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


def test_execution_rechecks_affordability(tmp_path: Path) -> None:
    """A ticket is blocked at execution when buying power fell since the proposal."""
    source = FakeSource(cash=100.0, buying_power=100_000.0)
    tools, store = _tools(tmp_path, source)
    store.patch_profile(
        {"execution": {"autonomous": True, "max_order_notional": 100_000.0}}
    )
    proposed = asyncio.run(
        tools.propose([{"ticker": "AAPL", "side": "buy", "qty": 1}], "thesis", "weeks")
    )
    assert proposed.proposal is not None, proposed.summary
    # The broker lowers the account between the proposal and execution.
    source.buying_power = 100.0

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

    assert output.error == "blocked"
    assert "insufficient_buying_power" in output.summary
    assert source.placed == []


def test_proposal_records_the_entry_price(tmp_path: Path) -> None:
    """The proposal journal row keeps the quote used to size the ticket."""
    source = FakeSource(prices={"AAPL": 100.0})
    tools, store = _tools(tmp_path, source)

    asyncio.run(
        tools.propose([{"ticker": "AAPL", "side": "buy", "qty": 5}], "x", "weeks")
    )

    row = store.list_journal(page_no=1, page_size=10)[0][0]
    assert row["legs"][0]["entry_price"] == 100.0


def test_a_priced_limit_leg_keeps_the_model_price(tmp_path: Path) -> None:
    """A leg price and order type reach the ticket and the journal."""
    source = FakeSource(
        prices={"AAPL": 100.0},
        positions=[{"ticker": "AAPL", "qty": 5, "market_value": 500.0}],
    )
    tools, store = _tools(tmp_path, source)

    output = asyncio.run(
        tools.propose(
            [
                {
                    "ticker": "AAPL",
                    "side": "sell",
                    "qty": 5,
                    "price": 95.0,
                    "type": "limit",
                }
            ],
            "exit",
            "immediate",
        )
    )

    assert output.proposal is not None, output.summary
    leg = output.proposal["legs"][0]
    assert leg["entry_price"] == 95.0
    assert leg["order_type"] == "limit"
    row = store.list_journal(page_no=1, page_size=10)[0][0]
    assert row["legs"][0]["entry_price"] == 95.0
    assert row["legs"][0]["notional"] == 475.0


def test_a_limit_leg_needs_a_price(tmp_path: Path) -> None:
    """A limit order without a price is rejected instead of repriced."""
    tools, _ = _tools(tmp_path, FakeSource())

    output = asyncio.run(
        tools.propose(
            [{"ticker": "AAPL", "side": "buy", "qty": 1, "type": "limit"}],
            "x",
            "weeks",
        )
    )

    assert output.error == "invalid"
    assert "needs a price" in output.summary


def test_execution_sends_the_leg_price_to_the_broker(tmp_path: Path) -> None:
    """The limit price survives execute_ticket and reaches place_leg."""
    source = FakeSource(prices={"AAPL": 100.0})
    tools, store = _tools(tmp_path, source)
    store.patch_profile(
        {"execution": {"autonomous": True, "max_order_notional": 100_000.0}}
    )
    proposed = asyncio.run(
        tools.propose(
            [
                {
                    "ticker": "AAPL",
                    "side": "buy",
                    "qty": 1,
                    "price": 95.0,
                    "type": "limit",
                }
            ],
            "x",
            "weeks",
        )
    )
    assert proposed.proposal is not None, proposed.summary

    pending = {
        proposed.proposal["id"]: {"ticket": proposed.proposal},
    }
    asyncio.run(tools.execute(proposed.proposal["id"], {"pending_tickets": pending}))

    placed, _ = source.placed[0]
    assert placed["entry_price"] == 95.0
    assert placed["order_type"] == "limit"


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


def test_an_expired_ticket_is_not_executed(tmp_path: Path, monkeypatch) -> None:
    """A proposal from long ago needs a fresh approval, not a placement."""
    from tradecopilot_agent import tools as tools_module

    monkeypatch.setattr(
        tools_module,
        "interrupt",
        lambda _value: {"decisions": [{"type": "approve"}]},
    )
    source = FakeSource()
    tools, _ = _tools(tmp_path, source)
    ticket = {
        "id": "t_old",
        "legs": [{"ticker": "AAPL", "side": "buy", "qty": 1, "entry_price": 100.0}],
        "thesis": "",
        "horizon": "weeks",
        "created_at": "2026-11-19T00:00:00Z",
    }

    output = asyncio.run(
        tools.execute("t_old", {"pending_tickets": {"t_old": {"ticket": ticket}}})
    )

    assert output.error == "expired"
    assert source.placed == []


def test_impact_reports_signed_quantities() -> None:
    """The card needs the signed position before and after the leg."""
    impact = TradingTools._impact(
        {
            "equity": 100_000.0,
            "positions": [{"ticker": "NVDA", "qty": 10, "market_value": 1000.0}],
        },
        {"NVDA": 100.0},
        [{"ticker": "NVDA", "side": "sell", "qty": 30}],
    )

    assert impact["before_qty"]["NVDA"] == 10.0
    assert impact["after_qty"]["NVDA"] == -20.0
    assert impact["after_pct"]["NVDA"] < 0


def test_split_orders_covers_every_shape() -> None:
    """A leg is split into its close and open portions, close first."""
    assert split_orders("sell", 100, 10) == [
        ("sell_to_close", 10),
        ("sell_to_open", 90),
    ]
    assert split_orders("buy", 50, -20) == [
        ("buy_to_close", 20),
        ("buy_to_open", 30),
    ]
    assert split_orders("sell", 30, 0) == [("sell_to_open", 30)]
    assert split_orders("buy", 30, 0) == [("buy_to_open", 30)]
    assert split_orders("sell", 10, 10) == [("sell_to_close", 10)]


def test_propose_allows_a_short_on_an_enabled_account(tmp_path: Path) -> None:
    """A sell above the holding builds a ticket when shorting is enabled."""
    source = FakeSource(
        shorting_enabled=True,
        prices={"NVDA": 100.0},
        positions=[{"ticker": "NVDA", "qty": 10, "market_value": 1000.0}],
    )
    tools, _ = _tools(tmp_path, source)

    output = asyncio.run(
        tools.propose([{"ticker": "NVDA", "side": "sell", "qty": 30}], "short", "weeks")
    )

    assert output.error is None
    assert output.proposal is not None
    assert output.proposal["portfolio_impact"]["after_qty"]["NVDA"] == -20.0


def test_propose_refuses_a_short_on_a_long_only_account(tmp_path: Path) -> None:
    """The same ticket is blocked without the capability."""
    source = FakeSource(
        prices={"NVDA": 100.0},
        positions=[{"ticker": "NVDA", "qty": 10, "market_value": 1000.0}],
    )
    tools, _ = _tools(tmp_path, source)

    output = asyncio.run(
        tools.propose([{"ticker": "NVDA", "side": "sell", "qty": 30}], "short", "weeks")
    )

    assert output.error == "blocked"


def test_execute_splits_a_flipping_sell(tmp_path: Path) -> None:
    """A sell past the holding closes first, then opens the short."""
    source = FakeSource(
        shorting_enabled=True,
        prices={"NVDA": 100.0},
        positions=[{"ticker": "NVDA", "qty": 10, "market_value": 1000.0}],
    )
    tools, store = _tools(tmp_path, source)
    store.patch_profile(
        {"execution": {"autonomous": True, "max_order_notional": 100_000.0}}
    )
    proposed = asyncio.run(
        tools.propose([{"ticker": "NVDA", "side": "sell", "qty": 30}], "short", "weeks")
    )
    assert proposed.proposal is not None
    pending = {proposed.proposal["id"]: {"ticket": proposed.proposal}}

    asyncio.run(tools.execute(proposed.proposal["id"], {"pending_tickets": pending}))

    intents = [order[0]["position_intent"] for order in source.placed]
    quantities = [order[0]["qty"] for order in source.placed]
    assert intents == ["sell_to_close", "sell_to_open"]
    assert quantities == [10.0, 20.0]


def test_a_failed_close_suppresses_the_open(tmp_path: Path) -> None:
    """A rejected close never sends the opening order."""
    source = FakeSource(
        shorting_enabled=True,
        prices={"NVDA": 100.0},
        positions=[{"ticker": "NVDA", "qty": 10, "market_value": 1000.0}],
        fail_intents={"sell_to_close"},
    )
    tools, store = _tools(tmp_path, source)
    store.patch_profile(
        {"execution": {"autonomous": True, "max_order_notional": 100_000.0}}
    )
    proposed = asyncio.run(
        tools.propose([{"ticker": "NVDA", "side": "sell", "qty": 30}], "short", "weeks")
    )
    assert proposed.proposal is not None
    pending = {proposed.proposal["id"]: {"ticket": proposed.proposal}}

    result = asyncio.run(
        tools.execute(proposed.proposal["id"], {"pending_tickets": pending})
    )

    assert [order[0]["position_intent"] for order in source.placed] == ["sell_to_close"]
    assert json.loads(result.summary)["legs"][0]["status"] == "failed"


def test_split_orders_track_earlier_legs(tmp_path: Path) -> None:
    """A second leg on the same ticker sees the first leg's resulting position."""
    source = FakeSource(shorting_enabled=True, prices={"NVDA": 100.0})
    tools, store = _tools(tmp_path, source)
    store.patch_profile(
        {"execution": {"autonomous": True, "max_order_notional": 100_000.0}}
    )
    proposed = asyncio.run(
        tools.propose(
            [
                {"ticker": "NVDA", "side": "sell", "qty": 2},
                {"ticker": "NVDA", "side": "buy", "qty": 5},
            ],
            "flip",
            "weeks",
        )
    )
    assert proposed.proposal is not None
    pending = {proposed.proposal["id"]: {"ticket": proposed.proposal}}

    asyncio.run(tools.execute(proposed.proposal["id"], {"pending_tickets": pending}))

    placed = [(order[0]["position_intent"], order[0]["qty"]) for order in source.placed]
    assert placed == [
        ("sell_to_open", 2.0),
        ("buy_to_close", 2.0),
        ("buy_to_open", 3.0),
    ]


def test_a_cover_does_not_need_cash(tmp_path: Path) -> None:
    """Closing a short releases collateral, so it is not an unfunded buy."""
    source = FakeSource(
        shorting_enabled=True,
        cash=0.0,
        buying_power=100_000.0,
        prices={"NVDA": 100.0},
        positions=[{"ticker": "NVDA", "qty": -3, "market_value": -300.0}],
    )
    tools, store = _tools(tmp_path, source)
    store.patch_profile(
        {"execution": {"autonomous": True, "max_order_notional": 100_000.0}}
    )
    proposed = asyncio.run(
        tools.propose([{"ticker": "NVDA", "side": "buy", "qty": 3}], "cover", "weeks")
    )
    assert proposed.proposal is not None
    pending = {proposed.proposal["id"]: {"ticket": proposed.proposal}}

    result = asyncio.run(
        tools.execute(proposed.proposal["id"], {"pending_tickets": pending})
    )

    assert json.loads(result.summary)["legs"][0]["status"] == "filled"
    assert source.placed[0][0]["position_intent"] == "buy_to_close"
