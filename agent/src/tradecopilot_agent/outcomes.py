"""Decision outcomes computed from locally recorded prices.

The journal stores what the user decided. This module measures what happened
afterwards using only the observations the app already recorded, so a journal
read never calls the broker.

A decision's return is the price change from its entry to the nearest
observation at or before its horizon end. An observation more than
``TOLERANCE_DAYS`` before the end is not used: a number that far from the
stated horizon would describe a different holding period.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any

from tradecopilot_agent.store import now_iso

HORIZON_DAYS: dict[str, int] = {
    "intraday": 1,
    "days": 5,
    "weeks": 28,
    "months": 90,
}
TOLERANCE_DAYS = 5
HISTORY_DAYS = 200
BENCHMARK = "SPY"

Observations = dict[str, list[tuple[str, float]]]


def _parse_date(value: Any) -> date | None:
    """Read the date part of an ISO timestamp without raising.

    Args:
        value: Timestamp, date, or unusable value.

    Returns:
        The date, or ``None`` when the value cannot be read.
    """
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _pick_price(
    rows: list[tuple[str, float]], start: date, end: date
) -> tuple[date, float] | None:
    """Return the latest usable observation inside an inclusive window.

    Args:
        rows: ``(ISO date, price)`` pairs for one ticker.
        start: Inclusive lower date.
        end: Inclusive upper date.

    Returns:
        The chosen date and price, or ``None`` when nothing falls inside.
    """
    chosen: tuple[date, float] | None = None
    for raw_date, raw_price in rows:
        observed = _parse_date(raw_date)
        if observed is None or observed < start or observed > end:
            continue
        if chosen is None or observed > chosen[0]:
            chosen = (observed, float(raw_price))
    return chosen


def _entry(
    leg: dict[str, Any], decision_date: date | None, decision_at: str
) -> tuple[float, date, str] | None:
    """Resolve a leg's entry price, entry date, and entry timestamp.

    Args:
        leg: Journal leg snapshot.
        decision_date: Proposal date, used when the leg did not fill.
        decision_at: Proposal timestamp, used when the leg did not fill.

    Returns:
        ``(price, date, timestamp)``, or ``None`` when the leg has no usable
        entry.
    """
    fill_price = leg.get("fill_price")
    if isinstance(fill_price, int | float) and fill_price > 0:
        entry_date = _parse_date(leg.get("fill_at")) or decision_date
        if entry_date is None:
            return None
        return float(fill_price), entry_date, str(leg.get("fill_at") or "")

    raw_entry = leg.get("entry_price")
    if isinstance(raw_entry, int | float) and raw_entry > 0:
        price = float(raw_entry)
    else:
        qty = float(leg.get("qty") or 0)
        notional = float(leg.get("notional") or 0)
        price = notional / qty if qty else 0.0
    if price <= 0 or decision_date is None:
        return None
    return price, decision_date, decision_at


def _weighted(values: list[tuple[float | None, float]]) -> float | None:
    """Return a notional-weighted mean, ignoring missing values.

    Args:
        values: ``(value, weight)`` pairs. A missing value is skipped.

    Returns:
        The weighted mean, or ``None`` when every value is missing.
    """
    present = [(value, weight) for value, weight in values if value is not None]
    if not present:
        return None
    total = sum(weight for _, weight in present)
    if total <= 0:
        return sum(value for value, _ in present) / len(present)
    return sum(float(value) * weight for value, weight in present) / total


def compute_outcome(
    decision: dict[str, Any],
    observations: Observations,
    today: date | None = None,
) -> dict[str, Any] | None:
    """Measure a decision against the locally recorded prices.

    Args:
        decision: Journal row with legs, horizon, and decision time.
        observations: Ticker to ``(ISO date, price)`` pairs.
        today: Clock override for tests. Defaults to the current UTC date.

    Returns:
        A ``JournalOutcome`` shaped dict, or ``None`` when no leg can be
        measured yet.
    """
    today = today or datetime.now(tz=UTC).date()
    horizon = str(decision.get("horizon") or "weeks")
    horizon_days = HORIZON_DAYS.get(horizon, HORIZON_DAYS["weeks"])
    decision_at = str(decision.get("created_at") or "")
    decision_date = _parse_date(decision_at)
    spy_rows = observations.get(BENCHMARK, [])
    tolerance = timedelta(days=TOLERANCE_DAYS)
    legs = [leg for leg in decision.get("legs", []) if isinstance(leg, dict)]

    priced: list[dict[str, Any]] = []
    for leg in legs:
        entry = _entry(leg, decision_date, decision_at)
        ticker = str(leg.get("ticker") or "").strip().upper()
        if entry is None or not ticker:
            continue
        entry_price, entry_date, entry_at = entry
        end = entry_date + timedelta(days=horizon_days)
        if end > today:
            continue
        lower = max(entry_date, end - tolerance)
        exit_price = _pick_price(observations.get(ticker, []), lower, end)
        if exit_price is None:
            continue
        exit_date, exit_value = exit_price
        move = (exit_value - entry_price) / entry_price
        if str(leg.get("side")) == "sell":
            move = -move
        return_pct = move * 100

        benchmark: float | None = None
        spy_start = _pick_price(spy_rows, entry_date - tolerance, entry_date)
        spy_exit = _pick_price(spy_rows, lower, end)
        if spy_start is not None and spy_exit is not None and spy_start[1] > 0:
            benchmark = (spy_exit[1] - spy_start[1]) / spy_start[1] * 100
        alpha = return_pct - benchmark if benchmark is not None else None

        priced.append(
            {
                "ticker": ticker,
                "entry_price": entry_price,
                "entry_date": entry_date,
                "entry_at": entry_at,
                "return_pct": return_pct,
                "benchmark": benchmark,
                "alpha_pct": alpha,
                "observed_at": exit_date.isoformat(),
                "counterfactual": leg.get("fill_price") is None,
                "weight": abs(float(leg.get("notional") or 0)),
            }
        )

    if not priced:
        return None

    aggregate_entry = _weighted(
        [(item["entry_price"], item["weight"]) for item in priced]
    )
    aggregate_return = _weighted(
        [(item["return_pct"], item["weight"]) for item in priced]
    )
    aggregate_benchmark = _weighted(
        [(item["benchmark"], item["weight"]) for item in priced]
    )
    aggregate_alpha = _weighted(
        [(item["alpha_pct"], item["weight"]) for item in priced]
    )
    earliest = min(priced, key=lambda item: item["entry_date"])

    return {
        "counterfactual": any(leg.get("fill_price") is None for leg in legs),
        "entry_price": aggregate_entry,
        "entry_at": earliest["entry_at"],
        "horizon": horizon,
        "return_pct": aggregate_return,
        "benchmark": BENCHMARK,
        "benchmark_return_pct": aggregate_benchmark,
        "alpha_pct": aggregate_alpha,
        "computed_at": now_iso(),
        "observed_at": max(item["observed_at"] for item in priced),
        "partial": len(priced) < len(legs),
        "legs": [
            {
                "ticker": item["ticker"],
                "entry_price": item["entry_price"],
                "return_pct": item["return_pct"],
                "alpha_pct": item["alpha_pct"],
                "observed_at": item["observed_at"],
                "counterfactual": item["counterfactual"],
            }
            for item in priced
        ],
    }


def attach_outcomes(
    rows: list[dict[str, Any]], store: Any, today: date | None = None
) -> list[dict[str, Any]]:
    """Attach computed outcomes to journal rows.

    Args:
        rows: Journal rows from ``Store.list_journal``.
        store: Store exposing ``observations_between``.
        today: Clock override for tests. Defaults to the current UTC date.

    Returns:
        The same rows, each with an ``outcome`` value.
    """
    today = today or datetime.now(tz=UTC).date()
    tickers = {BENCHMARK}
    for row in rows:
        for leg in row.get("legs", []) or []:
            ticker = str(leg.get("ticker") or "").strip().upper()
            if ticker:
                tickers.add(ticker)

    records = store.observations_between(
        tickers, today - timedelta(days=HISTORY_DAYS), today
    )
    observations: Observations = {}
    for record in records:
        observations.setdefault(str(record["ticker"]), []).append(
            (str(record["date"]), float(record["price"]))
        )
    for row in rows:
        row["outcome"] = compute_outcome(row, observations, today)
    return rows
