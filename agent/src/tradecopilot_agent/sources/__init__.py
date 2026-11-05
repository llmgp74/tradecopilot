"""Live data sources composed behind the ``DataSource`` protocol."""

from collections.abc import Callable
from typing import Any

import httpx

from tradecopilot_agent.models import AppSettings
from tradecopilot_agent.sources.alpaca import AlpacaSource
from tradecopilot_agent.sources.edgar import EdgarSource
from tradecopilot_agent.sources.feeds import FinnhubSource, FmpSource, FredSource
from tradecopilot_agent.state import ToolOutput

__all__ = ["LiveSource"]


class LiveSource:
    """Composes the provider adapters and reports their capabilities."""

    def __init__(
        self,
        settings: Callable[[], AppSettings],
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Create one adapter per provider.

        Args:
            settings: Callable returning the effective settings. It is read on
                every capability check and request, so a new key applies at once.
            client: Injected HTTP client for tests.
        """
        self.alpaca = AlpacaSource(settings, client)
        self.edgar = EdgarSource(settings, client)
        self.fmp = FmpSource(settings, client)
        self.finnhub = FinnhubSource(settings, client)
        self.fred = FredSource(settings, client)

    def capabilities(self) -> set[str]:
        """Return the union of the configured provider capabilities."""
        return (
            self.alpaca.capabilities()
            | self.edgar.capabilities()
            | self.fmp.capabilities()
            | self.finnhub.capabilities()
            | self.fred.capabilities()
        )

    async def quote(self, ticker: str) -> ToolOutput:
        """Return a quote from Alpaca."""
        return await self.alpaca.quote(ticker)

    async def bars(self, ticker: str, period: str, interval: str) -> ToolOutput:
        """Return bars from Alpaca."""
        return await self.alpaca.bars(ticker, period, interval)

    async def portfolio(self) -> ToolOutput:
        """Return the Alpaca account."""
        return await self.alpaca.portfolio()

    async def positions(self) -> ToolOutput:
        """Return the Alpaca positions."""
        return await self.alpaca.positions()

    async def fundamentals(self, ticker: str) -> ToolOutput:
        """Return fundamentals from FMP."""
        return await self.fmp.fundamentals(ticker)

    async def filings(self, ticker: str, limit: int = 10) -> ToolOutput:
        """Return filings from EDGAR."""
        return await self.edgar.filings(ticker, limit)

    async def xbrl_fact(
        self, ticker: str, tag: str, period: str, unit: str
    ) -> ToolOutput:
        """Return one XBRL fact from EDGAR."""
        return await self.edgar.xbrl_fact(ticker, tag, period, unit)

    async def news(self, ticker: str, limit: int = 10) -> ToolOutput:
        """Return news from Finnhub."""
        return await self.finnhub.news(ticker, limit)

    async def macro(self, series: str, period: str) -> ToolOutput:
        """Return a macro series from FRED."""
        return await self.fred.macro(series, period)

    async def place_leg(self, leg: dict[str, Any], client_order_id: str) -> ToolOutput:
        """Place one order leg through Alpaca."""
        return await self.alpaca.place_leg(leg, client_order_id)
