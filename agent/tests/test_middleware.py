"""Pure helpers behind the agent middleware."""

from datetime import date

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.types import Command
from tradecopilot_agent.middleware import (
    _with_updates,
    annotate,
    artifact_updates,
    budget_denied,
    render_memory,
    request_tickers,
)
from tradecopilot_agent.state import Claim, EvidenceRecord, ToolOutput

AS_OF = date(2026, 11, 5)


def _record(
    evidence_id: str = "ev_1",
    *,
    published_at: str | None = "2025-11-20T21:00:00Z",
    payload: dict | None = None,
) -> EvidenceRecord:
    return EvidenceRecord(
        id=evidence_id,
        tool="get_xbrl_fact",
        source="sec_edgar",
        published_at=published_at,
        fetched_at="2026-11-05T14:00:00Z",
        payload=payload or {"kind": "xbrl", "ticker": "NVDA"},
    )


def test_memory_condition_none_injects_nothing() -> None:
    """No memory renders an empty block."""
    assert render_memory("none", {"risk_band": "moderate"}, []) == ""


def test_prose_and_structured_render_the_profile() -> None:
    """Prose is ordinary text; structured names the typed constraints."""
    profile = {
        "risk_band": "conservative",
        "position_cap_pct": 5.0,
        "sector_exclusions": ["Energy"],
        "horizon": "weeks",
        "watchlist": ["NVDA"],
        "execution": {"autonomous": False, "max_order_notional": 1000.0},
    }

    prose = render_memory("prose", profile, [])
    structured = render_memory("structured", profile, [])

    assert "conservative" in prose
    assert "position_cap_pct" not in prose
    assert "position_cap_pct: 5.0" in structured
    assert "Energy" in structured


def test_full_memory_includes_recent_decisions() -> None:
    """Full memory appends compact journal entries."""
    entries = [
        {
            "id": "d1",
            "created_at": "2026-10-01T10:00:00Z",
            "status": "rejected",
            "thesis": "trim NVDA",
            "rejection_reason": "too big",
            "legs": [{"ticker": "NVDA", "side": "sell", "qty": 5}],
        }
    ]

    block = render_memory("full", {"risk_band": "moderate"}, entries)

    assert "d1" in block
    assert "trim NVDA" in block
    assert "too big" in block


def test_request_tickers_only_returns_known_symbols() -> None:
    """Only symbols already known to the app are treated as tickers."""
    text = "Should I add NVDA and sell TSLA? ALSO maybe"

    assert request_tickers(text, {"NVDA", "ZZZZ"}) == ["NVDA"]


def test_artifact_updates_drop_late_evidence() -> None:
    """Records dated after the cutoff never enter the ledger."""
    output = ToolOutput(
        summary="ok",
        evidence=[
            _record("ev_old", published_at="2025-11-20T21:00:00Z"),
            _record("ev_new", published_at="2026-12-01T21:00:00Z"),
        ],
    )

    updates = artifact_updates(output, AS_OF)

    assert set(updates["evidence"]) == {"ev_old"}


def test_artifact_updates_store_a_proposal() -> None:
    """A proposal fills the draft, ticket, impact, and verdict channels."""
    output = ToolOutput(
        summary="proposed",
        proposal={"id": "t_1", "legs": [], "thesis": "x"},
        portfolio_impact={"net_notional": 100.0},
        verification=[{"scope": "draft", "verdict": "supported", "text": "x"}],
    )

    updates = artifact_updates(output, None)

    assert updates["pending_ticket"]["id"] == "t_1"
    assert updates["portfolio_impact"] == {"net_notional": 100.0}
    assert updates["verification"][0]["scope"] == "draft"


def test_artifact_updates_clear_the_ticket_after_execution() -> None:
    """A finished execution clears the pending ticket."""
    updates = artifact_updates(ToolOutput(summary="done", ticket_done=True), None)

    assert updates["pending_ticket"] is None


def test_budget_denies_after_twelve_evidence_calls() -> None:
    """The gather budget refuses evidence tools past its limit."""
    calls = [
        ToolMessage(content="x", tool_call_id=f"c{i}", name="get_quote")
        for i in range(12)
    ]
    state = {"messages": [HumanMessage(content="hi"), *calls]}

    assert budget_denied(state, "get_quote") is True
    assert budget_denied(state, "verify_claims") is False
    assert budget_denied({"messages": calls[:2]}, "get_quote") is False


def test_annotation_marks_claims_and_survives_extractor_failure() -> None:
    """Verdicts use the answer scope; a failed extractor is recorded."""
    evidence = {
        "ev_1": _record(
            "ev_1",
            payload={
                "kind": "xbrl",
                "ticker": "NVDA",
                "tag": "Revenues",
                "period": "2025-10-26",
                "unit": "USD",
                "value": 35_082_000_000.0,
            },
        ).model_dump(mode="json")
    }

    def extract(_text: str) -> list[Claim]:
        return [
            Claim(
                text="NVDA revenue was 35.1B",
                kind="numeric",
                ticker="NVDA",
                tag="Revenues",
                value=35_100_000_000.0,
                unit="USD",
                period="2025-10-26",
            )
        ]

    verdicts = annotate("NVDA revenue was 35.1B", evidence, extract)
    assert verdicts[0]["verdict"] == "supported"
    assert verdicts[0]["scope"] == "answer"

    def broken(_text: str) -> list[Claim]:
        raise RuntimeError("boom")

    unavailable = annotate("anything", evidence, broken)
    assert unavailable[0]["status"] == "unavailable"


def test_tool_result_becomes_a_state_command() -> None:
    """A tool artifact is recorded and counted through a Command."""
    output = ToolOutput(summary="ok", evidence=[_record("ev_1")])
    message = ToolMessage(
        content="ok", tool_call_id="call_1", artifact=output.model_dump(mode="json")
    )

    command = _with_updates(message, AS_OF)

    assert isinstance(command, Command)
    assert set(command.update["evidence"]) == {"ev_1"}
    assert command.update["messages"] == [message]


def test_plain_tool_results_are_untouched() -> None:
    """A result without an artifact does not produce a Command."""
    message = ToolMessage(content="done", tool_call_id="call_2")

    assert _with_updates(message, AS_OF) is message
