"""Commands for local validation, experiments, reports, and blind human review."""

import argparse
import asyncio
import json
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from tradecopilot_eval.experiment import read_runs, run_suite, validate_cases
from tradecopilot_eval.human import (
    ReviewItem,
    calculate_agreement,
    read_human_reviews,
    select_review_sample,
    write_review_csv,
)
from tradecopilot_eval.judge import (
    JudgeConfig,
    JudgeInput,
    JudgeResult,
    LangChainJudgeTransport,
    ScriptedJudgeTransport,
    judge_candidate,
)
from tradecopilot_eval.offline import offline_connections
from tradecopilot_eval.records import RunRecord
from tradecopilot_eval.reference import load_case, load_suite
from tradecopilot_eval.runner import RunConfig, judge_input, write_json


def _default_suite() -> Path:
    return Path(__file__).resolve().parents[2] / "suites/pilot.json"


def _model_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mode", choices=["scripted", "model"], default="scripted")
    parser.add_argument("--agent-model")
    parser.add_argument("--agent-family")
    parser.add_argument("--judge-model")
    parser.add_argument("--judge-family")
    parser.add_argument("--allow-model-calls", action="store_true")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--max-output-tokens", type=int, default=4096)
    parser.add_argument("--input-usd-per-million", type=float)
    parser.add_argument("--output-usd-per-million", type=float)
    parser.add_argument("--judge-input-usd-per-million", type=float)
    parser.add_argument("--judge-output-usd-per-million", type=float)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="TradeCopilot evaluation and judge tools"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser(
        "validate", help="Check cases and reference labels locally"
    )
    validate.add_argument("--suite", type=Path, default=_default_suite())
    run = commands.add_parser(
        "run", help="Run a frozen suite; defaults to scripted rehearsal"
    )
    run.add_argument("--suite", type=Path, default=_default_suite())
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--limit", type=int)
    run.add_argument("--allow-unreviewed-fixtures", action="store_true")
    _model_options(run)
    calibration = commands.add_parser(
        "calibrate", help="Check judge development examples"
    )
    calibration.add_argument(
        "--data",
        type=Path,
        default=_default_suite().parent.parent / "calibration/dev01.json",
    )
    calibration.add_argument(
        "--case",
        type=Path,
        default=_default_suite().parent.parent / "scenarios/dev_01_position_cap",
    )
    calibration.add_argument("--output", type=Path, required=True)
    _model_options(calibration)
    report = commands.add_parser("report", help="Rebuild a report from saved runs")
    report.add_argument("--input", type=Path, required=True)
    review = commands.add_parser("review", help="Export a blind 20-percent review form")
    review.add_argument("--input", type=Path, required=True)
    review.add_argument("--output", type=Path, required=True)
    review.add_argument("--seed", type=int, default=74)
    review.add_argument("--disputed", action="append", default=[])
    agreement = commands.add_parser("agreement", help="Compare human and judge ratings")
    agreement.add_argument("--input", type=Path, required=True)
    agreement.add_argument("--reviews", type=Path, required=True)
    agreement.add_argument("--output", type=Path, required=True)
    return parser


def _configs(args: argparse.Namespace) -> tuple[RunConfig, JudgeConfig]:
    if args.mode == "model" and not all(
        (
            args.agent_model,
            args.agent_family,
            args.judge_model,
            args.judge_family,
        )
    ):
        raise ValueError(
            "Model mode needs explicit agent/judge model IDs and family labels."
        )
    if args.mode == "scripted" and any((args.agent_model, args.judge_model)):
        raise ValueError("Use --mode model for provider model identifiers.")
    config = RunConfig(
        mode=args.mode,
        model_id=args.agent_model or "scripted:workflow-v1",
        model_family=args.agent_family or "scripted",
        allow_model_calls=args.allow_model_calls,
        timeout_seconds=args.timeout,
        max_output_tokens=args.max_output_tokens,
        input_usd_per_million=args.input_usd_per_million,
        output_usd_per_million=args.output_usd_per_million,
    )
    judge = JudgeConfig(
        mode=args.mode,
        agent_model=config.model_id,
        agent_family=config.model_family,
        judge_model=args.judge_model or "scripted:judge-control-v1",
        judge_family=args.judge_family or "scripted",
        input_usd_per_million=args.judge_input_usd_per_million,
        output_usd_per_million=args.judge_output_usd_per_million,
    )
    return config, judge


