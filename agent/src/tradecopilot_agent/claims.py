"""Deterministic matching of claims against the evidence ledger."""

import re
from datetime import date, timedelta
from typing import Any, Literal

from tradecopilot_agent.state import Claim

NUMERIC_TOLERANCE = 0.005
NEWS_WINDOW = timedelta(days=1)


def _relative_difference(left: float, right: float) -> float:
    """Return the relative difference between two numbers.

    Args:
        left: First value.
        right: Second value.

    Returns:
        ``abs(left - right) / max(abs(left), abs(right))``, or 0 when both are 0.
    """
    scale = max(abs(left), abs(right))
    if scale == 0:
        return 0.0
    return abs(left - right) / scale


def _record_payload(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("payload")
    return payload if isinstance(payload, dict) else {}


def _period_matches(claim_period: str | None, payload: dict[str, Any]) -> bool:
    if claim_period is None:
        return True
    wanted = claim_period.strip().upper()
    for key in ("period", "fiscal_period"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip().upper() == wanted:
            return True
    return False


def _same_unit(claim_unit: str | None, payload_unit: Any) -> bool:
    if claim_unit is None:
        return True
    return isinstance(payload_unit, str) and payload_unit.lower() == claim_unit.lower()


def _verdict(
    claim: Claim,
    *,
    scope: str,
    verdict: str,
    records: list[dict[str, Any]] | None = None,
    matched_value: float | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    records = records or []
    return {
        "scope": scope,
        "text": claim.text,
        "verdict": verdict,
        "evidence_ids": [str(record.get("id")) for record in records],
        "source": records[0].get("source") if records else None,
        "matched_value": matched_value,
        "reason": reason,
    }


_ACCOUNT_FIELDS = (
    ("buying power", "buying_power"),
    ("equity", "equity"),
    ("cash", "cash"),
)

_POSITION_COUNT = re.compile(r"\bpositions\b")
"""A plural positions claim is a count. The singular "position" names one holding."""

_HOLDING = re.compile(r"\b(?:shares?|position|holding|worth|valued?|market value)\b")
"""Words that make a numeric claim about one holding rather than the account."""

_PERCENT_UNITS = frozenset({"%", "percent", "pct"})


def _against(
    claim: Claim, record: dict[str, Any], actual: float, scope: str
) -> dict[str, Any]:
    """Return a supported or contradicted verdict for one candidate value."""
    assert claim.value is not None
    verdict = (
        "supported"
        if _relative_difference(actual, claim.value) <= NUMERIC_TOLERANCE
        else "contradicted"
    )
    return _verdict(
        claim, scope=scope, verdict=verdict, records=[record], matched_value=actual
    )


def _holding_verdict(
    claim: Claim, record: dict[str, Any], payload: dict[str, Any], scope: str
) -> dict[str, Any] | None:
    """Match a share count or dollar value against one position.

    A holding claim can carry either its quantity or its market value, and the
    text may not say which. Both candidates are tested so an ambiguous claim is
    supported by whichever figure agrees; a contradiction reports the quantity
    unless the text names a value.
    """
    if claim.ticker is None or claim.value is None:
        return None
    text = claim.text.lower()
    if _HOLDING.search(text) is None:
        return None
    positions = payload.get("positions")
    if not isinstance(positions, list):
        return None
    wants_value = bool(re.search(r"\b(?:worth|valued?|market value)\b", text))
    unit = (claim.unit or "").strip().lower()
    if unit in {"share", "shares"}:
        keys = ("qty", "market_value")
    elif wants_value:
        keys = ("market_value", "qty")
    else:
        keys = ("qty", "market_value")
    for position in positions:
        if not isinstance(position, dict):
            continue
        if str(position.get("ticker", "")).upper() != claim.ticker.upper():
            continue
        fallback: float | None = None
        for key in keys:
            raw = position.get(key)
            if not isinstance(raw, int | float):
                continue
            candidate = float(raw)
            if fallback is None:
                fallback = candidate
            if _relative_difference(candidate, claim.value) <= NUMERIC_TOLERANCE:
                return _verdict(
                    claim,
                    scope=scope,
                    verdict="supported",
                    records=[record],
                    matched_value=candidate,
                )
        if fallback is not None:
            return _verdict(
                claim,
                scope=scope,
                verdict="contradicted",
                records=[record],
                matched_value=fallback,
            )
        return None
    return None


def _account_verdict(
    claim: Claim, evidence: dict[str, Any], scope: str
) -> dict[str, Any] | None:
    """Match a broker account figure against the Alpaca record."""
    if claim.value is None:
        return None
    text = claim.text.lower()
    counts_positions = (claim.unit or "").strip().lower() == "positions" or (
        _POSITION_COUNT.search(text) is not None
        and re.search(r"\b(?:worth|valued?|market value)\b", text) is None
    )
    field = (
        None
        if counts_positions
        else next(
            (
                name
                for needle, name in _ACCOUNT_FIELDS
                if re.search(rf"\b{needle}\b", text)
            ),
            None,
        )
    )
    for record in evidence.values():
        payload = _record_payload(record)
        if payload.get("kind") != "account":
            continue
        if counts_positions:
            positions = payload.get("positions")
            if not isinstance(positions, list):
                continue
            return _against(claim, record, float(len(positions)), scope)
        holding = _holding_verdict(claim, record, payload, scope)
        if holding is not None:
            return holding
        if field is not None:
            raw = payload.get(field)
            if not isinstance(raw, int | float):
                continue
            return _against(claim, record, float(raw), scope)
        scalars = [
            float(value)
            for key in ("equity", "cash", "buying_power")
            if isinstance((value := payload.get(key)), int | float)
        ]
        matches = [
            value
            for value in scalars
            if _relative_difference(value, claim.value) <= NUMERIC_TOLERANCE
        ]
        if matches:
            return _verdict(
                claim,
                scope=scope,
                verdict="supported",
                records=[record],
                matched_value=matches[0],
            )
    return None


def _quote_verdict(
    claim: Claim, evidence: dict[str, Any], scope: str
) -> dict[str, Any] | None:
    """Match a ticker price against the latest quote record."""
    if claim.ticker is None or claim.value is None:
        return None
    for record in evidence.values():
        payload = _record_payload(record)
        if payload.get("kind") != "quote":
            continue
        if payload.get("ticker") != claim.ticker:
            continue
        raw = payload.get("price")
        if not isinstance(raw, int | float):
            continue
        actual = float(raw)
        verdict = (
            "supported"
            if _relative_difference(actual, claim.value) <= NUMERIC_TOLERANCE
            else "contradicted"
        )
        return _verdict(
            claim,
            scope=scope,
            verdict=verdict,
            records=[record],
            matched_value=actual,
        )
    return None


def _numeric(claim: Claim, evidence: dict[str, Any], scope: str) -> dict[str, Any]:
    if claim.value is None:
        return _verdict(claim, scope=scope, verdict="unchecked", reason="no value")
    # A share of a total needs the total and the base to check, and the claim
    # carries only the percentage. Comparing it to a raw dollar figure reports
    # a contradiction that the evidence does not support.
    if (claim.unit or "").strip().lower() in _PERCENT_UNITS:
        return _verdict(
            claim, scope=scope, verdict="unchecked", reason="derived percentage"
        )
    # Account and quote figures are untagged by construction. A tagged claim is
    # a financial metric, so matching it against a balance or a price would
    # compare unrelated quantities and report a false contradiction.
    if claim.tag is None:
        account = _account_verdict(claim, evidence, scope)
        if account is not None:
            return account
        quote = _quote_verdict(claim, evidence, scope)
        if quote is not None:
            return quote
        return _verdict(claim, scope=scope, verdict="unchecked", reason="no XBRL tag")

    candidates = [
        record
        for record in evidence.values()
        if isinstance(record, dict)
        and _record_payload(record).get("kind") == "xbrl"
        and _record_payload(record).get("ticker") == claim.ticker
        and _record_payload(record).get("tag") == claim.tag
        and _same_unit(claim.unit, _record_payload(record).get("unit"))
        and _period_matches(claim.period, _record_payload(record))
    ]
    if claim.evidence_hint is not None:
        candidates = [
            record for record in candidates if record.get("id") == claim.evidence_hint
        ]
        if not candidates:
            return _verdict(
                claim, scope=scope, verdict="unchecked", reason="hint missing"
            )
    if not candidates:
        return _verdict(claim, scope=scope, verdict="unchecked", reason="no record")

    matched: list[tuple[dict[str, Any], float]] = []
    for record in candidates:
        value = _record_payload(record).get("value")
        if isinstance(value, int | float):
            matched.append((record, float(value)))
    if not matched:
        return _verdict(claim, scope=scope, verdict="unchecked", reason="no value")

    supporting = [
        record
        for record, value in matched
        if _relative_difference(value, claim.value) <= NUMERIC_TOLERANCE
    ]
    values_agree = all(
        _relative_difference(matched[0][1], value) <= NUMERIC_TOLERANCE
        for _, value in matched
    )
    if len(supporting) == len(matched):
        return _verdict(
            claim,
            scope=scope,
            verdict="supported",
            records=supporting,
            matched_value=matched[0][1],
        )
    if not supporting and values_agree:
        return _verdict(
            claim,
            scope=scope,
            verdict="contradicted",
            records=[matched[0][0]],
            matched_value=matched[0][1],
        )
    return _verdict(
        claim,
        scope=scope,
        verdict="unverifiable",
        records=[record for record, _ in matched],
        reason="conflicting records",
    )


def _filing(claim: Claim, evidence: dict[str, Any], scope: str) -> dict[str, Any]:
    candidates = [
        record
        for record in evidence.values()
        if isinstance(record, dict)
        and _record_payload(record).get("kind") == "filing"
        and (
            claim.ticker is None
            or _record_payload(record).get("ticker") == claim.ticker
        )
    ]
    if claim.accession is not None:
        for record in candidates:
            if _record_payload(record).get("accession") == claim.accession:
                return _verdict(
                    claim, scope=scope, verdict="supported", records=[record]
                )
    elif claim.filing_type is not None and claim.date is not None:
        for record in candidates:
            payload = _record_payload(record)
            if (
                payload.get("filing_type") == claim.filing_type
                and payload.get("date") == claim.date
            ):
                return _verdict(
                    claim, scope=scope, verdict="supported", records=[record]
                )
    return _verdict(
        claim, scope=scope, verdict="unchecked", reason="no matching filing"
    )


def _news(claim: Claim, evidence: dict[str, Any], scope: str) -> dict[str, Any]:
    if claim.date is None:
        return _verdict(claim, scope=scope, verdict="unchecked", reason="no date")
    try:
        wanted = date.fromisoformat(claim.date)
    except ValueError:
        return _verdict(claim, scope=scope, verdict="unchecked", reason="bad date")
    for record in evidence.values():
        payload = _record_payload(record)
        if payload.get("kind") != "news":
            continue
        if claim.ticker is not None and payload.get("ticker") != claim.ticker:
            continue
        raw_date = payload.get("date")
        if not isinstance(raw_date, str):
            continue
        try:
            record_date = date.fromisoformat(raw_date)
        except ValueError:
            continue
        if abs(record_date - wanted) <= NEWS_WINDOW:
            return _verdict(claim, scope=scope, verdict="supported", records=[record])
    return _verdict(claim, scope=scope, verdict="unchecked", reason="no matching news")


def match_claims(
    claims: list[Claim], evidence: dict[str, Any], *, scope: Literal["draft", "answer"]
) -> list[dict[str, Any]]:
    """Match claims against the ledger without fetching anything.

    Args:
        claims: Claims extracted from prose.
        evidence: The ledger, keyed by evidence id.
        scope: Whether the claims come from a draft or a final answer.

    Returns:
        One verdict per non-opinion claim. An opinion produces no verdict.
    """
    verdicts: list[dict[str, Any]] = []
    for claim in claims:
        if claim.kind == "opinion":
            continue
        if claim.kind == "numeric":
            verdicts.append(_numeric(claim, evidence, scope))
        elif claim.kind == "filing":
            verdicts.append(_filing(claim, evidence, scope))
        else:
            verdicts.append(_news(claim, evidence, scope))
    return verdicts
