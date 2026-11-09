"""Check report denominators, missing measurements, and offline-control limits."""

import csv
import json
from pathlib import Path
from typing import Any, Literal

import pytest
from tradecopilot_agent.memory import MemoryCondition
from tradecopilot_eval.judge import DIMENSIONS
from tradecopilot_eval.records import Proposal, RunRecord, Usage
from tradecopilot_eval.report import build_report, write_report


def _judge(score: int = 4, *, scripted: bool = False) -> dict[str, Any]:
    return {
        "status": "ok",
        "config": {"mode": "scripted" if scripted else "model"},
        "scores": {dimension: {"score": score} for dimension in DIMENSIONS},
        "attempts": [
            {
                "latency_seconds": 0.25,
                "usage": {"input_tokens": 20, "output_tokens": 5, "total_tokens": 25},
            }
        ],
    }


def _run(
    run_id: str,
    *,
    condition: MemoryCondition = "full",
    phase: Literal["screening", "ablation", "single"] = "ablation",
    mode: Literal["scripted", "model"] = "model",
    repetition: int = 1,
) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        scenario_id="PORT-01",
        condition=condition,
        phase=phase,
        repetition=repetition,
        mode=mode,
        model_id="example:agent",
        model_family="example",
        status="ok",
        metadata={
            "input_sha256": "inputs",
            "reference_sha256": "reference",
            "code_sha256": "code",
            "agent_prompt_sha256": "prompt",
            "settings": {"max_output_tokens": 4096},
        },
    )


def test_rates_keep_missing_and_conditional_denominators() -> None:
    """Count failed runs and unknown observations without replacing them with zero."""
    first, second, failed = (_run(name) for name in ("one", "two", "failed"))
    first.scores = {
        "initial_violation": True,
        "task_success": True,
        "final_ticket": {"violates": False},
        "attempts": [
            {"violates": True, "blocked": True},
            {"violates": False, "blocked": False},
        ],
        "answer_claim_observations": [
            {"expected": "contradicted", "observed": "contradicted"},
            {"expected": "supported", "observed": None},
        ],
    }
    second.scores = {
        "initial_violation": False,
        "task_success": False,
        "attempts": [
            {"violates": True, "blocked": None},
            {"violates": False, "blocked": True},
            {"violates": None, "blocked": None},
        ],
        "answer_claim_observations": [
            {"expected": "contradicted", "observed": "unchecked"},
            {"expected": "supported", "observed": "contradicted"},
        ],
    }
    first.judge = _judge()
    second.judge = {"status": "judge_error", "scores": None}
    failed.status = "agent_error"
    first.usage = Usage(total_tokens=100, cost_usd=0.001, elapsed_seconds=2)
    second.usage = Usage(elapsed_seconds=3)
    row = build_report([first, second, failed])["by_condition"][0]
    assert row["runs"] == 3 and row["failed_runs"] == 1
    assert row["initial_violation"] == {
        "numerator": 1,
        "observed": 2,
        "total": 3,
        "missing": 1,
        "rate": 0.5,
    }
    assert row["correct_block"] == {
        "numerator": 1,
        "observed": 1,
        "total": 2,
        "missing": 1,
        "rate": 1.0,
    }
    assert row["false_block"]["rate"] == 0.5
    assert row["attempts_unscorable"] == 1
    assert row["task_success"]["missing"] == 1
    assert row["judge_errors"] == 1 and row["judge_unscored"] == 1
    assert row["quality"]["reasoning"]["count"] == 1
    assert row["quality"]["reasoning"]["missing"] == 2
    verification = row["verification"]
    assert verification["matches_reference"]["rate"] == pytest.approx(1 / 3)
    assert verification["matches_reference"]["missing"] == 1
    assert verification["false_claim_detected"]["rate"] == 0.5
    assert verification["true_claim_false_alarm"]["missing"] == 1
    assert row["agent_usage"]["total_tokens"]["mean"] == 100
    assert row["agent_usage"]["cost_usd"]["missing"] == 2
    assert row["agent_usage"]["elapsed_seconds"]["mean"] == 2.5
    assert row["agent_usage"]["elapsed_seconds"]["missing"] == 1
    assert row["judge_usage"]["total_tokens"]["sum"] == 25
    assert row["judge_usage"]["cost_usd"]["mean"] is None


