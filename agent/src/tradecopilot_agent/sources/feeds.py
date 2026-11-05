"""FMP fundamentals, Finnhub news, and FRED macro series."""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import httpx

from tradecopilot_agent.models import AppSettings
from tradecopilot_agent.sources.common import record
from tradecopilot_agent.sources.http import fetch_json
from tradecopilot_agent.state import ToolOutput

FMP_URL = "https://financialmodelingprep.com/stable/profile"
FINNHUB_URL = "https://finnhub.io/api/v1/company-news"
FRED_URL = "https://api.stlouisfed.org/fred/series/observations"


class FmpSource:
    """Fundamentals only. The free plan allows 250 calls a day."""

    def __init__(
        self,
        settings: Callable[[], AppSettings],
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Bind the adapter to the effective settings.

        Args:
            settings: Callable returning the current settings.
            client: Injected HTTP client for tests.
        """
        self.settings = settings
        self.client = client
        self._cache: dict[tuple[str, date], ToolOutput] = {}

    def capabilities(self) -> set[str]:
        """Return FMP when a key is configured."""
        return {"fmp"} if self.settings().fmp_api_key else set()

    async def fundamentals(self, ticker: str) -> ToolOutput:
        """Return profile and sector, cached for the calendar day."""
        today = datetime.now(tz=UTC).date()
        cached = self._cache.get((ticker, today))
        if cached is not None:
            return cached
        try:
            data = await fetch_json(
                FMP_URL,
                params={"symbol": ticker, "apikey": self.settings().fmp_api_key},
                client=self.client,
            )
        except (httpx.HTTPError, ValueError) as exc:
            return ToolOutput(summary=f"FMP failed: {exc}", error="http")
        item = data[0] if isinstance(data, list) and data else {}
        if not isinstance(item, dict) or not item:
            return ToolOutput(summary=f"No profile for {ticker}.", error="missing")
        payload = {
            "kind": "fundamentals",
            "ticker": ticker,
            "sector": item.get("sector"),
            "industry": item.get("industry"),
            "market_cap": item.get("marketCap"),
        }
        output = ToolOutput(
            summary=f"{ticker} sector {payload['sector']}",
            evidence=[record("get_fundamentals", {"ticker": ticker}, "fmp", payload)],
        )
        self._cache[(ticker, today)] = output
        return output


class FinnhubSource:
    """Company news. The free plan covers North American companies."""

    def __init__(
        self,
        settings: Callable[[], AppSettings],
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Bind the adapter to the effective settings.

        Args:
            settings: Callable returning the current settings.
            client: Injected HTTP client for tests.
        """
        self.settings = settings
        self.client = client

    def capabilities(self) -> set[str]:
        """Return Finnhub when a key is configured."""
        return {"finnhub"} if self.settings().finnhub_api_key else set()

    async def news(self, ticker: str, limit: int = 10) -> ToolOutput:
        """Return recent company news."""
        today = datetime.now(tz=UTC).date()
        try:
            data = await fetch_json(
                FINNHUB_URL,
                params={
                    "symbol": ticker,
                    "from": (today - timedelta(days=30)).isoformat(),
                    "to": today.isoformat(),
                    "token": self.settings().finnhub_api_key,
                },
                client=self.client,
            )
        except (httpx.HTTPError, ValueError) as exc:
            return ToolOutput(summary=f"Finnhub failed: {exc}", error="http")
        items = data if isinstance(data, list) else []
        records = []
        for item in items[:limit]:
            stamp = item.get("datetime")
            published = (
                datetime.fromtimestamp(int(stamp), tz=UTC).isoformat()
                if isinstance(stamp, int | float)
                else None
            )
            payload = {
                "kind": "news",
                "ticker": ticker,
                "date": published[:10] if published else None,
                "headline": item.get("headline"),
            }
            records.append(
                record(
                    "get_news",
                    {"ticker": ticker, "limit": limit},
                    "finnhub",
                    payload,
                    url=item.get("url"),
                    published_at=published,
                )
            )
        return ToolOutput(
            summary=f"{len(records)} news items for {ticker}", evidence=records
        )


class FredSource:
    """Macro series."""

    def __init__(
        self,
        settings: Callable[[], AppSettings],
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Bind the adapter to the effective settings.

        Args:
            settings: Callable returning the current settings.
            client: Injected HTTP client for tests.
        """
        self.settings = settings
        self.client = client

    def capabilities(self) -> set[str]:
        """Return FRED when a key is configured."""
        return {"fred"} if self.settings().fred_api_key else set()

    async def macro(self, series: str, period: str) -> ToolOutput:
        """Return the latest observations for a series."""
        days = {"1m": 30, "3m": 90, "1y": 365}.get(period.lower(), 365)
        start = (datetime.now(tz=UTC).date() - timedelta(days=days)).isoformat()
        try:
            data = await fetch_json(
                FRED_URL,
                params={
                    "series_id": series,
                    "api_key": self.settings().fred_api_key,
                    "file_type": "json",
                    "sort_order": "desc",
                    "observation_start": start,
                },
                client=self.client,
            )
        except (httpx.HTTPError, ValueError) as exc:
            return ToolOutput(summary=f"FRED failed: {exc}", error="http")
        observations = [
            item
            for item in (data.get("observations") or [])
            if str(item.get("value", ".")) != "."
        ]
        if not observations:
            return ToolOutput(summary=f"No observations for {series}.", error="missing")
        latest = observations[0]
        payload = {
            "kind": "macro",
            "series": series,
            "date": latest.get("date"),
            "value": latest.get("value"),
        }
        return ToolOutput(
            summary=f"{series} {latest.get('date')}: {latest.get('value')}",
            evidence=[
                record(
                    "get_macro",
                    {"series": series, "period": period},
                    "fred",
                    payload,
                    published_at=latest.get("date"),
                )
            ],
        )
