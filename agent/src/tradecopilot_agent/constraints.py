"""Deterministic order ticket checks.

The check simulates the legs in order, sells before buys, so a buy funded by a
sell in the same ticket is judged on the cash that sell provides.
"""

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

MAX_LEG_QTY = 100_000.0
_EPSILON = 1e-9
_NEW_YORK = ZoneInfo("America/New_York")


def _violation(
    code: str, message: str, leg_index: int, value: Any = None
) -> dict[str, Any]:
    return {"code": code, "message": message, "leg_index": leg_index, "value": value}


def _leg_price(leg: dict[str, Any]) -> float | None:
    """Return the price the model attached to a leg, when it set one.

    Args:
        leg: Leg with an optional ``entry_price``.

    Returns:
        The positive price, or ``None`` when the leg carries no price.
    """
    value = leg.get("entry_price")
    if isinstance(value, int | float) and value > 0:
        return float(value)
    return None


def _checked_price(
    side: Any, limit_price: float | None, quote: float | None
) -> float | None:
    """Return the price used to size and check a leg.

    A buy is checked at the higher of its limit and the quote, so a limit far
    below the market cannot shrink the position under the cap. A sell is
    checked at the lower, so its proceeds are not overstated.

    Args:
        side: Leg side, buy or sell.
        limit_price: The leg's own price, or ``None``.
        quote: The quote price, or ``None``.

    Returns:
        The checked price, or ``None`` when neither price is known.
    """
    if limit_price is not None and quote is not None:
        return max(limit_price, quote) if side == "buy" else min(limit_price, quote)
    if limit_price is not None:
        return limit_price
    return quote


def _ordered(legs: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
    indexed = list(enumerate(legs))
    sells = [item for item in indexed if item[1].get("side") == "sell"]
    buys = [item for item in indexed if item[1].get("side") != "sell"]
    return [*sells, *buys]


def _next_open(next_open: str | None) -> datetime | None:
    """Parse the broker's next regular open in New York time.

    Args:
        next_open: RFC 3339 timestamp, when the broker supplies one.

    Returns:
        The parsed instant, or None when missing, naive, or malformed.
    """
    if not next_open:
        return None
    try:
        upcoming = datetime.fromisoformat(next_open)
    except ValueError:
        return None
    if upcoming.tzinfo is None or upcoming.utcoffset() is None:
        return None
    return upcoming.astimezone(_NEW_YORK)


def session_open(now: datetime, is_open: bool, next_open: str | None) -> bool:
    """Resolve the effective session state from the broker clock.

    Alpaca reports the regular session only, so a closed clock still leaves its
    24/5 schedule open: 04:00 to 20:00 on weekdays, plus overnight from 20:00
    to 04:00 and Sunday from 20:00. Overnight needs the next regular open to
    prove a session exists: before 04:00 it must fall on the same New York
    date, and from 20:00 it must fall on the next day. That closes the weekend
    and the evenings before market holidays.

    Args:
        now: Wall clock in any time zone.
        is_open: The broker's regular-session state.
        next_open: RFC 3339 time of the next regular open, when supplied.

    Returns:
        True when orders may be placed now.
    """
    if is_open:
        return True
    local = now.astimezone(_NEW_YORK)
    minutes = local.hour * 60 + local.minute
    upcoming = _next_open(next_open)
    if local.weekday() == 5:
        return False
    if local.weekday() == 6 and minutes < 20 * 60:
        return False
    if 4 * 60 <= minutes < 20 * 60:
        if minutes < 9 * 60 + 30:
            return upcoming is not None and upcoming.date() == local.date()
        return True
    if minutes < 4 * 60:
        return upcoming is not None and upcoming.date() == local.date()
    tomorrow = local.date() + timedelta(days=1)
    return upcoming is not None and upcoming.date() == tomorrow


def regular_hours(now: datetime) -> bool:
    """Whether the regular session is open.

    Args:
        now: Wall clock in any time zone.

    Returns:
        True on weekdays from 09:30 up to, not including, 16:00 New York time.
        Alpaca accepts market orders only in this window.
    """
    local = now.astimezone(_NEW_YORK)
    if local.weekday() >= 5:
        return False
    minutes = local.hour * 60 + local.minute
    return 9 * 60 + 30 <= minutes < 16 * 60


def _market_open(now: datetime) -> bool:
    """Whether Alpaca's 24/5 schedule is open, without a broker clock.

    Args:
        now: Wall clock in any time zone.

    Returns:
        True from Sunday 20:00 through Friday 20:00 New York time. Holiday
        evenings cannot be detected here; the broker rejects them.
    """
    local = now.astimezone(_NEW_YORK)
    minutes = local.hour * 60 + local.minute
    if local.weekday() == 5:
        return False
    if local.weekday() == 6 and minutes < 20 * 60:
        return False
    if 4 * 60 <= minutes < 20 * 60:
        return True
    if minutes < 4 * 60:
        return True
    return local.weekday() != 4


def check_ticket(
    legs: list[dict[str, Any]],
    profile: dict[str, Any],
    account: dict[str, Any],
    prices: dict[str, float],
    sectors: dict[str, str | None],
    now: datetime,
    *,
    live: bool = False,
    market_open: bool | None = None,
    next_open: str | None = None,
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
        market_open: The broker's session state. When None the local extended
            window decides.
        next_open: RFC 3339 time of the next session open, shown when closed.

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

    open_now = _market_open(now) if market_open is None else market_open
    if live and legs and not open_now:
        message = "The market is closed."
        if next_open:
            message = f"The market is closed. It opens at {next_open}."
        violations.append(_violation("market_closed", message, 0, next_open))

    for index, leg in _ordered(legs):
        ticker = str(leg.get("ticker", "")).upper()
        side = leg.get("side")
        qty = float(leg.get("qty", 0))
        price = _checked_price(side, _leg_price(leg), position_values.get(ticker))

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
        * (
            _checked_price(
                "buy",
                _leg_price(leg),
                position_values.get(str(leg.get("ticker", "")).upper(), 0),
            )
            or 0
        )
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
