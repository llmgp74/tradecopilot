"""Portfolio snapshots from the Alpaca trading API."""

from datetime import UTC, datetime
from typing import Literal

import httpx

from tradecopilot_agent.config import Settings
from tradecopilot_agent.models import (
    Account,
    DayPnl,
    EquityPoint,
    Portfolio,
    Position,
)
from tradecopilot_agent.store import now_iso

_RANGES: dict[str, tuple[str, str]] = {
    "1D": ("1D", "5Min"),
    "1W": ("1W", "30Min"),
    "1M": ("1M", "1Day"),
    "3M": ("3M", "1Day"),
    "1Y": ("1Y", "1Day"),
    "ALL": ("all", "1Day"),
}


class PortfolioUnavailable(Exception):
    """The broker is unconfigured, unreachable, or returned unusable data."""


async def fetch_portfolio(settings: Settings, range_: str) -> Portfolio:
    """Fetch and normalize the current portfolio.

    Args:
        settings: Broker credentials and base URL.
        range_: Equity curve window, one of ``1D``, ``1W``, ``1M``, ``3M``,
            ``1Y``, ``ALL``. Unknown values fall back to ``1M``.

    Returns:
        The normalized portfolio.

    Raises:
        PortfolioUnavailable: If credentials are missing or the broker call
            fails.
    """
    if not settings.alpaca_api_key or not settings.alpaca_api_secret:
        raise PortfolioUnavailable("Broker is not configured.")

    period, timeframe = _RANGES.get(range_, _RANGES["1M"])
    headers = {
        "APCA-API-KEY-ID": settings.alpaca_api_key,
        "APCA-API-SECRET-KEY": settings.alpaca_api_secret,
    }
    try:
        async with httpx.AsyncClient(
            base_url=settings.alpaca_base_url,
            headers=headers,
            timeout=10.0,
        ) as client:
            account_response = await client.get("/v2/account")
            positions_response = await client.get("/v2/positions")
            history_response = await client.get(
                "/v2/account/portfolio/history",
                params={"period": period, "timeframe": timeframe},
            )
            for response in (
                account_response,
                positions_response,
                history_response,
            ):
                response.raise_for_status()
            account = account_response.json()
            raw_positions = positions_response.json()
            history = history_response.json()
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise PortfolioUnavailable("Portfolio is unavailable.") from exc

    try:
        return _portfolio(settings, account, raw_positions, history)
    except (KeyError, TypeError, ValueError) as exc:
        raise PortfolioUnavailable("Portfolio is unavailable.") from exc


def _portfolio(
    settings: Settings,
    account: dict[str, object],
    raw_positions: list[dict[str, object]],
    history: dict[str, object],
) -> Portfolio:
    equity = float(str(account["equity"]))
    last_equity = float(str(account["last_equity"]))
    pnl = equity - last_equity
    pnl_pct = pnl / last_equity * 100.0 if last_equity else 0.0

    positions = [
        _position(raw, equity) for raw in raw_positions if isinstance(raw, dict)
    ]
    timestamps = history.get("timestamp")
    equities = history.get("equity")
    curve: list[EquityPoint] = []
    if isinstance(timestamps, list) and isinstance(equities, list):
        for timestamp, value in zip(timestamps, equities, strict=False):
            if value is None:
                continue
            curve.append(
                EquityPoint(
                    t=_iso_time(int(str(timestamp))),
                    equity=float(str(value)),
                )
            )

    return Portfolio(
        as_of=now_iso(),
        paper="paper-api" in settings.alpaca_base_url,
        account=Account(
            currency=str(account["currency"]),
            equity=equity,
            cash=float(str(account["cash"])),
            buying_power=float(str(account["buying_power"])),
            long_market_value=float(str(account["long_market_value"])),
        ),
        day=DayPnl(pnl=pnl, pnl_pct=pnl_pct),
        positions=positions,
        equity_curve=curve,
    )


def _position(raw: dict[str, object], equity: float) -> Position:
    market_value = float(str(raw["market_value"]))
    side: Literal["long", "short"] = (
        "short" if str(raw.get("side")) == "short" else "long"
    )
    return Position(
        ticker=str(raw["symbol"]),
        side=side,
        sector=None,
        qty=abs(float(str(raw["qty"]))),
        avg_entry_price=float(str(raw["avg_entry_price"])),
        current_price=float(str(raw["current_price"])),
        market_value=market_value,
        unrealized_pl=float(str(raw["unrealized_pl"])),
        unrealized_pl_pct=float(str(raw["unrealized_plpc"])) * 100.0,
        weight_pct=market_value / equity * 100.0 if equity else 0.0,
    )


def _iso_time(epoch_seconds: int) -> str:
    return (
        datetime.fromtimestamp(epoch_seconds, tz=UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