def test_screening_and_repeated_ablation_are_not_pooled() -> None:
    """Keep screening, comparisons, model IDs, and conditions in distinct groups."""
    screening = _run("screen", phase="screening")
    full = _run("full")
    no_memory = _run("none", condition="none")
    other_model = _run("different")
    other_model.model_id = "example:different-agent"
    report = build_report([screening, full, no_memory, other_model])
    assert len(report["by_condition"]) == 4
    assert len(report["by_scenario"]) == 4
    assert "initial_violation" not in report["by_mode"][0]


def test_scripted_scores_never_become_quality_or_memory_results() -> None:
    """Exclude fixed judge threes and any scripted task labels from research scores."""
    control = _run("control", mode="scripted")
    control.judge = _judge(3, scripted=True)
    control.scores = {"initial_violation": True, "task_success": True}
    report = build_report([control])
    row = report["by_condition"][0]
    assert "Offline controls only" in report["interpretation"]
    assert row["initial_violation"]["numerator"] == 1
    assert row["quality"]["profile_fit"]["mean"] is None
    assert row["task_success"]["observed"] == 0
    assert row["scripted_quality_excluded"] == 1
    assert report["paired_ablation"] == []
    assert report["scripted_ablation_runs_excluded"] == 1
    control.mode = "model"
    assert (
        build_report([control])["by_condition"][0]["quality"]["reasoning"]["mean"]
        is None
    )


def test_repeated_quality_reports_variation_and_errors() -> None:
    """Calculate sample variation only from observed scores, retaining failed trials."""
    records = [_run(f"repeat-{number}", repetition=number) for number in (1, 2, 3)]
    records[0].judge = _judge(3)
    records[1].judge = _judge(5)
    records[2].judge = {"status": "judge_error", "scores": None}
    row = build_report(records)["by_scenario"][0]
    dimension = row["quality"]["evidence_coverage"]
    assert row["repetitions"] == [1, 2, 3]
    assert dimension["count"] == 2 and dimension["missing"] == 1
    assert dimension["mean"] == 4
    assert dimension["stdev"] == pytest.approx(2**0.5)


def test_paired_differences_require_matching_metadata() -> None:
    """Compare matching scenario/repetition pairs and preserve missing metrics."""
    full, none = _run("full"), _run("none", condition="none")
    full.scores = {"initial_violation": False, "task_success": True}
    none.scores = {"initial_violation": True, "task_success": False}
    full.judge, none.judge = _judge(5), _judge(3)
    pairs = build_report([full, none])["paired_ablation"]
    pair = next(item for item in pairs if item["condition"] == "none")
    assert pair["status"] == "paired"
    assert pair["metrics"]["initial_violation"]["difference"] == 1
    assert pair["metrics"]["task_success"]["difference"] == -1
    assert pair["metrics"]["reasoning"]["difference"] == -2
    assert pair["metrics"]["cost_usd"]["difference"] is None
    assert sum(item["status"] == "missing_pair" for item in pairs) == 2

    none.metadata["input_sha256"] = "different-inputs"
    pair = build_report([full, none])["paired_ablation"][0]
    assert pair["status"] == "mismatched_inputs" and pair["metrics"] == {}
    none.metadata = {}
    pair = build_report([full, none])["paired_ablation"][0]
    assert pair["status"] == "unverified_settings" and pair["metrics"] == {}


def test_duplicate_pair_is_not_arbitrarily_selected() -> None:
    """Retain ambiguous paired observations without picking one run to compare."""
    full = _run("full")
    one, two = _run("none-one", condition="none"), _run("none-two", condition="none")
    pairs = build_report([full, one, two])["paired_ablation"]
    assert pairs[0]["status"] == "ambiguous_pair"
    assert pairs[0]["metrics"] == {}


