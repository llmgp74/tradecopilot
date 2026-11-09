"""Summarize saved trials with explicit missing values and control-run labels."""

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, stdev
from typing import Any

from tradecopilot_eval.judge import DIMENSIONS
from tradecopilot_eval.records import RunRecord

_PAIR_METADATA = (
    "input_sha256",
    "reference_sha256",
    "code_sha256",
    "agent_prompt_sha256",
    "settings",
)
_COMPARISON_CONDITIONS = ("none", "prose", "structured")


def _boolean(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) else None


def _difference(left: float | None, right: float | None) -> float | None:
    return right - left if left is not None and right is not None else None


def _rate(values: list[bool | None]) -> dict[str, Any]:
    observed = [value for value in values if value is not None]
    numerator = sum(observed)
    return {
        "numerator": numerator,
        "observed": len(observed),
        "total": len(values),
        "missing": len(values) - len(observed),
        "rate": numerator / len(observed) if observed else None,
    }


def _statistics(values: list[float | None]) -> dict[str, Any]:
    observed = [value for value in values if value is not None]
    return {
        "count": len(observed),
        "total": len(values),
        "missing": len(values) - len(observed),
        "sum": sum(observed) if observed else None,
        "mean": mean(observed) if observed else None,
        "stdev": stdev(observed) if len(observed) > 1 else None,
        "min": min(observed) if observed else None,
        "max": max(observed) if observed else None,
    }


def _items(value: Any) -> list[dict[str, Any]]:
    return (
        [item for item in value if isinstance(item, dict)]
        if isinstance(value, list)
        else []
    )


def _control(record: RunRecord) -> bool:
    judge_config = (record.judge or {}).get("config", {})
    return record.mode == "scripted" or (
        isinstance(judge_config, dict) and judge_config.get("mode") == "scripted"
    )


def _quality(record: RunRecord, dimension: str) -> float | None:
    if _control(record) or record.status != "ok":
        return None
    judge = record.judge or {}
    config = judge.get("config", {})
    scores = judge.get("scores", {})
    if (
        judge.get("status") != "ok"
        or not isinstance(config, dict)
        or config.get("mode") != "model"
        or not isinstance(scores, dict)
    ):
        return None
    item = scores.get(dimension)
    value = _number(item.get("score")) if isinstance(item, dict) else None
    return value if value is not None and 1 <= value <= 5 else None


def _task_success(record: RunRecord) -> bool | None:
    if _control(record) or record.status != "ok":
        return None
    return _boolean(record.scores.get("task_success"))


def _final_violation(record: RunRecord) -> bool | None:
    ticket = record.scores.get("final_ticket")
    return _boolean(ticket.get("violates")) if isinstance(ticket, dict) else None


