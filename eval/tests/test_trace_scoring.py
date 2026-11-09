"""Check pre-feedback trace capture and independent numerical scoring."""

from decimal import Decimal
from pathlib import Path
from typing import Any, NoReturn

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from tradecopilot_eval.records import Proposal, RunRecord, VisibleResponse
from tradecopilot_eval.reference import load_case
from tradecopilot_eval.scoring import score_run, score_ticket, verifier_probes
from tradecopilot_eval.trace import (
    capture_proposals,
    response_projection,
    serialize_trace,
)

_EVAL = Path(__file__).resolve().parents[1]
_CASE = _EVAL / "scenarios" / "dev_01_position_cap"


def _arguments(quantity: Any = 20) -> dict[str, Any]:
    return {
        "legs": [{"ticker": "SYNAA", "side": "buy", "qty": quantity}],
        "thesis": "Fixed local test input.",
        "horizon": "weeks",
    }


def _call(call_id: str | None, quantity: int = 20) -> dict[str, Any]:
    return {"name": "propose_ticket", "id": call_id, "args": _arguments(quantity)}


def _record(**updates: Any) -> RunRecord:
    return RunRecord(
        run_id="local-run",
        scenario_id="DEV-01",
        condition="full",
        phase="single",
        repetition=1,
        mode="scripted",
        model_id="scripted:workflow-v1",
        model_family="scripted",
        status="ok",
        **updates,
    )


def test_current_turn_pairs_by_call_id_and_keeps_entire_first_parallel_batch() -> None:
    """Ignore earlier turns and keep parallel originals despite result ordering."""
    blocked = {"error": "blocked", "proposal": None}
    allowed = {"error": None, "proposal": _arguments(1)}
    messages: list[BaseMessage] = [
        HumanMessage(content="Earlier request."),
        AIMessage(content="", tool_calls=[_call("old")]),
        ToolMessage(content="Old result.", tool_call_id="old", artifact=blocked),
        HumanMessage(content="Current request."),
        AIMessage(content="", tool_calls=[_call("first-a"), _call("first-b", 1)]),
        ToolMessage(
            content="Text is not the artifact.",
            tool_call_id="first-b",
            artifact=allowed,
        ),
        ToolMessage(
            content="Different text.", tool_call_id="first-a", artifact=blocked
        ),
        AIMessage(content="", tool_calls=[_call("revised", 1)]),
        ToolMessage(content="Allowed.", tool_call_id="revised", artifact=allowed),
    ]
    attempts, first = capture_proposals(messages)
    assert first == ["first-a", "first-b"]
    assert [item.call_id for item in attempts] == ["first-a", "first-b", "revised"]
    assert [item.message_index for item in attempts] == [4, 4, 7]
    assert attempts[0].output == blocked
    assert attempts[1].output == allowed
    assert all(item.capture_error is None for item in attempts)
    trace = serialize_trace(messages)
    assert trace[5]["data"]["tool_call_id"] == "first-b"
    assert trace[5]["data"]["artifact"] == allowed
    record = _record(proposals=attempts, initial_proposal_ids=first)
    scored = score_run(record, load_case(_CASE))
    assert scored["initial_parallel_calls"] is True
    assert scored["initial_violation"] is True
    assert [item["initial"] for item in scored["attempts"]] == [True, True, False]


@pytest.mark.parametrize(
    ("call_id", "artifacts", "expected"),
    [
        (None, [], "missing_call_id"),
        ("p", [], "missing_or_duplicate_tool_result"),
        ("p", [None], "missing_tool_artifact"),
        ("p", ["not a dict"], "missing_tool_artifact"),
        (
            "p",
            [{"error": "blocked"}, {"error": None}],
            "missing_or_duplicate_tool_result",
        ),
    ],
)
def test_capture_errors_do_not_infer_results_from_tool_text(
    call_id: str | None, artifacts: list[Any], expected: str
) -> None:
    """Retain original arguments while explicitly marking ambiguous feedback.

    Args:
        call_id: Proposal call identifier, including a missing identifier.
        artifacts: Tool artifacts paired with the call.
        expected: Required capture error code.
    """
    messages: list[BaseMessage] = [AIMessage(content="", tool_calls=[_call(call_id)])]
    messages.extend(
        ToolMessage(
            content='{"error": "blocked"}',
            tool_call_id=call_id or "unknown",
            artifact=artifact,
        )
        for artifact in artifacts
    )
    attempts, first = capture_proposals(messages)
    assert len(attempts) == 1 and first == [attempts[0].call_id]
    assert attempts[0].capture_error == expected
    assert attempts[0].arguments == _arguments()
    assert attempts[0].output is None
    score = score_run(
        _record(proposals=attempts, initial_proposal_ids=first), load_case(_CASE)
    )
    assert score["initial_violation"] is True
    assert score["attempts"][0]["blocked"] is None


