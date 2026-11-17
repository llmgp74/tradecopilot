"""Alpaca account, market data, and order placement."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from tradecopilot_agent.data import MarketClock
from tradecopilot_agent.models import AppSettings
from tradecopilot_agent.portfolio import (
    PortfolioUnavailable,
    fetch_portfolio,
    trading_base_url,
)
from tradecopilot_agent.sources.common import record
from tradecopilot_agent.sources.http import fetch_json, post_json
from tradecopilot_agent.state import ToolOutput

DATA_URL = "https://data.alpaca.markets"
STALE_AFTER_SECONDS = 15 * 60
_NEW_YORK = ZoneInfo("America/New_York")
_REGULAR_OPEN_MINUTES = 9 * 60 + 30
_REGULAR_CLOSE_MINUTES = 16 * 60


def _in_regular_hours(now: datetime) -> bool:
    """Whether the regular session is running, 09:30-16:00 New York time.

    Args:
        now: Wall clock in any time zone.

    Returns:
        True on weekdays inside the regular session.
    """
    local = now.astimezone(_NEW_YORK)
    if local.weekday() >= 5:
        return False
    minutes = local.hour * 60 + local.minute
    return _REGULAR_OPEN_MINUTES <= minutes < _REGULAR_CLOSE_MINUTES


class AlpacaSource:
    """Free-tier Alpaca adapter. Recent quotes are IEX and delayed."""

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
        """Return the Alpaca capabilities that are configured."""
        current = self.settings()
        if not (current.alpaca_api_key and current.alpaca_api_secret):
            return set()
        return {"alpaca", "order_execution"}

    def _headers(self) -> dict[str, str]:
        current = self.settings()
        return {
            "APCA-API-KEY-ID": current.alpaca_api_key,
            "APCA-API-SECRET-KEY": current.alpaca_api_secret,
            "accept": "application/json",
        }

    async def quote(self, ticker: str) -> ToolOutput:
        """Return the latest IEX trade price."""
        url = f"{DATA_URL}/v2/stocks/{ticker}/snapshot"
        try:
            data = await fetch_json(
                url, headers=self._headers(), params={"feed": "iex"}, client=self.client
            )
        except (httpx.HTTPError, ValueError) as exc:
            return ToolOutput(summary=f"Alpaca quote failed: {exc}", error="http")
        trade = data.get("latestTrade") or {}
        price = trade.get("p")
        if not isinstance(price, int | float):
            return ToolOutput(summary=f"No price for {ticker}.", error="missing")
        published = trade.get("t")
        stale = _is_stale(published)
        payload = {
            "kind": "quote",
            "ticker": ticker,
            "price": float(price),
            "as_of": published,
        }
        return ToolOutput(
            summary=f"{ticker} last {price} (IEX, may be delayed)",
            evidence=[
                record(
                    "get_quote",
                    {"ticker": ticker},
                    "alpaca",
                    payload,
                    published_at=published,
                    stale=stale,
                )
            ],
        )

    async def bars(self, ticker: str, period: str, interval: str) -> ToolOutput:
        """Return recent bars."""
        timeframe = "1Day" if interval.startswith("1d") else "1Hour"
        url = f"{DATA_URL}/v2/stocks/{ticker}/bars"
        now = datetime.now(tz=UTC)
        lookback = 120 if timeframe == "1Day" else 7
        params = {
            "timeframe": timeframe,
            "start": (now - timedelta(days=lookback)).date().isoformat(),
            "end": now.date().isoformat(),
            "limit": 60,
            "feed": "iex",
        }
        try:
            data = await fetch_json(
                url, headers=self._headers(), params=params, client=self.client
            )
        except (httpx.HTTPError, ValueError) as exc:
            return ToolOutput(summary=f"Alpaca bars failed: {exc}", error="http")
        bars = data.get("bars") or []
        payload = {"kind": "bars", "ticker": ticker, "bars": bars}
        return ToolOutput(
            summary=f"{len(bars)} bars for {ticker}",
            evidence=[
                record(
                    "get_bars",
                    {"ticker": ticker, "period": period, "interval": interval},
                    "alpaca",
                    payload,
                )
            ],
        )

    async def portfolio(self) -> ToolOutput:
        """Return the account and its positions."""
        return await self._account("get_portfolio")

    async def positions(self) -> ToolOutput:
        """Return the open positions."""
        return await self._account("get_positions")

    async def _account(self, tool: str) -> ToolOutput:
        try:
            snapshot = await fetch_portfolio(self.settings(), "1M")
        except PortfolioUnavailable as exc:
            return ToolOutput(summary=f"Alpaca account failed: {exc}", error="http")
        payload = {
            "kind": "account",
            "paper": snapshot.paper,
            "equity": snapshot.account.equity,
            "cash": snapshot.account.cash,
            "buying_power": snapshot.account.buying_power,
            "positions": [
                {
                    "ticker": position.ticker,
                    "qty": position.qty,
                    "market_value": position.market_value,
                }
                for position in snapshot.positions
            ],
        }
        environment = "Paper account" if snapshot.paper else "Live account"
        return ToolOutput(
            summary=(
                f"{environment}. Equity {snapshot.account.equity}, "
                f"cash {snapshot.account.cash}, "
                f"buying power {snapshot.account.buying_power}"
            ),
            evidence=[record(tool, {}, "alpaca", payload)],
        )

    async def clock(self) -> MarketClock | None:
        """Return Alpaca's session state, or None when it is unavailable."""
        base = trading_base_url(self.settings().alpaca_base_url)
        try:
            data = await fetch_json(
                f"{base}/v2/clock", headers=self._headers(), client=self.client
            )
        except (httpx.HTTPError, ValueError):
            return None
        if not isinstance(data, dict) or not isinstance(data.get("is_open"), bool):
            return None
        next_open = data.get("next_open")
        return MarketClock(
            is_open=data["is_open"],
            next_open=next_open if isinstance(next_open, str) else None,
        )

    async def place_leg(
        self,
        leg: dict[str, Any],
        client_order_id: str,
        now: datetime | None = None,
    ) -> ToolOutput:
        """Place one order on the configured Alpaca account.

        Outside the regular session Alpaca accepts only limit orders flagged
        for extended hours, so the ticket's entry price becomes the limit.

        Args:
            leg: Ticket leg with ticker, side, qty, and entry_price.
            client_order_id: Idempotency key for the order.
            now: Wall clock, injected by tests.

        Returns:
            The order result.
        """
        current = self.settings()
        moment = now if now is not None else datetime.now(tz=UTC)
        body: dict[str, Any] = {
            "symbol": leg["ticker"],
            "qty": str(leg["qty"]),
            "side": leg["side"],
            "type": "market",
            "time_in_force": "day",
            "client_order_id": client_order_id,
        }
        entry_price = leg.get("entry_price")
        if not _in_regular_hours(moment) and isinstance(entry_price, int | float):
            body["type"] = "limit"
            body["limit_price"] = f"{float(entry_price):.2f}"
            body["extended_hours"] = True
        try:
            data = await post_json(
                f"{trading_base_url(current.alpaca_base_url)}/v2/orders",
                headers={**self._headers(), "Content-Type": "application/json"},
                body=body,
                client=self.client,
            )
        except (httpx.HTTPError, ValueError) as exc:
            return ToolOutput(summary=f"Order failed: {exc}", error="http")
        payload = {
            "kind": "order",
            "status": str(data.get("status", "submitted")),
            "fill_price": data.get("filled_avg_price"),
            "fill_at": data.get("filled_at"),
        }
        return ToolOutput(
            summary=f"Order {payload['status']} for {leg['ticker']}",
            evidence=[
                record(
                    "place_leg", leg, "alpaca", payload, published_at=payload["fill_at"]
                )
            ],
        )


def _is_stale(published_at: str | None) -> bool:
    if not published_at:
        return True
    try:
        stamp = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    return (datetime.now(tz=UTC) - stamp.astimezone(UTC)).total_seconds() > (
        STALE_AFTER_SECONDS
    )