def _judge_usage(record: RunRecord, key: str) -> float | None:
    if key == "cost_usd":
        return _number((record.judge or {}).get("cost_usd"))
    attempts = _items((record.judge or {}).get("attempts"))
    values: list[float | None] = []
    for attempt in attempts:
        if key == "elapsed_seconds":
            values.append(_number(attempt.get("latency_seconds")))
        else:
            usage = attempt.get("usage")
            values.append(_number(usage.get(key)) if isinstance(usage, dict) else None)
    if not values or any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def _summary(records: list[RunRecord]) -> dict[str, Any]:
    attempts = [
        item for record in records for item in _items(record.scores.get("attempts"))
    ]
    invalid = [item for item in attempts if item.get("violates") is True]
    valid = [item for item in attempts if item.get("violates") is False]
    claims = [
        item
        for record in records
        for item in _items(record.scores.get("answer_claim_observations"))
    ]
    matched: list[bool | None] = []
    false_claims: list[bool | None] = []
    true_claims: list[bool | None] = []
    for item in claims:
        observed, expected = item.get("observed"), item.get("expected")
        matched.append(observed == expected if observed is not None else None)
        value = observed == "contradicted" if observed is not None else None
        if expected == "contradicted":
            false_claims.append(value)
        if expected == "supported":
            true_claims.append(value)
    judge_statuses = Counter(
        str(record.judge.get("status", "unscored")) if record.judge else "unscored"
        for record in records
    )
    return {
        "runs": len(records),
        "statuses": dict(sorted(Counter(record.status for record in records).items())),
        "failed_runs": sum(record.status != "ok" for record in records),
        "tool_errors": sum(len(record.tool_errors) for record in records),
        "runs_with_tool_errors": sum(bool(record.tool_errors) for record in records),
        "capture_errors": sum(
            proposal.capture_error is not None
            for record in records
            for proposal in record.proposals
        ),
        "runs_with_capture_errors": sum(
            any(proposal.capture_error is not None for proposal in record.proposals)
            for record in records
        ),
        "capture_errors_by_type": dict(
            sorted(
                Counter(
                    proposal.capture_error
                    for record in records
                    for proposal in record.proposals
                    if proposal.capture_error is not None
                ).items()
            )
        ),
        "judge_statuses": dict(sorted(judge_statuses.items())),
        "judge_errors": judge_statuses["judge_error"],
        "judge_unscored": judge_statuses["unscored"],
        "scripted_quality_excluded": sum(_control(record) for record in records),
        "no_initial_proposal": sum(
            not record.initial_proposal_ids for record in records
        ),
        "initial_violation": _rate(
            [_boolean(record.scores.get("initial_violation")) for record in records]
        ),
        "attempts_total": len(attempts),
        "attempts_unscorable": sum(item.get("violates") is None for item in attempts),
        "correct_block": _rate([_boolean(item.get("blocked")) for item in invalid]),
        "false_block": _rate([_boolean(item.get("blocked")) for item in valid]),
        "final_ticket_violation": _rate(
            [_final_violation(record) for record in records]
        ),
        "task_success": _rate([_task_success(record) for record in records]),
        "outcomes": dict(
            sorted(
                Counter(
                    "scripted_control"
                    if _control(record)
                    else str(record.scores.get("outcome", "unscored"))
                    for record in records
                ).items()
            )
        ),
        "verification": {
            "match_rule": "exact_normalized_claim_text",
            "matches_reference": _rate(matched),
            "false_claim_detected": _rate(false_claims),
            "true_claim_false_alarm": _rate(true_claims),
        },
        "quality": {
            dimension: _statistics([_quality(record, dimension) for record in records])
            for dimension in DIMENSIONS
        },
        "agent_usage": {
            key: _statistics(
                [_number(getattr(record.usage, key)) for record in records]
            )
            for key in (
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "cost_usd",
                "elapsed_seconds",
            )
        },
        "judge_usage": {
            key: _statistics([_judge_usage(record, key) for record in records])
            for key in (
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "elapsed_seconds",
                "cost_usd",
            )
        },
        "repetitions": sorted({record.repetition for record in records}),
    }


def _grouped(
    records: list[RunRecord], *, scenario: bool = False
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, ...], list[RunRecord]] = defaultdict(list)
    for record in records:
        key: tuple[str, ...] = (
            record.mode,
            record.model_id,
            record.phase,
            record.condition,
        )
        if scenario:
            key += (record.scenario_id,)
        groups[key].append(record)
    rows = []
    for key, members in sorted(groups.items()):
        row = dict(
            zip(("mode", "model_id", "phase", "condition"), key[:4], strict=True)
        )
        if scenario:
            row["scenario_id"] = key[4]
        rows.append({**row, **_summary(members)})
    return rows


def _pair_values(record: RunRecord) -> dict[str, float | None]:
    return {
        "initial_violation": _number(int(value))
        if (value := _boolean(record.scores.get("initial_violation"))) is not None
        else None,
        "final_ticket_violation": float(value)
        if (value := _final_violation(record)) is not None
        else None,
        "task_success": float(value)
        if (value := _task_success(record)) is not None
        else None,
        **{dimension: _quality(record, dimension) for dimension in DIMENSIONS},
        "total_tokens": _number(record.usage.total_tokens),
        "cost_usd": _number(record.usage.cost_usd),
        "elapsed_seconds": _number(record.usage.elapsed_seconds),
    }


