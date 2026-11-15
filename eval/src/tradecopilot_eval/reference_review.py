"""Export unreviewed references and separate blind development worksheets."""

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from tradecopilot_eval.calibration import build_calibration_inputs, load_calibration
from tradecopilot_eval.experiment import validate_cases
from tradecopilot_eval.judge import (
    DIMENSIONS,
    PROMPT_VERSION,
    RUBRIC_VERSION,
    JudgeInput,
)
from tradecopilot_eval.records import PROJECTION_VERSION, RunRecord
from tradecopilot_eval.reference import Case, load_case, load_suite
from tradecopilot_eval.runner import code_digest, judge_input, write_json
from tradecopilot_eval.scoring import score_ticket


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(value: Any) -> str:
    return "```json\n" + json.dumps(value, indent=2, ensure_ascii=True) + "\n```\n"


def _section(title: str, value: Any) -> str:
    return f"## {title}\n\n{_json(value)}\n"


def _safe_id(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value):
        raise ValueError("Scenario and candidate IDs need safe ASCII identifiers.")


def _destination(output: Path) -> None:
    target = output.resolve()
    project = Path(__file__).resolve().parents[3]
    if target.is_relative_to(project) or any(
        (parent / ".git").exists() for parent in (target, *target.parents)
    ):
        raise ValueError("Keep review materials outside Git repositories.")
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Output directory already exists: {output}")


def _csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    field: "'" + value
                    if value.lstrip().startswith(("=", "+", "-", "@"))
                    else value
                    for field, value in row.items()
                }
            )


def _case_markdown(case: Case) -> str:
    scenario, reference = case.scenario, case.reference
    origin = (
        "All inputs are synthetic."
        if scenario.synthetic
        else "Primary-source evidence uses an assumed profile and account."
    )
    text = (
        f"# {scenario.scenario_id}: Reference review\n\n"
        f"Human review: pending. {origin}\n"
        "The labels below are\n"
        "provisional expectations, not completed human judgments.\n\n"
        f"Split: {scenario.split}. Category: {reference.category}.\n"
        f"Decision time: {scenario.decision_time.isoformat()}.\n\n"
        "## Request\n\n"
        + "\n".join("> " + line for line in scenario.request.splitlines())
        + "\n\n"
        + _section("Confirmed profile", scenario.profile.model_dump(mode="json"))
        + _section("Journal before the decision", scenario.journal_before_decision)
        + _section("Assumptions", reference.assumptions)
        + _section("Reference calculations to check", reference.calculation)
        + "## Frozen evidence\n\n"
    )
    for record in reference.reference_evidence:
        text += f"### Evidence {record.id}\n\n{_json(record.model_dump(mode='json'))}\n"
    text += _section(
        "Recorded tool calls and failures",
        [
            {
                "method": fixture.method,
                "arguments": fixture.arguments,
                "available_at": fixture.available_at.isoformat(),
                "error": fixture.output.error,
                "summary": fixture.output.summary,
                "evidence_ids": [item.id for item in fixture.output.evidence],
            }
            for fixture in scenario.tool_fixtures
        ],
    )
    text += (
        "## Candidate tickets and independent arithmetic\n\n"
        "The independent Decimal scorer recomputes constraints from frozen inputs.\n"
        "Its result is a software check, not human approval or a trade execution.\n\n"
    )
    if not reference.candidates:
        text += "No ticket candidates are defined for this case.\n\n"
    for candidate in reference.candidates:
        text += (
            f"### Candidate {candidate.id}\n\n"
            + _json(
                {
                    "tool_arguments": candidate.tool_arguments,
                    "provisional_reference": candidate.expected.model_dump(),
                    "independent_arithmetic": score_ticket(
                        candidate.tool_arguments, scenario
                    ),
                }
            )
            + "\n"
        )
    text += _section(
        "Claim probes and provisional labels",
        [item.model_dump(mode="json") for item in reference.claim_probes],
    )
    text += _section("Response criteria to check", reference.response_criteria)
    text += _section("Provisional acceptable outcomes", reference.acceptable_outcomes)
    if case.provenance is not None:
        text += _section(
            "Source and assumption mapping", case.provenance.model_dump(mode="json")
        )
        text += (
            "Archive hashes and record mappings were checked locally. These checks\n"
            "do not prove source authenticity, transcription accuracy, or the claims.\n"
            "Publication availability assumptions still require human review.\n\n"
        )
    text += (
        "## Original snapshots\n\n"
        f"- [inputs.json](inputs.json): SHA-256 `{case.input_sha256}`.\n"
        f"- [reference.json](reference.json): SHA-256 `{case.reference_sha256}`.\n\n"
        "Record factual, arithmetic, timing, ambiguity, and rubric issues in your\n"
        "own copy of cases.csv. Keep both reviewers' original notes; save any\n"
        "reconciled decision separately. This export does not approve references.\n"
    )
    if case.provenance_sha256 is not None:
        text += (
            "\n[provenance.json](provenance.json): "
            f"SHA-256 `{case.provenance_sha256}`.\n"
        )
    return text