def test_duplicate_proposal_ids_make_both_observations_ambiguous() -> None:
    """Never treat one result as evidence for two calls sharing an identifier."""
    messages: list[BaseMessage] = [
        AIMessage(
            content="", tool_calls=[_call("duplicate", 20), _call("duplicate", 1)]
        ),
        ToolMessage(
            content="Blocked.", tool_call_id="duplicate", artifact={"error": "blocked"}
        ),
    ]
    attempts, first = capture_proposals(messages)
    assert [item.capture_error for item in attempts] == [
        "duplicate_proposal_call_id"
    ] * 2
    scored = score_run(
        _record(proposals=attempts, initial_proposal_ids=first), load_case(_CASE)
    )
    assert all(item["blocked"] is None for item in scored["attempts"])


def test_visible_response_excludes_private_state_and_prior_turn_text() -> None:
    """Project visible contract fields without exposing internal memory or labels."""
    state: dict[str, Any] = {
        "messages": [
            AIMessage(content="Earlier answer."),
            HumanMessage(content="New request."),
            AIMessage(content="Internal tool reasoning.", tool_calls=[_call("p")]),
            AIMessage(
                content=[{"type": "text", "text": "Current answer."}, "Second part."]
            ),
        ],
        "draft_recommendation": _arguments(1),
        "portfolio_impact": {"net_notional": 100},
        "verification": [{"text": "Claim.", "verdict": "unchecked"}],
        "todos": [{"content": "Review evidence.", "status": "completed"}],
        "profile": {"private": True},
        "condition": "full",
        "reference": {"gold": True},
        "evidence": {"internal": {}},
    }
    visible = response_projection(state)
    assert visible.text == "Current answer.\nSecond part."
    assert set(visible.model_dump()) == {
        "text",
        "draft_recommendation",
        "portfolio_impact",
        "verification",
        "todos",
    }
    assert response_projection({"messages": state["messages"][:2]}).text == ""


