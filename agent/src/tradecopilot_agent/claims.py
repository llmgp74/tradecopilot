"""Claim extraction and deterministic matching against the evidence ledger."""

from datetime import date, timedelta
from typing import Any, Literal

from langchain.chat_models import init_chat_model
from pydantic import BaseModel

from tradecopilot_agent.state import Claim

NUMERIC_TOLERANCE = 0.005
NEWS_WINDOW = timedelta(days=1)


class ExtractedClaims(BaseModel):
    """Structured output of the claim extractor."""

    claims: list[Claim]


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


def _numeric(claim: Claim, evidence: dict[str, Any], scope: str) -> dict[str, Any]:
    if claim.value is None:
        return _verdict(claim, scope=scope, verdict="unchecked", reason="no value")
    if claim.tag is None:
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


def build_extractor(model: str) -> Any:
    """Return a callable that extracts claims from prose.

    Args:
        model: ``provider:model`` string used for extraction.

    Returns:
        A synchronous callable taking text and returning claims.
    """
    chat = init_chat_model(model, temperature=0).with_structured_output(ExtractedClaims)

    def extract(text: str) -> list[Claim]:
        if not text.strip():
            return []
        result: Any = chat.invoke(
            "Extract every factual claim from the text. Use kind numeric for "
            "numbers, filing for SEC filing references, news for dated news, and "
            "opinion otherwise. Give numeric claims their XBRL tag when known. "
            f"Text:\n{text}"
        )
        return list(ExtractedClaims.model_validate(result).claims)

    return extract