def _blind_markdown(candidate: JudgeInput) -> str:
    text = (
        f"# Candidate {candidate.sample_id}\n\n"
        "Independent development review. No human scores have been entered.\n\n"
        + _section("Request", candidate.request)
        + _section("Decision time", candidate.decision_time)
        + _section("Confirmed profile", candidate.profile)
        + _section("Portfolio", candidate.portfolio)
        + _section("Journal before the decision", candidate.journal_before_decision)
        + _section("Reference evidence", candidate.reference_evidence)
        + _section("Acceptance criteria", candidate.acceptance_criteria)
        + _section("Candidate response", candidate.final_response)
    )
    return text.rstrip() + "\n"


def _blind_readme(samples: list[str]) -> str:
    links = "\n".join(f"- [{sample}]({sample}.md)" for sample in samples)
    return (
        "# Blind development review\n\n"
        "Prefer two independent reviewers. Copy [ratings.csv](ratings.csv) and\n"
        "fill separate sheets before comparing notes. Keep the original sheets\n"
        "and save reconciled opinions separately. Leave uncertain scores blank.\n\n"
        "This worksheet reviews predefined development examples. It is not the\n"
        "formal run-agreement CSV and cannot establish measured judge agreement.\n"
        "No import or automatic approval is performed.\n\n"
        f"Rubric version: {RUBRIC_VERSION}. Read [the scoring rubric](judge.md).\n"
        "Use integer scores from 1 to 5 and give a reason for each dimension.\n"
        "Review every candidate; the formal experiment's sampling rule does not\n"
        "apply here. For each zero-based criterion column, enter true, false,\n"
        "or leave it blank, and explain the assessment in its reason column.\n\n"
        "Use outcome recommendation, no_trade, needs_information, refusal, or\n"
        "unclear, or leave it blank. Check claims in the final answer against\n"
        "the reference evidence. A plan lists intended steps.\n\n"
        "## Candidates\n\n" + links + "\n"
    )