async def _calibrate(args: argparse.Namespace) -> bool:
    from tradecopilot_eval.calibration import (
        build_calibration_inputs,
        compare_calibration,
        load_calibration,
    )

    config, judge = _configs(args)
    if config.mode == "model" and not config.allow_model_calls:
        raise PermissionError("Model calls require explicit enablement.")
    examples = load_calibration(args.data)
    case = load_case(args.case)
    if examples.scenario_id != case.scenario.scenario_id:
        raise ValueError("Calibration examples and scenario IDs disagree.")
    placeholder = RunRecord(
        run_id="calibration-context",
        scenario_id=case.scenario.scenario_id,
        condition="full",
        phase="single",
        repetition=1,
        mode=config.mode,
        model_id=config.model_id,
        model_family=config.model_family,
        status="ok",
    )
    inputs = build_calibration_inputs(examples, judge_input(placeholder, case))
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "examples-private.json", examples.model_dump(mode="json"))
    transport = (
        ScriptedJudgeTransport()
        if config.mode == "scripted"
        else LangChainJudgeTransport(judge, enabled=config.allow_model_calls)
    )
    results: dict[str, JudgeResult] = {}
    for candidate_id, candidate in inputs.items():
        result = await judge_candidate(candidate, transport, judge)
        results[candidate_id] = result
        write_json(
            args.output / f"{candidate.sample_id}.input.json", candidate.model_dump()
        )
        write_json(
            args.output / f"{candidate.sample_id}.judge.json",
            result.model_dump(mode="json"),
        )
    comparison = compare_calibration(examples, results)
    write_json(args.output / "calibration.json", comparison.model_dump(mode="json"))
    return all(result.status == "ok" for result in results.values())


def _review_items(directory: Path) -> list[ReviewItem]:
    items: list[ReviewItem] = []
    for path in sorted(directory.glob("runs/*/run.json")):
        record = RunRecord.model_validate_json(path.read_text(encoding="utf-8"))
        if record.judge is None:
            continue
        candidate = JudgeInput.model_validate_json(
            (path.parent / "judge-input.json").read_text(encoding="utf-8")
        )
        items.append(
            ReviewItem(
                run_id=record.run_id,
                condition=record.condition,
                scenario_type=str(record.metadata["category"]),
                candidate=candidate,
                judge_result=JudgeResult.model_validate(record.judge),
            )
        )
    if not items:
        raise ValueError("No judged candidates are available for review.")
    return items


def main(argv: list[str] | None = None) -> int:
    """Run a command and print only output locations or concise validation results.

    Args:
        argv: Explicit arguments for tests; None reads the process arguments.

    Returns:
        Zero on success, one for validation failures, two for invalid commands.
        Model calls require their explicit flag; broker execution stays disabled.
    """
    args = _parser().parse_args(argv)
    try:
        from tradecopilot_eval.report import write_report

        if args.command == "validate":
            suite, cases = load_suite(args.suite)
            result = validate_cases(cases)
            print(json.dumps({"suite_id": suite.suite_id, **result}, indent=2))
            return 0 if result["status"] == "passed" else 1
        if args.command == "calibrate":
            guard = offline_connections() if args.mode == "scripted" else nullcontext()
            with guard:
                succeeded = asyncio.run(_calibrate(args))
            print(f"Saved calibration controls/results to {args.output.resolve()}")
            return 0 if succeeded else 1
        if args.command == "run":
            config, judge = _configs(args)
            guard = (
                offline_connections() if config.mode == "scripted" else nullcontext()
            )
            with guard:
                records = asyncio.run(
                    run_suite(
                        args.suite,
                        args.output,
                        config,
                        judge,
                        limit=args.limit,
                        allow_unreviewed=args.allow_unreviewed_fixtures,
                    )
                )
            write_report(records, args.output)
            print(f"Saved {len(records)} {config.mode} runs to {args.output.resolve()}")
            return (
                0
                if all(
                    record.status == "ok" and (record.judge or {}).get("status") == "ok"
                    for record in records
                )
                else 1
            )
        if args.command == "report":
            write_report(read_runs(args.input), args.input)
            print(f"Updated report in {args.input.resolve()}")
            return 0
        if args.command == "review":
            items = _review_items(args.input)
            selection = select_review_sample(
                items, seed=args.seed, disputed_run_ids=args.disputed
            )
            args.output.mkdir(parents=True, exist_ok=False)
            write_review_csv(selection, args.output / "ratings.csv")
            write_json(
                args.output / "selection-private.json",
                selection.model_dump(mode="json"),
            )
            print(
                f"Saved {selection.selected_count} blind samples "
                f"to {args.output / 'ratings.csv'}"
            )
            return 0
        reviews = read_human_reviews(args.reviews)
        report: Any = calculate_agreement(_review_items(args.input), reviews)
        if args.output.exists():
            raise FileExistsError(
                "Agreement output already exists; choose a new filename."
            )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.output, report.model_dump(mode="json"))
        print(f"Saved agreement report to {args.output.resolve()}")
        return 0
    except (ValueError, OSError, PermissionError) as exc:
        print(f"Evaluation error: {exc}")
        return 2
