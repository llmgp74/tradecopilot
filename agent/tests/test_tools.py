"""Tool behavior against a stub data source."""

import asyncio
from datetime import date
from pathlib import Path

from tradecopilot_agent.state import EvidenceRecord, ToolOutput
from tradecopilot_agent.store import Store
from tradecopilot_agent.tools import TradingTools

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
        tools.execute(proposed.proposal["id"], {"pending_ticket": proposed.proposal})
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
        tools.execute(proposed.proposal["id"], {"pending_ticket": proposed.proposal})
    )

    assert output.error == "rejected"
    rows, _ = store.list_journal(page_no=1, page_size=10)
    assert rows[0]["status"] == "rejected"
    assert rows[0]["rejection_reason"] == "not now"


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
        tools.execute(proposed.proposal["id"], {"pending_ticket": proposed.proposal})
    )

    assert output.error is None
    assert source.placed == []
    rows, _ = store.list_journal(page_no=1, page_size=10)
    assert rows[0]["status"] == "failed"
    assert rows[0]["legs"][0]["status"] == "skipped_unfunded"
