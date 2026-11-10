"""Deterministic claim matching against the evidence ledger."""

from tradecopilot_agent.claims import match_claims
from tradecopilot_agent.state import Claim, EvidenceRecord


def _record(
    evidence_id: str,
    *,
    source: str = "sec_edgar",
    tool: str = "get_xbrl_fact",
    payload: dict | None = None,
) -> EvidenceRecord:
    return EvidenceRecord(
        id=evidence_id,
        tool=tool,
        args={"ticker": "NVDA", "tag": "Revenues"},
        source=source,
        url=None,
        published_at="2025-11-20T21:00:00Z",
        fetched_at="2026-11-05T14:03:11Z",
        stale=False,
        payload=payload
        or {
            "kind": "xbrl",
            "ticker": "NVDA",
            "tag": "Revenues",
            "period": "2025-10-26",
            "unit": "USD",
            "value": 35_082_000_000.0,
        },
    )


def _ledger(*records: EvidenceRecord) -> dict[str, dict]:
    return {record.id: record.model_dump(mode="json") for record in records}


def _numeric_claim(**overrides: object) -> Claim:
    values: dict[str, object] = {
        "text": "NVDA revenue was 35.1 billion",
        "kind": "numeric",
        "ticker": "NVDA",
        "tag": "Revenues",
        "value": 35_100_000_000.0,
        "unit": "USD",
        "period": "2025-10-26",
    }
    values.update(overrides)
    return Claim(**values)


def test_numeric_claim_within_tolerance_is_supported() -> None:
    """A value inside the relative tolerance is supported."""
    verdicts = match_claims(
        [_numeric_claim()], _ledger(_record("ev_1")), scope="answer"
    )

    assert len(verdicts) == 1
    assert verdicts[0]["verdict"] == "supported"
    assert verdicts[0]["evidence_ids"] == ["ev_1"]
    assert verdicts[0]["source"] == "sec_edgar"


def test_numeric_claim_outside_tolerance_is_contradicted() -> None:
    """A value outside the tolerance against a matching record is contradicted."""
    verdicts = match_claims(
        [_numeric_claim(value=36_000_000_000.0)],
        _ledger(_record("ev_1")),
        scope="answer",
    )

    assert verdicts[0]["verdict"] == "contradicted"
    assert verdicts[0]["matched_value"] == 35_082_000_000.0


def test_numeric_claim_without_tag_is_unchecked() -> None:
    """Without an XBRL tag there is no deterministic match."""
    verdicts = match_claims(
        [_numeric_claim(tag=None)], _ledger(_record("ev_1")), scope="answer"
    )

    assert verdicts[0]["verdict"] == "unchecked"


def test_conflicting_records_are_unverifiable() -> None:
    """Two records for the same subject and period cannot be chosen between."""
    second = _record("ev_2")
    second.payload["value"] = 30_000_000_000.0

    verdicts = match_claims(
        [_numeric_claim()], _ledger(_record("ev_1"), second), scope="answer"
    )

    assert verdicts[0]["verdict"] == "unverifiable"


def test_missing_evidence_hint_is_unchecked() -> None:
    """A hint that names no ledger record is unchecked, never matched elsewhere."""
    verdicts = match_claims(
        [_numeric_claim(evidence_hint="ev_missing")],
        _ledger(_record("ev_1")),
        scope="answer",
    )

    assert verdicts[0]["verdict"] == "unchecked"


def test_filing_claim_matches_accession() -> None:
    """A filing claim matches on accession number."""
    record = _record(
        "ev_filing",
        tool="get_filings",
        payload={
            "kind": "filing",
            "ticker": "NVDA",
            "accession": "0001045810-25-000123",
            "filing_type": "10-Q",
            "date": "2025-11-20",
        },
    )
    claim = Claim(
        text="NVDA filed a 10-Q on 20 November",
        kind="filing",
        ticker="NVDA",
        accession="0001045810-25-000123",
    )

    verdicts = match_claims([claim], _ledger(record), scope="draft")

    assert verdicts[0]["verdict"] == "supported"
    assert verdicts[0]["scope"] == "draft"


def test_news_claim_matches_date_window() -> None:
    """A news claim matches a record dated within one day."""
    record = _record(
        "ev_news",
        source="finnhub",
        tool="get_news",
        payload={
            "kind": "news",
            "ticker": "NVDA",
            "date": "2025-11-20",
            "headline": "NVDA raises guidance",
        },
    )
    claim = Claim(
        text="NVDA raised guidance yesterday",
        kind="news",
        ticker="NVDA",
        date="2025-11-21",
    )

    verdicts = match_claims([claim], _ledger(record), scope="answer")

    assert verdicts[0]["verdict"] == "supported"


def _account_record() -> EvidenceRecord:
    return EvidenceRecord(
        id="ev_account",
        tool="get_portfolio",
        args={},
        source="alpaca",
        fetched_at="2026-11-05T14:03:11Z",
        payload={
            "kind": "account",
            "equity": 1_000_000.0,
            "cash": 1_000_000.0,
            "buying_power": 4_000_000.0,
            "positions": [],
        },
    )


def test_account_figures_match_the_broker_record() -> None:
    """Equity, cash, buying power, and position count verify against Alpaca."""
    claims = [
        Claim(text="Total equity is $1,000,000.", kind="numeric", value=1_000_000.0),
        Claim(text="Cash is $1,000,000.", kind="numeric", value=1_000_000.0),
        Claim(text="Buying power is $4,000,000.", kind="numeric", value=4_000_000.0),
        Claim(
            text="There are no open positions.",
            kind="numeric",
            value=0,
            unit="positions",
        ),
    ]

    verdicts = match_claims(claims, _ledger(_account_record()), scope="answer")

    assert [item["verdict"] for item in verdicts] == ["supported"] * 4
    assert all(item["source"] == "alpaca" for item in verdicts)


def test_wrong_account_figure_is_contradicted() -> None:
    """A wrong account number is contradicted by the broker record."""
    claim = Claim(text="Cash is $2,000,000.", kind="numeric", value=2_000_000.0)

    verdict = match_claims([claim], _ledger(_account_record()), scope="answer")[0]

    assert verdict["verdict"] == "contradicted"
    assert verdict["matched_value"] == 1_000_000.0


def test_tagged_claim_ignores_an_unrelated_quote() -> None:
    """A tagged metric is not checked against a same-ticker price record."""
    quote = _record(
        "ev_quote",
        source="alpaca",
        tool="get_quote",
        payload={"kind": "quote", "ticker": "NVDA", "price": 195.0},
    )

    verdict = match_claims(
        [_numeric_claim()], _ledger(_record("ev_1"), quote), scope="answer"
    )[0]

    assert verdict["verdict"] == "supported"
    assert verdict["evidence_ids"] == ["ev_1"]


def test_quote_matches_a_ticker_numeric_claim() -> None:
    """A quoted price verifies against the quote record."""
    record = _record(
        "ev_quote",
        source="alpaca",
        tool="get_quote",
        payload={"kind": "quote", "ticker": "NVDA", "price": 195.0},
    )
    claim = Claim(text="NVDA is at 195.", kind="numeric", ticker="NVDA", value=195.0)

    verdict = match_claims([claim], _ledger(record), scope="answer")[0]

    assert verdict["verdict"] == "supported"


def test_opinion_produces_no_verdict() -> None:
    """Opinions are not checked."""
    claim = Claim(text="NVDA is a good buy", kind="opinion", ticker="NVDA")

    assert match_claims([claim], _ledger(_record("ev_1")), scope="answer") == []
