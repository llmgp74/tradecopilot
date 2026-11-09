"""Freeze case versions and schedule the proposal's repeated memory comparison."""

import json
import random
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel
from tradecopilot_agent.memory import MemoryCondition

from tradecopilot_eval.judge import JudgeConfig
from tradecopilot_eval.records import RunRecord
from tradecopilot_eval.reference import Case, Suite, file_digest, load_suite
from tradecopilot_eval.runner import RunConfig, run_case, write_json
from tradecopilot_eval.scoring import score_ticket, verifier_probes


class Trial(BaseModel):
    """A planned trial, identified before any model output is available."""

    scenario_id: str
    condition: MemoryCondition
    phase: Literal["screening", "ablation"]
    repetition: int


def plan_trials(suite: Suite, cases: list[Case]) -> list[Trial]:
    """Plan full-system screening and separate repeated four-condition trials."""
    screening = [
        Trial(
            scenario_id=case.scenario.scenario_id,
            condition="full",
            phase="screening",
            repetition=1,
        )
        for case in cases
    ]
    comparisons = [
        Trial(
            scenario_id=scenario, condition=condition, phase="ablation", repetition=rep
        )
        for scenario in suite.ablation_scenarios
        for rep in range(1, suite.repetitions + 1)
        for condition in suite.conditions
    ]
    randomizer = random.Random(suite.seed)
    randomizer.shuffle(screening)
    randomizer.shuffle(comparisons)
    return screening + comparisons


def validate_cases(cases: list[Case]) -> dict[str, Any]:
    """Validate independent ticket labels and direct claim probes before a run.

    Args:
        cases: Loaded case inputs and references.

    Returns:
        Case counts, separate direct-verifier observations, and validation errors.
        This checks software and labels, not human acceptance or model quality.
    """
    errors: list[str] = []
    verifier_mismatches: list[str] = []
    probes: dict[str, Any] = {}
    ticket_count = 0
    for case in cases:
        for candidate in case.reference.candidates:
            ticket_count += 1
            observed = score_ticket(candidate.tool_arguments, case.scenario)
            expected = candidate.expected
            if (
                observed["status"] != "scored"
                or observed["violates"] != (not expected.eligible)
                or observed["violation_codes"] != sorted(expected.violation_codes)
            ):
                errors.append(
                    f"{case.scenario.scenario_id}/{candidate.id}: ticket label mismatch"
                )
        observations = verifier_probes(case)
        probes[case.scenario.scenario_id] = observations
        for item in observations:
            if not item["matches_reference"]:
                verifier_mismatches.append(
                    f"{case.scenario.scenario_id}/{item['id']}: verifier mismatch"
                )
    return {
        "case_count": len(cases),
        "ticket_reference_count": ticket_count,
        "category_counts": dict(Counter(case.reference.category for case in cases)),
        "direct_verifier_probes": probes,
        "verifier_mismatches": verifier_mismatches,
        "errors": errors,
        "status": "passed" if not errors else "failed",
        "provenance_statuses": sorted(
            {case.reference.provenance_status for case in cases}
        ),
    }


def _check_destination(output: Path) -> None:
    project = Path(__file__).resolve().parents[3]
    if output.resolve().is_relative_to(project):
        raise ValueError("Keep run artifacts outside the Git repository.")
    if output.exists():
        raise FileExistsError(f"Output directory already exists: {output}")


async def run_suite(
    suite_path: Path,
    output: Path,
    config: RunConfig,
    judge_config: JudgeConfig,
    *,
    limit: int | None = None,
    allow_unreviewed: bool = False,
) -> list[RunRecord]:
    """Run a frozen plan and save every attempted trial, including failures.

    Args:
        suite_path: Schedule JSON and relative case paths.
        output: New directory outside the repository.
        config: Shared model settings; scripted mode uses no external model.
        judge_config: Shared judge configuration.
        limit: Optional smoke-test cap; the manifest marks such runs as partial.
        allow_unreviewed: Explicit opt-in to model calls on draft synthetic cases.

    Returns:
        Records for executed trials; all planned but omitted trials remain listed.

    Raises:
        ValueError: Labels, model identities, or the output path are invalid.
        PermissionError: Real calls or draft-case use was not enabled.
        FileExistsError: A previous output directory would be overwritten.
    """
    suite, cases = load_suite(suite_path)
    if config.mode != judge_config.mode or config.model_id != judge_config.agent_model:
        raise ValueError("Agent and judge run modes/model identifiers disagree.")
    if config.model_family != judge_config.agent_family:
        raise ValueError("Agent family differs from the judge configuration.")
    if config.mode == "model":
        if not config.allow_model_calls:
            raise PermissionError("Model calls require explicit enablement.")
        if not allow_unreviewed and any(
            case.reference.provenance_status != "reviewed" for case in cases
        ):
            raise PermissionError("Draft fixtures require --allow-unreviewed-fixtures.")
    validation = validate_cases(cases)
    if validation["errors"]:
        raise ValueError("Reference checks failed: " + "; ".join(validation["errors"]))
    trials = plan_trials(suite, cases)
    if limit is not None and limit < 1:
        raise ValueError("A smoke-test limit must be positive.")
    selected = trials if limit is None else trials[:limit]
    _check_destination(output)
    output.mkdir(parents=True)
    write_json(output / "validation.json", validation)
    write_json(
        output / "plan.json",
        {
            "suite": suite.model_dump(),
            "suite_sha256": file_digest(suite_path),
            "agent_settings": config.model_dump(),
            "judge_settings": judge_config.model_dump(),
            "planned_count": len(trials),
            "selected_count": len(selected),
            "partial": len(selected) < len(trials),
            "trials": [trial.model_dump() for trial in trials],
            "case_hashes": {
                case.scenario.scenario_id: {
                    "input_sha256": case.input_sha256,
                    "reference_sha256": case.reference_sha256,
                }
                for case in cases
            },
        },
    )
    by_id = {case.scenario.scenario_id: case for case in cases}
    records: list[RunRecord] = []
    for index, trial in enumerate(selected, start=1):
        record = await run_case(
            by_id[trial.scenario_id],
            output / "runs" / f"{index:04d}",
            config,
            condition=trial.condition,
            phase=trial.phase,
            repetition=trial.repetition,
            judge_config=judge_config,
        )
        records.append(record)
        write_json(
            output / "progress.json",
            {
                "completed_count": len(records),
                "selected_count": len(selected),
                "run_ids": [item.run_id for item in records],
            },
        )
    return records


def read_runs(directory: Path) -> list[RunRecord]:
    """Load saved runs in order and fail explicitly on absent or invalid records."""
    paths = sorted(directory.glob("runs/*/run.json"))
    if not paths:
        raise ValueError("No runs/*/run.json records were found.")
    return [
        RunRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))
        for path in paths
    ]
