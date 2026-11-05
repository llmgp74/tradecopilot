"""Deterministic order ticket checks.

The check simulates the legs in order, sells before buys, so a buy funded by a
sell in the same ticket is judged on the cash that sell provides.
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

MAX_LEG_QTY = 100_000.0
_EPSILON = 1e-9
_NEW_YORK = ZoneInfo("America/New_York")


def _violation(
    code: str, message: str, leg_index: int, value: Any = None
) -> dict[str, Any]:
    return {"code": code, "message": message, "leg_index": leg_index, "value": value}


def _ordered(legs: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
    indexed = list(enumerate(legs))
    sells = [item for item in indexed if item[1].get("side") == "sell"]
    buys = [item for item in indexed if item[1].get("side") != "sell"]
    return [*sells, *buys]


def _market_open(now: datetime) -> bool:
    local = now.astimezone(_NEW_YORK)
    if local.weekday() >= 5:
        return False
    minutes = local.hour * 60 + local.minute
    return 9 * 60 + 30 <= minutes < 16 * 60


def check_ticket(
    legs: list[dict[str, Any]],
    profile: dict[str, Any],
    account: dict[str, Any],
    prices: dict[str, float],
    sectors: dict[str, str | None],
    now: datetime,
    *,
    live: bool = False,
) -> list[dict[str, Any]]:
    """Check a ticket against the profile and account.

    Args:
        legs: Legs with ``ticker``, ``side``, and ``qty``.
        profile: Ground-truth profile, including ``position_cap_pct``,
            ``sector_exclusions``, and ``execution``.
        account: Account snapshot with ``equity``, ``buying_power``, and
            ``positions``. Each position has ``ticker``, ``qty``, and
            ``market_value``.
        prices: Price per ticker, from quotes fetched for this ticket.
        sectors: Sector per ticker, or ``None`` when unknown.
        now: Wall clock, used only when ``live`` is true.
        live: Whether the app is talking to a live broker. Evaluation runs pass
            false and skip the market-hours rule.

    Returns:
        Violations, each with a code, message, leg index, and value. An empty
        list means the ticket passes.
    """
    violations: list[dict[str, Any]] = []
    if not legs:
        return [_violation("empty", "The ticket has no legs.", 0)]

    holdings: dict[str, float] = {}
    position_values: dict[str, float] = {}
    for position in account.get("positions", []):
        ticker = str(position.get("ticker", "")).upper()
        qty = float(position.get("qty", 0))
        holdings[ticker] = qty
        if qty:
            position_values[ticker] = float(position.get("market_value", 0)) / qty

    for ticker, quote_price in prices.items():
        position_values[ticker.upper()] = float(quote_price)

    equity = float(account.get("equity", 0))
    available = float(account.get("buying_power", 0))
    execution = profile.get("execution", {})
    exclusions = set(profile.get("sector_exclusions", []))
    cap_pct = float(profile.get("position_cap_pct", 100))

    if live and legs and not _market_open(now):
        violations.append(_violation("market_closed", "The market is closed.", 0))

    for index, leg in _ordered(legs):
        ticker = str(leg.get("ticker", "")).upper()
        side = leg.get("side")
        qty = float(leg.get("qty", 0))
        price = position_values.get(ticker)

        if qty <= 0 or qty > MAX_LEG_QTY:
            violations.append(
                _violation(
                    "extreme_qty", "Quantity is outside the allowed range.", index, qty
                )
            )
            continue
        if qty % 1 and not account.get("fractional", False):
            violations.append(
                _violation(
                    "fractional_qty", "Fractional shares are not allowed.", index, qty
                )
            )
        if price is None:
            violations.append(
                _violation("missing_price", "No quote for this ticker.", index, ticker)
            )
            continue

        notional = qty * price
        held = holdings.get(ticker, 0.0)
        if side == "sell":
            if qty > held + _EPSILON:
                violations.append(
                    _violation(
                        "oversell", "The sell exceeds the held quantity.", index, qty
                    )
                )
                continue
            holdings[ticker] = held - qty
            available += notional
            continue

        sector = sectors.get(ticker)
        if exclusions and (sector is None or sector in exclusions):
            violations.append(
                _violation(
                    "sector_exclusion",
                    "The sector is excluded or unknown.",
                    index,
                    sector,
                )
            )
        holdings[ticker] = held + qty
        available -= notional

        resulting_value = holdings[ticker] * price
        if equity > 0 and resulting_value / equity * 100 > cap_pct + _EPSILON:
            violations.append(
                _violation(
                    "position_cap",
                    "The position would exceed the cap.",
                    index,
                    resulting_value / equity * 100,
                )
            )

    if available < -_EPSILON:
        violations.append(
            _violation(
                "insufficient_buying_power",
                "The buys exceed available cash after the sells.",
                len(legs) - 1,
                available,
            )
        )

    buy_notional = sum(
        float(leg.get("qty", 0))
        * position_values.get(str(leg.get("ticker", "")).upper(), 0)
        for leg in legs
        if leg.get("side") == "buy"
    )
    if execution.get("autonomous") and buy_notional > float(
        execution.get("max_order_notional", 0)
    ):
        violations.append(
            _violation(
                "notional_cap",
                "The ticket exceeds the autonomous notional cap.",
                0,
                buy_notional,
            )
        )
    return violations
