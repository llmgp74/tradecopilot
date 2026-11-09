"""Check provisional calibration data and blind comparisons without model calls."""

import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError
from tradecopilot_eval.calibration import (
    CalibrationSet,
    build_calibration_inputs,
    compare_calibration,
    load_calibration,
)
from tradecopilot_eval.judge import (
    DIMENSIONS,
    JudgeConfig,
    JudgeInput,
    ScriptedJudgeTransport,
    judge_candidate,
)

_DATA = Path(__file__).resolve().parents[1] / "calibration" / "dev01.json"


def _context() -> JudgeInput:
    return JudgeInput(
        sample_id="context",
        request="Could I add to my SYNAA position?",
        decision_time="2026-09-15T14:00:00Z",
        profile={"position_cap_pct": 5},
        portfolio={"equity": 100000},
        journal_before_decision=[],
        reference_evidence=[
            {"id": "DEV01-QUOTE-20260915", "payload": {"price": 100}},
            {"id": "DEV01-PORTFOLIO-20260915", "payload": {"equity": 100000}},
        ],
        acceptance_criteria=["Use the confirmed position cap."],
        final_response={"text": ""},
    )


def _config() -> JudgeConfig:
    return JudgeConfig(
        agent_model="scripted:agent",
        judge_model="scripted:judge",
        agent_family="scripted",
        judge_family="scripted",
        mode="scripted",
    )


def test_calibration_inputs_exclude_provisional_labels() -> None:
    """Keep all four response kinds while withholding their labels from the judge."""
    suite = load_calibration(_DATA)
    assert suite.status == "provisional_unreviewed"
    assert {item.case_kind for item in suite.reference_expectations.values()} == {
        "strong",
        "mixed",
        "weak",
        "justified_abstention",
    }
    inputs = build_calibration_inputs(suite, _context())
    assert len(inputs) == 4
    assert len({candidate.sample_id for candidate in inputs.values()}) == 4
    for candidate_id, candidate in inputs.items():
        assert candidate.sample_id != candidate_id
        encoded = candidate.model_dump_json()
        for field in (
            "case_kind",
            "score_ranges",
            "reference_expectations",
            "expected_outcome",
        ):
            assert field not in encoded
        assert candidate.profile == _context().profile


def test_calibration_controls_and_missing_runs_remain_unassessed() -> None:
    """Fixed control scores cannot be presented as successful calibration."""
    suite = load_calibration(_DATA)
    inputs = build_calibration_inputs(suite, _context())
    first_id, first_input = next(iter(inputs.items()))
    result = asyncio.run(
        judge_candidate(first_input, ScriptedJudgeTransport(), _config())
    )
    comparison = compare_calibration(suite, {first_id: result})
    assert comparison.reference_status == "provisional_unreviewed"
    assert comparison.assessments[0].status == "scripted_control"
    assert comparison.assessments[0].within_provisional_ranges is None
    assert all(item.status == "missing" for item in comparison.assessments[1:])


def test_calibration_comparison_retains_errors_and_checks_sample_ids() -> None:
    """Report failures per case and reject results attached to the wrong candidate."""
    suite = load_calibration(_DATA)
    inputs = build_calibration_inputs(suite, _context())
    candidate_id, candidate = next(iter(inputs.items()))
    result = asyncio.run(
        judge_candidate(candidate, ScriptedJudgeTransport(), _config())
    )
    result.status = "judge_error"
    result.scores = None
    result.error = "Injected test failure"
    assessment = compare_calibration(suite, {candidate_id: result}).assessments[0]
    assert assessment.status == "judge_error" and assessment.error == result.error
    result.sample_id = "wrong-id"
    with pytest.raises(ValueError, match="mismatched"):
        compare_calibration(suite, {candidate_id: result})


def test_calibration_ranges_are_validated_without_claiming_human_review() -> None:
    """Require complete numeric ranges while keeping the unreviewed status explicit."""
    suite = load_calibration(_DATA)
    for expected in suite.reference_expectations.values():
        assert set(expected.score_ranges) == set(DIMENSIONS)
    raw = suite.model_dump()
    first = next(iter(raw["reference_expectations"].values()))
    first["score_ranges"]["reasoning"] = [5, 1]
    with pytest.raises(ValidationError, match="ranges"):
        CalibrationSet.model_validate(raw)