def _paired(records: list[RunRecord]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, int], dict[str, list[RunRecord]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for record in records:
        if record.mode == "model" and record.phase == "ablation":
            groups[record.model_id, record.scenario_id, record.repetition][
                record.condition
            ].append(record)
    contrasts = []
    for (model_id, scenario_id, repetition), members in sorted(groups.items()):
        for condition in _COMPARISON_CONDITIONS:
            full = members.get("full", [])
            other = members.get(condition, [])
            row: dict[str, Any] = {
                "model_id": model_id,
                "scenario_id": scenario_id,
                "repetition": repetition,
                "condition": condition,
                "reference_condition": "full",
                "difference": "condition_minus_full",
                "full_run_ids": [record.run_id for record in full],
                "condition_run_ids": [record.run_id for record in other],
                "status": "missing_pair",
                "missing_metadata": [],
                "mismatched_metadata": [],
                "metrics": {},
            }
            if len(full) > 1 or len(other) > 1:
                row["status"] = "ambiguous_pair"
            elif len(full) == len(other) == 1:
                left, right = full[0], other[0]
                missing = [
                    key
                    for key in _PAIR_METADATA
                    if left.metadata.get(key) is None or right.metadata.get(key) is None
                ]
                mismatch = [
                    key
                    for key in _PAIR_METADATA
                    if key not in missing and left.metadata[key] != right.metadata[key]
                ]
                row["missing_metadata"] = missing
                row["mismatched_metadata"] = mismatch
                row["status"] = (
                    "mismatched_inputs"
                    if mismatch
                    else "unverified_settings"
                    if missing
                    else "paired"
                )
                if row["status"] == "paired":
                    full_values, other_values = _pair_values(left), _pair_values(right)
                    row["metrics"] = {
                        name: {
                            "full": full_value,
                            "condition": other_values[name],
                            "difference": _difference(full_value, other_values[name]),
                        }
                        for name, full_value in full_values.items()
                    }
            contrasts.append(row)
    return contrasts


def build_report(records: list[RunRecord]) -> dict[str, Any]:
    """Build grouped summaries while keeping controls and missing data separate.

    Args:
        records: Saved run records, including failed trials. A trial with no
            record cannot be counted; the runner must save every scheduled run.

    Returns:
        JSON-compatible summaries, per-scenario variation, and paired contrasts.
        Rates use observed denominators and also show total and missing counts.

    Raises:
        ValueError: Duplicate run IDs would count a trial more than once.
    """
    ids = [record.run_id for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate run_id in report inputs.")
    modes = sorted({record.mode for record in records})
    return {
        "schema_version": 1,
        "input_run_count": len(records),
        "modes": modes,
        "interpretation": (
            "Offline controls only; no agent quality or memory-effect conclusion."
            if modes == ["scripted"]
            else "Scripted controls are excluded from quality and memory contrasts; "
            "model results require reference review."
        ),
        "notes": [
            "Screening and ablation are summarized separately.",
            "Rates show observed, total, and missing counts; "
            "missing values are not zero.",
            "Correct/false-block denominators are labeled invalid/valid attempts.",
            "No exact claim match may mean the answer corrected or omitted that claim.",
            "Quality excludes scripted judge controls and failed agent runs.",
            "Standard deviations are sample deviations and need two observations.",
            "Paired differences are condition minus full; no significance is inferred.",
        ],
        "by_mode": [
            {
                "mode": mode,
                "runs": sum(record.mode == mode for record in records),
                "failed_runs": sum(
                    record.mode == mode and record.status != "ok" for record in records
                ),
                "judge_errors": sum(
                    record.mode == mode
                    and (record.judge or {}).get("status") == "judge_error"
                    for record in records
                ),
            }
            for mode in modes
        ],
        "by_condition": _grouped(records),
        "by_scenario": _grouped(records, scenario=True),
        "paired_ablation": _paired(records),
        "scripted_ablation_runs_excluded": sum(
            record.mode == "scripted" and record.phase == "ablation"
            for record in records
        ),
        "run_ids": ids,
    }


def _format_rate(value: dict[str, Any]) -> str:
    observed = value["observed"]
    return (
        f"{value['numerator']}/{observed} (missing {value['missing']}/{value['total']})"
        if observed
        else f"unscored (missing {value['missing']}/{value['total']})"
    )


def _format_statistics(value: dict[str, Any], *, total: bool = False) -> str:
    count, size = value["count"], value["total"]
    if count == 0:
        return f"unmeasured (0/{size})"
    number = value["sum"] if total else value["mean"]
    spread = value["stdev"]
    suffix = f" +/- {spread:.3g}" if not total and spread is not None else ""
    return f"{number:.4g}{suffix} ({count}/{size})"


def _table(
    lines: list[str], title: str, headers: list[str], rows: list[list[Any]]
) -> None:
    lines.extend(["", f"## {title}", ""])
    for row in [headers, ["---"] * len(headers), *rows]:
        cells = [str(value).replace("|", "\\|").replace("\n", " ") for value in row]
        lines.append("| " + " | ".join(cells) + " |")


def _markdown(report: dict[str, Any]) -> str:
    lines = ["# Evaluation report", "", report["interpretation"], ""]
    lines.append(f"Runs recorded: {report['input_run_count']}.")
    coverage = report.get("plan_coverage")
    if isinstance(coverage, dict) and coverage["status"] != "unknown":
        lines.extend(
            [
                "",
                f"Plan coverage: {coverage['status']}. "
                f"Planned {coverage['planned_count']}; "
                f"selected {coverage['selected_count']}; "
                f"recorded {coverage['recorded_count']}; "
                f"missing selected trials {coverage['missing_selected_count']}.",
                "A complete record set includes failed trials; it does not mean every "
                "trial succeeded.",
            ]
        )
    else:
        lines.extend(
            ["", "Plan coverage is unknown because no plan.json was supplied."]
        )
    groups = report["by_condition"]
    labels = ["Mode", "Model", "Phase", "Condition"]

    def prefix(row: dict[str, Any]) -> list[str]:
        return [str(row[key]) for key in ("mode", "model_id", "phase", "condition")]

    _table(
        lines,
        "Conditions",
        [*labels, "Runs", "Failed", "Initial violations", "Task success"],
        [
            [
                *prefix(row),
                row["runs"],
                row["failed_runs"],
                _format_rate(row["initial_violation"]),
                _format_rate(row["task_success"]),
            ]
            for row in groups
        ],
    )
    _table(
        lines,
        "Rule checks",
        [*labels, "Correct blocks", "False blocks", "Final violations"],
        [
            [
                *prefix(row),
                _format_rate(row["correct_block"]),
                _format_rate(row["false_block"]),
                _format_rate(row["final_ticket_violation"]),
            ]
            for row in groups
        ],
    )
    _table(
        lines,
        "Verification observations",
        [
            *labels,
            "Matched references",
            "False claims detected",
            "True-claim false alarms",
        ],
        [
            [
                *prefix(row),
                *[
                    _format_rate(row["verification"][key])
                    for key in (
                        "matches_reference",
                        "false_claim_detected",
                        "true_claim_false_alarm",
                    )
                ],
            ]
            for row in groups
        ],
    )
    _table(
        lines,
        "Operational measurements",
        [
            *labels,
            "Agent tokens",
            "Agent USD sum",
            "Agent seconds",
            "Judge tokens",
            "Judge seconds",
            "Judge USD sum",
        ],
        [
            [
                *prefix(row),
                _format_statistics(row["agent_usage"]["total_tokens"]),
                _format_statistics(row["agent_usage"]["cost_usd"], total=True),
                _format_statistics(row["agent_usage"]["elapsed_seconds"]),
                _format_statistics(row["judge_usage"]["total_tokens"]),
                _format_statistics(row["judge_usage"]["elapsed_seconds"]),
                _format_statistics(row["judge_usage"]["cost_usd"], total=True),
            ]
            for row in groups
        ],
    )
    model_groups = [row for row in groups if row["mode"] == "model"]
    if model_groups:
        _table(
            lines,
            "Recommendation quality",
            [*labels, *DIMENSIONS],
            [
                [
                    *prefix(row),
                    *[
                        _format_statistics(row["quality"][dimension])
                        for dimension in DIMENSIONS
                    ],
                ]
                for row in model_groups
            ],
        )
    _table(
        lines,
        "Scenarios",
        [
            *labels,
            "Case",
            "Runs",
            "Initial violations",
            "Capture errors",
            "Judge errors",
        ],
        [
            [
                *prefix(row),
                row["scenario_id"],
                row["runs"],
                _format_rate(row["initial_violation"]),
                row["capture_errors"],
                row["judge_errors"],
            ]
            for row in report["by_scenario"]
        ],
    )
    lines.extend(["", "## Reading the numbers", ""])
    lines.extend(f"- {note}" for note in report["notes"])
    lines.extend(
        [
            "",
            "Measurement cells show mean +/- sample deviation "
            "and observed/total counts.",
            "USD sums cover observed costs only. Unpriced calls remain unmeasured.",
            "report.json also contains per-scenario variation and paired differences.",
            "runs.csv lists individual trial statuses and observed measurements.",
            "",
        ]
    )
    return "\n".join(lines)


def _plan_coverage(records: list[RunRecord], output_dir: Path) -> dict[str, Any]:
    path = output_dir / "plan.json"
    if not path.exists():
        return {"status": "unknown", "recorded_count": len(records)}
    plan = json.loads(path.read_text(encoding="utf-8"))
    planned, selected = plan.get("planned_count"), plan.get("selected_count")
    trials = plan.get("trials")
    if (
        type(planned) is not int
        or type(selected) is not int
        or not 0 <= selected <= planned
        or not isinstance(trials, list)
        or len(trials) != planned
    ):
        raise ValueError("Invalid trial counts in plan.json.")
    keys = ("scenario_id", "condition", "phase", "repetition")
    try:
        expected = Counter(
            tuple(trial[key] for key in keys) for trial in trials[:selected]
        )
    except (KeyError, TypeError) as exc:
        raise ValueError("Invalid trial entries in plan.json.") from exc
    observed = Counter(
        tuple(getattr(record, key) for key in keys) for record in records
    )
    missing = sum((expected - observed).values())
    unexpected = sum((observed - expected).values())
    status = (
        "inconsistent_records"
        if missing and unexpected
        else "incomplete_records"
        if missing
        else "unexpected_records"
        if unexpected
        else "partial_selection"
        if selected < planned
        else "complete"
    )
    return {
        "status": status,
        "planned_count": planned,
        "selected_count": selected,
        "recorded_count": len(records),
        "missing_selected_count": missing,
        "unselected_count": planned - selected,
        "unexpected_record_count": unexpected,
    }


def write_report(records: list[RunRecord], output_dir: Path) -> None:
    """Write derived JSON, Markdown, and CSV summaries without editing run records.

    Args:
        records: Saved records to summarize, including failures.
        output_dir: Report directory; report.json, report.md, and runs.csv are
            replaced on rerun. No other files are written or removed.

    Raises:
        ValueError: Duplicate run IDs or an invalid plan manifest are supplied.
        OSError: The output directory or report files cannot be written.
    """
    report = build_report(records)
    report["plan_coverage"] = _plan_coverage(records, output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(_markdown(report), encoding="utf-8")
    fields = [
        "run_id",
        "scenario_id",
        "mode",
        "model_id",
        "phase",
        "condition",
        "repetition",
        "status",
        "judge_status",
        "initial_violation",
        "task_success",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "cost_usd",
        "elapsed_seconds",
    ]
    with (output_dir / "runs.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    **{key: getattr(record, key) for key in fields[:8]},
                    "judge_status": (record.judge or {}).get("status", "unscored"),
                    "initial_violation": _boolean(
                        record.scores.get("initial_violation")
                    ),
                    "task_success": _task_success(record),
                    **{key: getattr(record.usage, key) for key in fields[11:]},
                }
            )
