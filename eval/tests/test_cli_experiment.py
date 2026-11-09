"""Exercise the command workflow, frozen schedule, and external-call gates."""

import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from tradecopilot_eval.cli import main
from tradecopilot_eval.experiment import plan_trials, read_runs, validate_cases
from tradecopilot_eval.reference import file_digest, load_case, load_suite
from tradecopilot_eval.runner import RunConfig, run_case

_EVAL = Path(__file__).resolve().parents[1]
_SUITE = _EVAL / "suites/pilot.json"
_DEV01 = _EVAL / "scenarios/dev_01_position_cap"


def test_schedule_is_fixed_balanced_and_separates_phases() -> None:
    """Keep the ten screening trials distinct from the repeated comparison."""
    suite, cases = load_suite(_SUITE)
    planned = plan_trials(suite, cases)
    assert planned == plan_trials(suite, cases)
    assert len(planned) == 46
    assert Counter(item.phase for item in planned) == {"screening": 10, "ablation": 36}
    comparisons = [item for item in planned if item.phase == "ablation"]
    assert Counter(item.condition for item in comparisons) == {
        "none": 9,
        "prose": 9,
        "structured": 9,
        "full": 9,
    }
    assert {item.scenario_id for item in comparisons} == set(suite.ablation_scenarios)
    assert validate_cases(cases)["status"] == "passed"


def test_wrong_reference_label_is_rejected() -> None:
    """A contradictory gold label cannot pass just because it is in the file."""
    case = load_case(_DEV01)
    case.reference.candidates[0].expected.eligible = True
    result = validate_cases([case])
    assert result["status"] == "failed"
    assert result["errors"]


def test_cli_rehearsal_report_review_and_blank_agreement(tmp_path: Path) -> None:
    """Produce artifacts end to end while treating blank ratings as missing."""
    output = tmp_path / "experiment"
    review = tmp_path / "review"
    assert main(["validate", "--suite", str(_SUITE)]) == 0
    assert main(["run", "--output", str(output), "--limit", "2"]) == 0
    records = read_runs(output)
    assert len(records) == 2
    assert all(item.status == "ok" for item in records)
    assert all(
        item.mode == "scripted" and item.scores["task_success"] is None
        for item in records
    )
    plan = json.loads((output / "plan.json").read_text())
    assert plan["partial"] is True
    assert plan["planned_count"] == 46 and plan["selected_count"] == 2
    assert main(["report", "--input", str(output)]) == 0
    assert main(["review", "--input", str(output), "--output", str(review)]) == 0
    assert "condition" not in (review / "ratings.csv").read_text().splitlines()[0]
    agreement = review / "agreement.json"
    assert (
        main(
            [
                "agreement",
                "--input",
                str(output),
                "--reviews",
                str(review / "ratings.csv"),
                "--output",
                str(agreement),
            ]
        )
        == 0
    )
    data = json.loads(agreement.read_text())
    assert data["comparison_kind"] == "scripted_control"
    assert all(
        item["pairs"] == 0 and item["exact_agreement"] is None
        for item in data["dimensions"].values()
    )
    assert main(["run", "--output", str(output), "--limit", "2"]) == 2
    assert len(read_runs(output)) == 2


def test_cli_model_calls_require_explicit_enablement(tmp_path: Path) -> None:
    """Reject a configured model run before making a directory or provider call."""
    output = tmp_path / "forbidden"
    common = [
        "run",
        "--mode",
        "model",
        "--output",
        str(output),
        "--agent-model",
        "anthropic:claude-example",
        "--agent-family",
        "claude",
        "--judge-model",
        "openai:gpt-example",
        "--judge-family",
        "openai",
    ]
    assert main(common) == 2
    assert not output.exists()
    assert main([*common, "--allow-model-calls"]) == 2
    assert not output.exists()


def test_calibration_is_an_unassessed_control_without_models(tmp_path: Path) -> None:
    """Run four predefined responses through judge plumbing without claiming quality."""
    output = tmp_path / "calibration"
    assert main(["calibrate", "--output", str(output)]) == 0
    report = json.loads((output / "calibration.json").read_text())
    assert report["reference_status"] == "provisional_unreviewed"
    assert len(report["assessments"]) == 4
    assert all(item["status"] == "scripted_control" for item in report["assessments"])


def test_saved_input_bytes_match_recorded_hashes(tmp_path: Path) -> None:
    """Preserve exact source bytes even when the source JSON uses CRLF."""
    original = tmp_path / "case"
    original.mkdir()
    for name in ("inputs.json", "reference.json"):
        original.joinpath(name).write_bytes(
            _DEV01.joinpath(name).read_bytes().replace(b"\n", b"\r\n")
        )
    case = load_case(original)
    output = tmp_path / "run"
    record = asyncio.run(run_case(case, output, RunConfig()))
    assert record.status == "ok"
    assert file_digest(output / "inputs.json") == record.metadata["input_sha256"]
    assert file_digest(output / "reference.json") == record.metadata["reference_sha256"]


def test_future_and_conflicting_reference_evidence_fail_validation(
    tmp_path: Path,
) -> None:
    """Exclude future truth and reused evidence IDs with inconsistent payloads."""
    original = tmp_path / "case"
    original.mkdir()
    inputs: dict[str, Any] = json.loads((_DEV01 / "inputs.json").read_text())
    reference: dict[str, Any] = json.loads((_DEV01 / "reference.json").read_text())
    inputs["tool_fixtures"][0]["output"]["evidence"][0]["published_at"] = (
        "2026-09-16T00:00:00Z"
    )
    (original / "inputs.json").write_text(json.dumps(inputs))
    (original / "reference.json").write_text(json.dumps(reference))
    with pytest.raises(ValueError, match="unavailable"):
        load_case(original)
    inputs = json.loads((_DEV01 / "inputs.json").read_text())
    reference["reference_evidence"] = [
        inputs["tool_fixtures"][0]["output"]["evidence"][0]
    ]
    reference["reference_evidence"][0]["payload"]["price"] = 999
    (original / "inputs.json").write_bytes((_DEV01 / "inputs.json").read_bytes())
    (original / "reference.json").write_text(json.dumps(reference))
    with pytest.raises(ValueError, match="disagree"):
        load_case(original)


def test_matcher_regressions_are_results_not_invalid_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep verifier mistakes measurable instead of aborting the experiment."""
    monkeypatch.setattr(
        "tradecopilot_eval.scoring.match_claims",
        lambda *args, **kwargs: [{"verdict": "unchecked"}],
    )
    _, cases = load_suite(_SUITE)
    result = validate_cases(cases)
    assert result["status"] == "passed"
    assert result["verifier_mismatches"]


def test_judge_errors_return_failure_and_keep_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A completed agent does not hide a failed judge from command automation."""

    class FailedJudge:
        async def __call__(self, system_prompt: str, user_json: str) -> str:
            raise RuntimeError("planned judge outage")

    monkeypatch.setattr("tradecopilot_eval.runner.ScriptedJudgeTransport", FailedJudge)
    monkeypatch.setattr("tradecopilot_eval.cli.ScriptedJudgeTransport", FailedJudge)
    output = tmp_path / "runs"
    assert main(["run", "--limit", "1", "--output", str(output)]) == 1
    record = read_runs(output)[0]
    assert record.status == "ok"
    assert record.judge is not None and record.judge["status"] == "judge_error"
    assert record.judge["scores"] is None
    calibration = tmp_path / "calibration"
    assert main(["calibrate", "--output", str(calibration)]) == 1
    result = json.loads((calibration / "calibration.json").read_text())
    assert all(item["status"] == "judge_error" for item in result["assessments"])
