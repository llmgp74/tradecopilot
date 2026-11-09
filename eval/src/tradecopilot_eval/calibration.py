"""Load provisional calibration cases without exposing their expected scores."""

import hashlib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, StrictInt, model_validator

from tradecopilot_eval.judge import (
    DIMENSIONS,
    RUBRIC_VERSION,
    Dimension,
    JudgeInput,
    JudgeResult,
    Outcome,
)


class CalibrationCandidate(BaseModel):
    """Candidate content only; quality labels are stored separately."""

    model_config = ConfigDict(extra="forbid")
    id: str
    final_response: dict[str, Any]


class CalibrationExpectation(BaseModel):
    """Provisional evaluator-only ranges that still need independent human review."""

    model_config = ConfigDict(extra="forbid")
    case_kind: Literal["strong", "mixed", "weak", "justified_abstention"]
    expected_outcome: Outcome
    score_ranges: dict[Dimension, tuple[StrictInt, StrictInt]]
    notes: str

    @model_validator(mode="after")
    def validate_ranges(self) -> "CalibrationExpectation":
        """Require a valid inclusive range for every rubric dimension."""
        if set(self.score_ranges) != set(DIMENSIONS):
            raise ValueError("Calibration expectations need all five dimensions.")
        if any(not 1 <= low <= high <= 5 for low, high in self.score_ranges.values()):
            raise ValueError("Calibration score ranges must lie between 1 and 5.")
        return self


class CalibrationSet(BaseModel):
    """Development candidates and separate, unreviewed reference expectations."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    status: Literal["provisional_unreviewed"]
    scenario_id: str
    rubric_version: str
    description: str
    candidates: list[CalibrationCandidate]
    reference_expectations: dict[str, CalibrationExpectation]

    @model_validator(mode="after")
    def validate_ids(self) -> "CalibrationSet":
        """Match every candidate to one expectation under the current rubric."""
        ids = [candidate.id for candidate in self.candidates]
        if not ids or len(set(ids)) != len(ids) or any(not value for value in ids):
            raise ValueError("Calibration candidate IDs must be nonempty and unique.")
        if set(ids) != set(self.reference_expectations):
            raise ValueError("Candidate and expectation IDs must match.")
        if self.rubric_version != RUBRIC_VERSION:
            raise ValueError("The calibration set uses a different rubric version.")
        return self


def load_calibration(path: Path) -> CalibrationSet:
    """Read and validate one provisional development calibration file.

    Args:
        path: JSON file containing candidates and separate expectations.

    Returns:
        Validated cases; this does not validate the quality of the human labels.

    Raises:
        ValueError: The file or its IDs, rubric, or score ranges are invalid.
        OSError: The file cannot be read.
    """
    return CalibrationSet.model_validate_json(path.read_text(encoding="utf-8"))


def _sample_id(suite: CalibrationSet, candidate_id: str) -> str:
    value = f"calibration:{suite.scenario_id}:{candidate_id}"
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def build_calibration_inputs(
    suite: CalibrationSet, context: JudgeInput
) -> dict[str, JudgeInput]:
    """Build blind candidate inputs without kinds, expected outcomes, or ranges.

    Args:
        suite: Validated development cases.
        context: The shared scenario request, confirmed context, and evidence.

    Returns:
        Inputs keyed by evaluator-side candidate ID. Prompt sample IDs are opaque.

    Raises:
        ValueError: A candidate contains fields outside the visible response view.
    """
    inputs: dict[str, JudgeInput] = {}
    for candidate in suite.candidates:
        data = context.model_dump()
        data.update(
            {
                "sample_id": _sample_id(suite, candidate.id),
                "final_response": candidate.final_response,
            }
        )
        inputs[candidate.id] = JudgeInput.model_validate(data)
    return inputs


class CalibrationAssessment(BaseModel):
    """Comparison with provisional expectations, or an explicit unassessed state."""

    candidate_id: str
    status: Literal["scored", "missing", "judge_error", "scripted_control"]
    outcome_matches: bool | None = None
    within_provisional_ranges: dict[Dimension, bool] | None = None
    error: str | None = None


class CalibrationComparison(BaseModel):
    """Per-case comparison that retains missing results and unreviewed label status."""

    reference_status: Literal["provisional_unreviewed"] = "provisional_unreviewed"
    assessments: list[CalibrationAssessment]


def compare_calibration(
    suite: CalibrationSet, results: dict[str, JudgeResult]
) -> CalibrationComparison:
    """Compare model scores with provisional ranges, preserving errors and controls.

    Args:
        suite: Candidate and evaluator-only expectations.
        results: Results keyed by the IDs returned from build_calibration_inputs.

    Returns:
        A comparison for every case. Scripted controls are left unassessed.

    Raises:
        ValueError: Result IDs are unknown or a result belongs to another sample.
    """
    if results.keys() - suite.reference_expectations.keys():
        raise ValueError("Calibration results contain an unknown candidate ID.")
    assessments = []
    for candidate in suite.candidates:
        result = results.get(candidate.id)
        if result is None:
            assessments.append(
                CalibrationAssessment(candidate_id=candidate.id, status="missing")
            )
            continue
        if result.sample_id != _sample_id(suite, candidate.id):
            raise ValueError("A calibration result has a mismatched blind sample ID.")
        if result.status != "ok" or result.scores is None:
            assessments.append(
                CalibrationAssessment(
                    candidate_id=candidate.id, status="judge_error", error=result.error
                )
            )
        elif result.config.mode == "scripted":
            assessments.append(
                CalibrationAssessment(
                    candidate_id=candidate.id, status="scripted_control"
                )
            )
        else:
            expected = suite.reference_expectations[candidate.id]
            assessments.append(
                CalibrationAssessment(
                    candidate_id=candidate.id,
                    status="scored",
                    outcome_matches=result.outcome == expected.expected_outcome,
                    within_provisional_ranges={
                        dimension: low <= result.scores[dimension].score <= high
                        for dimension, (low, high) in expected.score_ranges.items()
                    },
                )
            )
    return CalibrationComparison(assessments=assessments)
