"""Check frozen replay boundaries without model or provider requests."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from tradecopilot_agent.data import DataSource
from tradecopilot_agent.state import EvidenceRecord, ToolOutput
from tradecopilot_eval.fixtures import ToolFixture
from tradecopilot_eval.source import FrozenSource

_DECISION = datetime(2026, 9, 15, 14, tzinfo=UTC)
_CONTENT = "fixture-content-that-must-not-leak"


def _quote_fixture() -> ToolFixture:
    return ToolFixture(
        method="quote",
        arguments={"ticker": "SYNAA"},
        available_at=_DECISION,
        output=ToolOutput(
            summary=_CONTENT,
            evidence=[
                EvidenceRecord(
                    id="synthetic-quote",
                    tool="get_quote",
                    source="synthetic",
                    published_at=_DECISION.isoformat(),
                    fetched_at="2026-11-05T00:00:00Z",
                    payload={
                        "kind": "quote",
                        "ticker": "SYNAA",
                        "price": 100.0,
                        "nested": {"notes": [_CONTENT]},
                    },
                )
            ],
        ),
    )


def test_protocol_and_capabilities_exclude_execution() -> None:
    """Expose the DataSource interface without allowing mutable capabilities."""
    source = FrozenSource([], _DECISION)
    assert isinstance(source, DataSource)
    expected = {"alpaca", "edgar", "fmp", "finnhub", "fred"}
    assert source.capabilities() == expected
    returned = source.capabilities()
    returned.add("order_execution")
    assert source.capabilities() == expected


def test_duplicate_keys_ignore_dictionary_order() -> None:
    """Reject competing responses for the same method and argument values."""
    first = ToolFixture(
        method="news",
        arguments={"ticker": "SYNAA", "limit": 10},
        available_at=_DECISION,
        output=ToolOutput(summary="First response"),
    )
    second = first.model_copy(
        update={"arguments": {"limit": 10, "ticker": "SYNAA"}}, deep=True
    )
    second.output.summary = "Conflicting response"
    with pytest.raises(ValueError, match="Duplicate fixture"):
        FrozenSource([first, second], _DECISION)


@pytest.mark.parametrize(
    ("method", "arguments"),
    [
        ("quote", {"ticker": "MISSING"}),
        ("bars", {"ticker": "MISSING", "period": "1d", "interval": "1d"}),
        ("portfolio", {}),
        ("positions", {}),
        ("fundamentals", {"ticker": "MISSING"}),
        ("filings", {"ticker": "MISSING"}),
        (
            "xbrl_fact",
            {"ticker": "MISSING", "tag": "Revenues", "period": "FY2025", "unit": "USD"},
        ),
        ("news", {"ticker": "MISSING"}),
        ("macro", {"series": "MISSING", "period": "1y"}),
    ],
)
def test_missing_fixture_is_an_explicit_error(
    method: str, arguments: dict[str, Any]
) -> None:
    """Return a failure from every data method instead of fetching live data.

    Args:
        method: DataSource method to call.
        arguments: Valid arguments without a matching fixture.
    """
    source = FrozenSource([], _DECISION)
    output = asyncio.run(getattr(source, method)(**arguments))
    assert isinstance(output, ToolOutput)
    assert output.error == "fixture_missing"
    assert method in output.summary
    assert output.evidence == []


def test_lookup_keeps_exact_arguments_and_method_defaults() -> None:
    """Do not broaden a replay to a different ticker or result limit."""
    quote = _quote_fixture()
    news = ToolFixture(
        method="news",
        arguments={"ticker": "SYNAA", "limit": 10},
        available_at=_DECISION,
        output=ToolOutput(summary="No news in this fixture."),
    )
    source = FrozenSource([quote, news], _DECISION)
    assert asyncio.run(source.quote("SYNAA")).error is None
    assert asyncio.run(source.quote("synaa")).error == "fixture_missing"
    assert asyncio.run(source.news("SYNAA")).error is None
    assert asyncio.run(source.news("SYNAA", limit=11)).error == "fixture_missing"


def test_replay_copies_inputs_and_each_returned_response() -> None:
    """Prevent caller mutations from changing later replay results."""
    fixture = _quote_fixture()
    fixtures = [fixture]
    source = FrozenSource(fixtures, _DECISION)
    fixture.arguments["ticker"] = "CHANGED"
    fixture.output.evidence[0].payload["price"] = 999.0
    fixtures.clear()
    first = asyncio.run(source.quote("SYNAA"))
    assert first.evidence[0].payload["price"] == 100.0
    first.summary = "Changed summary"
    first.evidence[0].payload["nested"]["notes"].append("Changed nested value")
    first.evidence.clear()
    second = asyncio.run(source.quote("SYNAA"))
    assert second.summary == _CONTENT
    assert second.evidence[0].payload["nested"]["notes"] == [_CONTENT]


@pytest.mark.parametrize("future_field", ["available_at", "published_at"])
def test_future_content_withholds_the_entire_response(future_field: str) -> None:
    """Reject summary and all evidence if any part is unavailable.

    Args:
        future_field: Availability boundary moved beyond the decision time.
    """
    fixture = _quote_fixture()
    future = _DECISION + timedelta(seconds=1)
    if future_field == "available_at":
        fixture.available_at = future
    else:
        extra = fixture.output.evidence[0].model_copy(deep=True)
        extra.id = "future-record"
        extra.published_at = future.isoformat()
        fixture.output.evidence.append(extra)
    output = asyncio.run(FrozenSource([fixture], _DECISION).quote("SYNAA"))
    assert output.error == "fixture_after_cutoff"
    assert output.evidence == []
    assert _CONTENT not in output.model_dump_json()


@pytest.mark.parametrize(
    "published_at", [None, "invalid-time", "2026-09-15", "2026-09-15T14:00:00"]
)
def test_unusable_publication_time_withholds_content(published_at: str | None) -> None:
    """Do not treat missing or timezone-free publication dates as eligible.

    Args:
        published_at: Missing, malformed, or naive evidence timestamp.
    """
    fixture = _quote_fixture()
    fixture.output.evidence[0].published_at = published_at
    output = asyncio.run(FrozenSource([fixture], _DECISION).quote("SYNAA"))
    assert output.error == "fixture_invalid"
    assert output.evidence == []
    assert _CONTENT not in output.model_dump_json()


def test_cutoff_is_inclusive_and_archival_fetch_time_can_be_later() -> None:
    """Compare absolute availability times, independently of later archiving."""
    fixture = _quote_fixture()
    offset_time = datetime.fromisoformat("2026-09-15T22:00:00+08:00")
    fixture.available_at = offset_time
    fixture.output.evidence[0].published_at = offset_time.isoformat()
    output = asyncio.run(FrozenSource([fixture], _DECISION).quote("SYNAA"))
    assert output.error is None
    assert output.evidence[0].fetched_at == "2026-11-05T00:00:00Z"


def test_naive_decision_time_is_rejected() -> None:
    """Require an unambiguous cutoff before serving any fixture."""
    with pytest.raises(ValueError, match="timezone"):
        FrozenSource([], _DECISION.replace(tzinfo=None))


def test_planned_tool_failure_is_preserved() -> None:
    """Replay an eligible failure instead of treating it as a missing fixture."""
    fixture = _quote_fixture()
    fixture.output = ToolOutput(
        summary="Planned quote failure.", error="planned_outage"
    )
    output = asyncio.run(FrozenSource([fixture], _DECISION).quote("SYNAA"))
    assert output.error == "planned_outage"
    assert output.summary == "Planned quote failure."


def test_direct_order_calls_are_disabled() -> None:
    """Refuse order calls even when a caller bypasses capability filtering."""
    source = FrozenSource([_quote_fixture()], _DECISION)
    output = asyncio.run(
        source.place_leg({"ticker": "SYNAA", "side": "buy", "qty": 10}, "manual-call")
    )
    assert output.error == "execution_disabled"
    assert output.evidence == []
    assert output.proposal is None
    assert output.ticket_done is False