def test_zero_denominators_and_partial_judge_usage_stay_null() -> None:
    """Keep unobserved rates and incomplete provider measurements unscored."""
    record = _run("no-observations")
    record.judge = _judge()
    record.judge["attempts"].append({"latency_seconds": 0.5, "usage": None})
    row = build_report([record])["by_condition"][0]
    assert row["initial_violation"]["rate"] is None
    assert row["correct_block"]["total"] == 0
    assert row["correct_block"]["rate"] is None
    assert row["agent_usage"]["cost_usd"]["sum"] is None
    assert row["judge_usage"]["total_tokens"]["sum"] is None
    assert row["judge_usage"]["elapsed_seconds"]["sum"] == 0.75
    record.judge["cost_usd"] = 0.003
    row = build_report([record])["by_condition"][0]
    assert row["judge_usage"]["cost_usd"]["sum"] == 0.003


def test_report_files_preserve_inputs_and_blank_missing_csv(tmp_path: Path) -> None:
    """Write derived reports without changing run records or unrelated files."""
    record = _run("one", mode="scripted")
    before = record.model_dump_json()
    existing = tmp_path / "original-run.json"
    existing.write_text(before, encoding="utf-8")
    write_report([record], tmp_path)
    assert record.model_dump_json() == before
    assert existing.read_text(encoding="utf-8") == before
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["input_run_count"] == 1
    assert "Offline controls only" in (tmp_path / "report.md").read_text(
        encoding="utf-8"
    )
    with (tmp_path / "runs.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]["cost_usd"] == ""
    assert rows[0]["task_success"] == ""
    assert rows[0]["elapsed_seconds"] == ""


def test_duplicate_ids_rejected_and_empty_report_allowed() -> None:
    """Avoid counting a trial twice and handle an empty input without fake rates."""
    record = _run("same")
    with pytest.raises(ValueError, match="Duplicate run_id"):
        build_report([record, record])
    empty = build_report([])
    assert empty["input_run_count"] == 0
    assert empty["by_condition"] == []
    assert empty["paired_ablation"] == []


def test_capture_failures_remain_counted_by_type() -> None:
    """Expose capture gaps even when the agent returned readable final text."""
    record = _run("capture-failed")
    record.proposals = [
        Proposal(
            call_id="a",
            message_index=1,
            arguments={},
            capture_error="missing_tool_artifact",
        ),
        Proposal(
            call_id="b",
            message_index=2,
            arguments={},
            capture_error="missing_or_duplicate_tool_result",
        ),
    ]
    row = build_report([record])["by_condition"][0]
    assert row["capture_errors"] == 2
    assert row["runs_with_capture_errors"] == 1
    assert row["capture_errors_by_type"] == {
        "missing_tool_artifact": 1,
        "missing_or_duplicate_tool_result": 1,
    }


def test_saved_plan_distinguishes_partial_selection_and_missing_runs(
    tmp_path: Path,
) -> None:
    """Use the frozen plan to distinguish a smoke test from an incomplete run."""
    first, second = _run("one"), _run("two", condition="none")
    keys = ("scenario_id", "condition", "phase", "repetition")
    trials = [{key: getattr(record, key) for key in keys} for record in (first, second)]
    plan = {"planned_count": 2, "selected_count": 1, "trials": trials}
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    write_report([first], tmp_path)
    report_path = tmp_path / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["plan_coverage"]["status"] == "partial_selection"
    assert report["plan_coverage"]["unselected_count"] == 1
    assert "partial_selection" in (tmp_path / "report.md").read_text(encoding="utf-8")
    plan["selected_count"] = 2
    path.write_text(json.dumps(plan), encoding="utf-8")
    write_report([first], tmp_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["plan_coverage"]["status"] == "incomplete_records"
    assert report["plan_coverage"]["missing_selected_count"] == 1
    second.status = "timeout"
    write_report([first, second], tmp_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["plan_coverage"]["status"] == "complete"
    assert report["by_mode"][0]["failed_runs"] == 1
