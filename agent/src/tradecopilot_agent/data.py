"""The data source contract every tool binds to."""

from typing import Any, Protocol, runtime_checkable

from tradecopilot_agent.state import ToolOutput

CAPABILITIES = frozenset(
    {"alpaca", "order_execution", "edgar", "fmp", "finnhub", "fred"}
)


@runtime_checkable
class DataSource(Protocol):
    """Supplies the external data the agent tools read.

    The live app composes provider adapters. The evaluation harness replays
    frozen fixtures. A missing provider is reported by ``capabilities`` and its
    tools are hidden from the model.
    """

    def capabilities(self) -> set[str]:
        """Return the capabilities this source can serve right now."""
        ...

    async def quote(self, ticker: str) -> ToolOutput:
        """Return the latest quote for a ticker."""
        ...

    async def bars(self, ticker: str, period: str, interval: str) -> ToolOutput:
        """Return price bars for a ticker."""
        ...

    async def portfolio(self) -> ToolOutput:
        """Return the account and its positions."""
        ...

    async def positions(self) -> ToolOutput:
        """Return the open positions only."""
        ...

    async def fundamentals(self, ticker: str) -> ToolOutput:
        """Return profile, sector, and valuation ratios."""
        ...

    async def filings(self, ticker: str, limit: int = 10) -> ToolOutput:
        """Return recent SEC filings."""
        ...

    async def xbrl_fact(
        self, ticker: str, tag: str, period: str, unit: str
    ) -> ToolOutput:
        """Return one XBRL fact."""
        ...

    async def news(self, ticker: str, limit: int = 10) -> ToolOutput:
        """Return recent company news."""
        ...

    async def macro(self, series: str, period: str) -> ToolOutput:
        """Return one macro series."""
        ...

    async def place_leg(self, leg: dict[str, Any], client_order_id: str) -> ToolOutput:
        """Place one order leg."""
        ...