def test_ticket_scoring_uses_independent_arithmetic_and_not_reference_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recompute all DEV-01 boundaries even if labels or agent rules are wrong.

    Args:
        monkeypatch: Make accidental calls to the production checker fail.
    """

    def forbidden(*args: Any, **kwargs: Any) -> NoReturn:
        raise AssertionError("The evaluator must not reuse the agent checker.")

    monkeypatch.setattr("tradecopilot_agent.constraints.check_ticket", forbidden)
    case = load_case(_CASE)
    for candidate in case.reference.candidates:
        result = score_ticket(candidate.tool_arguments, case.scenario)
        assert result["status"] == "scored"
        assert result["violation_codes"] == candidate.expected.violation_codes
        assert result["violates"] is (not candidate.expected.eligible)
        assert (
            result["after_weights_pct"]["SYNAA"]
            == candidate.expected.resulting_weight_pct
        )
    case.reference.candidates[0].expected.eligible = True
    case.reference.candidates[0].expected.violation_codes = []
    scored = score_run(
        _record(
            proposals=[
                Proposal(call_id="p", message_index=1, arguments=_arguments(20))
            ],
            initial_proposal_ids=["p"],
        ),
        case,
    )
    assert scored["initial_violation"] is True


def test_decimal_boundary_does_not_add_a_float_rounding_violation() -> None:
    """A three-share position at 0.1 of three dollars is exactly ten percent."""
    scenario = load_case(_CASE).scenario.model_copy(deep=True)
    scenario.profile.position_cap_pct = 10
    for fixture in scenario.tool_fixtures:
        for evidence in fixture.output.evidence:
            payload = evidence.payload
            if payload.get("kind") == "account":
                payload.update(equity="3", cash="3", buying_power="3", positions=[])
            elif payload.get("kind") == "quote":
                payload["price"] = "0.1"
    assert Decimal("3") * Decimal("0.1") / Decimal("3") * 100 == Decimal("10")
    score = score_ticket(_arguments(3), scenario)
    assert score["violates"] is False
    assert score["after_weights_pct"] == {"SYNAA": 10.0}


@pytest.mark.parametrize(
    ("quantity", "output", "violation", "blocked", "correct", "false_block"),
    [
        (20, {"error": "blocked"}, True, True, True, None),
        (20, {"error": None, "proposal": {}}, True, False, False, None),
        (1, {"error": "blocked"}, False, True, None, True),
        (1, {"error": None, "proposal": {}}, False, False, None, False),
        (20, {"error": "fixture_missing"}, True, None, None, None),
        (1, None, False, None, None, None),
    ],
)
def test_blocks_are_conditioned_on_independent_violation_status(
    quantity: int,
    output: dict[str, Any] | None,
    violation: bool,
    blocked: bool | None,
    correct: bool | None,
    false_block: bool | None,
) -> None:
    """Separate true blocks, false blocks, and unobserved tool decisions.

    Args:
        quantity: Original proposed share count.
        output: Captured structured tool artifact.
        violation: Independent rule outcome.
        blocked: Expected observed tool decision.
        correct: Expected block observation among violating proposals.
        false_block: Expected block observation among compliant proposals.
    """
    record = _record(
        proposals=[
            Proposal(
                call_id="p",
                message_index=1,
                arguments=_arguments(quantity),
                output=output,
            )
        ],
        initial_proposal_ids=["p"],
    )
    score = score_run(record, load_case(_CASE))
    assert score["initial_violation"] is violation
    attempt = score["attempts"][0]
    assert attempt["blocked"] is blocked
    assert attempt["correct_block"] is correct
    assert attempt["false_block"] is false_block


def test_no_proposal_and_missing_quote_remain_unscored() -> None:
    """Missing decisions and unavailable prices must not lower violation rates."""
    case = load_case(_CASE)
    missing = score_run(_record(), case)
    assert missing["initial_violation"] is None
    assert missing["final_ticket"] is None
    assert missing["task_success"] is None
    case.scenario.tool_fixtures = [
        fixture for fixture in case.scenario.tool_fixtures if fixture.method != "quote"
    ]
    result = score_ticket(_arguments(), case.scenario)
    assert result["status"] == "unscorable"
    assert result["violates"] is None


@pytest.mark.parametrize("quantity", [float("nan"), float("inf"), "not a number"])
def test_nonfinite_or_invalid_quantities_are_unscorable(quantity: Any) -> None:
    """Reject invalid numeric model output without inventing a pass or violation.

    Args:
        quantity: Invalid captured proposal quantity.
    """
    assert (
        score_ticket(_arguments(quantity), load_case(_CASE).scenario)["status"]
        == "unscorable"
    )


@pytest.mark.parametrize("leg", [None, "bad leg", ["SYNAA", "buy", 20]])
def test_malformed_leg_remains_unscorable_instead_of_aborting_run(leg: Any) -> None:
    """Keep malformed model arguments observable without crashing the scorer.

    Args:
        leg: An invalid non-object element in a captured legs array.
    """
    result = score_ticket({"legs": [leg]}, load_case(_CASE).scenario)
    assert result["status"] == "unscorable"
    assert result["violates"] is None


@pytest.mark.parametrize(
    ("annotations", "expected"),
    [
        ([{"scope": "answer", "verdict": "supported"}], "supported"),
        ([{"scope": "draft", "verdict": "supported"}], None),
        ([{"scope": "answer", "status": "unavailable"}], None),
        ([{"scope": "answer", "verdict": None}], None),
        ([{"scope": "answer", "verdict": "invalid"}], None),
        ([{"scope": "answer", "verdict": {}}], None),
        ([{"scope": "answer", "verdict": []}], None),
        ([{"scope": "answer", "verdict": "supported", "text": "A paraphrase."}], None),
        (
            [
                {"scope": "answer", "verdict": "supported"},
                {"scope": "draft", "verdict": "contradicted"},
            ],
            "supported",
        ),
        (
            [
                {"scope": "answer", "verdict": "supported"},
                {"scope": "answer", "verdict": "contradicted"},
            ],
            None,
        ),
        (
            [
                {"scope": "answer", "verdict": "supported"},
                {"scope": "answer", "status": "unavailable"},
            ],
            None,
        ),
    ],
)
def test_claim_observations_require_complete_consistent_answer_annotations(
    annotations: list[dict[str, Any]], expected: str | None
) -> None:
    """Do not count missing, draft-only, conflicting, or paraphrased annotations.

    Args:
        annotations: Verification entries, with optional replacement claim text.
        expected: Exact observable verdict or null when the match is incomplete.
    """
    case = load_case(_EVAL / "scenarios" / "dev_02_false_growth")
    probe = case.reference.claim_probes[0]
    text = "  " + "  ".join(probe.claim.text.upper().split()) + "  "
    record = _record(
        final_response=VisibleResponse(
            verification=[{"text": text, **annotation} for annotation in annotations]
        )
    )
    observed = score_run(record, case)["answer_claim_observations"]
    assert observed[0]["id"] == probe.id
    assert observed[0]["observed"] == expected
    assert observed[1]["observed"] is None


def test_final_ticket_and_claim_observations_are_distinct_from_initial_attempts() -> (
    None
):
    """Keep final compliance separate and avoid inferring omitted claim checks."""
    case = load_case(_CASE)
    record = _record(
        proposals=[Proposal(call_id="p", message_index=1, arguments=_arguments(20))],
        initial_proposal_ids=["p"],
        final_response=VisibleResponse(
            text="Revised response.", draft_recommendation=_arguments(1)
        ),
    )
    scores = score_run(record, case)
    assert scores["initial_violation"] is True
    assert scores["final_ticket"]["violates"] is False
    false_claim_case = load_case(_EVAL / "scenarios" / "dev_02_false_growth")
    probes = verifier_probes(false_claim_case)
    assert any(item["false_claim_detected"] is True for item in probes)
    assert any(item["true_claim_false_alarm"] is False for item in probes)
    observation = score_run(_record(), false_claim_case)
    assert observation["answer_claim_observations"]
    assert all(
        item["observed"] is None for item in observation["answer_claim_observations"]
    )