def write_reference_review(
    suite_path: Path,
    development_paths: list[Path],
    calibration_path: Path,
    calibration_case_path: Path,
    output: Path,
    *,
    evidence_root: Path | None = None,
) -> dict[str, Any]:
    """Export reference review materials without model calls or human approvals.

    Args:
        suite_path: Evaluation suite JSON with relative case directories.
        development_paths: Additional development case directories.
        calibration_path: Provisional predefined calibration examples.
        calibration_case_path: Case supplying the calibration reference context.
        output: New directory outside any Git repository.
        evidence_root: External archives for primary-source cases; not exported.

    Returns:
        The saved manifest, including software validation and pending human review.
        Label-check failures are exported for inspection, not treated as approval.

    Raises:
        FileExistsError: The output path already exists.
        ValueError: Structure, duplicate paths/IDs, context, or destination is invalid.
        OSError: An input cannot be read or an output cannot be written.
    """
    _destination(output)
    suite, suite_cases = load_suite(suite_path, evidence_root=evidence_root)
    paths = [suite_path.parent / item for item in suite.scenario_paths]
    paths += development_paths
    resolved = [str(path.resolve()).casefold() for path in paths]
    if len(set(resolved)) != len(resolved):
        raise ValueError("Duplicate scenario paths.")
    cases = suite_cases + [
        load_case(path, evidence_root=evidence_root) for path in development_paths
    ]
    ids = [case.scenario.scenario_id for case in cases]
    if len({value.casefold() for value in ids}) != len(ids):
        raise ValueError("Duplicate scenario IDs.")
    for value in ids:
        _safe_id(value)
    calibration = load_calibration(calibration_path)
    context_case = load_case(calibration_case_path, evidence_root=evidence_root)
    if calibration.scenario_id != context_case.scenario.scenario_id:
        raise ValueError("Calibration scenario and context case disagree.")
    matching = [
        case for case in cases if case.scenario.scenario_id == calibration.scenario_id
    ]
    if len(matching) != 1 or matching[0] != context_case:
        raise ValueError("Calibration context must match one exported case exactly.")
    for authored in calibration.candidates:
        _safe_id(authored.id)
    placeholder = RunRecord(
        run_id="reference-review",
        scenario_id=context_case.scenario.scenario_id,
        condition="full",
        phase="single",
        repetition=1,
        mode="scripted",
        model_id="scripted:reference-review",
        model_family="scripted",
        status="ok",
    )
    blind = build_calibration_inputs(
        calibration, judge_input(placeholder, context_case)
    )
    validation = validate_cases(cases)
    suite_document = suite_path.read_bytes()
    calibration_document = calibration_path.read_bytes()
    rubric_document = (Path(__file__).resolve().parents[2] / "judge.md").read_bytes()
    rubric = rubric_document.decode("utf-8")
    start = rubric.index("## Prompt constraints\n")
    stop = rubric.index("## Output and failure handling\n", start)
    blind_rubric = (
        "# Judge rubric\n\n"
        f"Rubric version: {RUBRIC_VERSION}.\n"
        f"Source SHA-256: `{_digest(rubric_document)}`.\n\n"
        "The following scoring instructions are copied from the source rubric.\n\n"
        + rubric[start:stop].rstrip()
        + "\n"
    )
    output.mkdir(parents=True, exist_ok=False)
    private = output / "private"
    private.mkdir()
    (private / "suite.json").write_bytes(suite_document)
    (private / "calibration.json").write_bytes(calibration_document)
    (private / "judge.md").write_bytes(rubric_document)
    rows: list[dict[str, str]] = []
    for case in cases:
        folder = output / "cases" / case.scenario.scenario_id
        folder.mkdir(parents=True)
        (folder / "inputs.json").write_bytes(case.input_document)
        (folder / "reference.json").write_bytes(case.reference_document)
        if case.provenance_document:
            (folder / "provenance.json").write_bytes(case.provenance_document)
        (folder / "case.md").write_text(_case_markdown(case), encoding="utf-8")
        rows.append(
            {
                "scenario_id": case.scenario.scenario_id,
                "split": case.scenario.split,
                "category": case.reference.category,
                "evidence_origin": "synthetic"
                if case.scenario.synthetic
                else "primary_source_with_assumptions",
                "case_path": str((folder / "case.md").relative_to(output)),
                "reviewer": "",
                "reviewed_at": "",
                "status": "",
                "notes": "",
            }
        )
    _csv(output / "cases.csv", list(rows[0]) if rows else ["scenario_id"], rows)
    blind_folder = output / "calibration" / "blind"
    blind_folder.mkdir(parents=True)
    (blind_folder / "judge.md").write_text(blind_rubric, encoding="utf-8")
    mapping: dict[str, Any] = {}
    rating_rows: list[dict[str, str]] = []
    for candidate_id, candidate in sorted(
        blind.items(), key=lambda item: item[1].sample_id
    ):
        sample = candidate.sample_id
        write_json(blind_folder / f"{sample}.json", candidate.model_dump())
        (blind_folder / f"{sample}.md").write_text(
            _blind_markdown(candidate), encoding="utf-8"
        )
        rating_rows.append(
            {
                "sample_id": sample,
                "rubric_version": RUBRIC_VERSION,
                "reviewer": "",
                "reviewed_at": "",
                **{dimension: "" for dimension in DIMENSIONS},
                **{dimension + "_reason": "" for dimension in DIMENSIONS},
                **{
                    f"criterion_{index}_{field}": ""
                    for index in range(len(candidate.acceptance_criteria))
                    for field in ("met", "reason")
                },
                "outcome": "",
                "notes": "",
            }
        )
        mapping[sample] = {
            "candidate_id": candidate_id,
            **calibration.reference_expectations[candidate_id].model_dump(mode="json"),
        }
    _csv(blind_folder / "ratings.csv", list(rating_rows[0]), rating_rows)
    (blind_folder / "README.md").write_text(
        _blind_readme(sorted(mapping)), encoding="utf-8"
    )
    write_json(
        private / "calibration-expectations.json",
        {
            "human_review": "pending",
            "rubric_version": RUBRIC_VERSION,
            "samples": mapping,
        },
    )
    links = "\n".join(f"- [{row['scenario_id']}]({row['case_path']})" for row in rows)
    (output / "README.md").write_text(
        "# Reference review materials\n\n"
        "Human review: pending. Each case identifies synthetic or primary-source\n"
        "evidence; user profiles and accounts remain scenario assumptions.\n"
        "Software validation does not approve data or establish model quality.\n\n"
        f"Cases: {len(cases)}. Calibration examples: {len(blind)}.\n"
        f"Software validation: {validation['status']}; "
        "see [manifest.json](manifest.json) for details.\n\n"
        "## Reference reviewers\n\n"
        "Prefer two independent reviewers. Each should copy [cases.csv](cases.csv)\n"
        "and review each case. Check facts, timestamps, arithmetic, labels,\n"
        "and criteria. Leave reviewer, reviewed_at, status, and notes blank until\n"
        "reviewing. Keep original sheets and reconcile differences separately.\n\n"
        + links
        + "\n\n"
        "## Blind calibration reviewers\n\n"
        "Share only [calibration/blind](calibration/blind/README.md) with the blind\n"
        "reviewers. Its README and blank ratings.csv describe the task.\n"
        "Do not share private/, which contains provisional expectations and the\n"
        "candidate mapping. Those expectations also need independent review.\n"
        "The worksheet is for development, not the formal agreement import.\n\n"
        "## Provenance\n\n"
        "Case folders retain exact inputs.json and reference.json bytes. Private\n"
        "snapshots retain the suite and calibration inputs. manifest.json records\n"
        "file hashes and checks. No review status is imported or approved.\n"
        "Primary-source cases also retain provenance.json and archive hashes;\n"
        "the external source archives and their private root paths are not copied.\n"
        "These mechanical checks do not establish the correctness of the facts.\n"
        "No model calls or judging were performed for this export.\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "artifact_type": "reference_review",
        "human_review": "pending",
        "judge_status": "not_run",
        "code_sha256": code_digest(),
        "prompt_version": PROMPT_VERSION,
        "projection_version": PROJECTION_VERSION,
        "rubric_version": RUBRIC_VERSION,
        "case_count": len(cases),
        "development_case_count": sum(
            case.scenario.split == "development" for case in cases
        ),
        "evaluation_case_count": sum(
            case.scenario.split == "evaluation" for case in cases
        ),
        "calibration_count": len(blind),
        "synthetic_case_count": sum(case.scenario.synthetic for case in cases),
        "primary_source_case_count": sum(not case.scenario.synthetic for case in cases),
        "validation": validation,
        "suite_sha256": _digest(suite_document),
        "calibration_sha256": _digest(calibration_document),
        "rubric_sha256": _digest(rubric_document),
        "case_hashes": {
            case.scenario.scenario_id: {
                "input_sha256": case.input_sha256,
                "reference_sha256": case.reference_sha256,
                **(
                    {
                        "provenance_sha256": case.provenance_sha256,
                        "source_hashes": case.source_hashes,
                    }
                    if case.provenance is not None
                    else {}
                ),
            }
            for case in cases
        },
        "files": {
            str(path.relative_to(output)): _digest(path.read_bytes())
            for path in sorted(output.rglob("*"))
            if path.is_file()
        },
    }
    write_json(output / "manifest.json", manifest)
    return manifest
