"""Check offline review exports, exact snapshots, and blind worksheets."""

import csv
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any, NoReturn

import pytest
from tradecopilot_eval.calibration import load_calibration
from tradecopilot_eval.judge import (
    DIMENSIONS,
    PROMPT_VERSION,
    RUBRIC_VERSION,
    JudgeInput,
)
from tradecopilot_eval.reference import load_case, load_suite
from tradecopilot_eval.reference_review import write_reference_review
from tradecopilot_eval.scoring import score_ticket

_EVAL = Path(__file__).resolve().parents[1]
_SUITE = _EVAL / "suites" / "pilot.json"
_DEV01 = _EVAL / "scenarios" / "dev_01_position_cap"
_DEV02 = _EVAL / "scenarios" / "dev_02_false_growth"
_CALIBRATION = _EVAL / "calibration" / "dev01.json"


def _export(output: Path, **overrides: Any) -> dict[str, Any]:
    arguments = {
        "suite_path": _SUITE,
        "development_paths": [_DEV01, _DEV02],
        "calibration_path": _CALIBRATION,
        "calibration_case_path": _DEV01,
        "output": output,
        **overrides,
    }
    return write_reference_review(**arguments)


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _copy_case(directory: Path, **changes: Any) -> Path:
    shutil.copytree(_DEV01, directory)
    for filename in ("inputs.json", "reference.json"):
        path = directory / filename
        document = json.loads(path.read_text())
        document.update(changes)
        path.write_text(json.dumps(document), encoding="utf-8")
    return directory


def test_export_preserves_all_sources_and_has_pending_human_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Export the complete current set without providers or fabricated review.

    Args:
        tmp_path: New review destination parent.
        monkeypatch: Reject any model construction in this offline export.
    """

    def forbidden(*args: Any, **kwargs: Any) -> NoReturn:
        raise AssertionError("Reference export must not construct a model.")

    monkeypatch.setattr("tradecopilot_eval.runner.build_chat_model", forbidden)
    monkeypatch.setattr("tradecopilot_agent.agent.build_chat_model", forbidden)
    output = tmp_path / "review"
    manifest = _export(output)
    assert manifest == json.loads((output / "manifest.json").read_text())
    assert manifest["human_review"] == "pending"
    assert manifest["judge_status"] == "not_run"
    assert manifest["prompt_version"] == PROMPT_VERSION
    assert manifest["rubric_version"] == RUBRIC_VERSION
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["code_sha256"])
    assert manifest["case_count"] == 12
    assert manifest["development_case_count"] == 2
    assert manifest["evaluation_case_count"] == 10
    assert manifest["calibration_count"] == 4
    assert manifest["validation"]["status"] == "passed"
    assert (output / "private" / "suite.json").read_bytes() == _SUITE.read_bytes()
    assert (
        output / "private" / "calibration.json"
    ).read_bytes() == _CALIBRATION.read_bytes()
    assert (output / "private" / "judge.md").read_bytes() == (
        _EVAL / "judge.md"
    ).read_bytes()
    _, cases = load_suite(_SUITE)
    cases.extend([load_case(_DEV01), load_case(_DEV02)])
    for case in cases:
        folder = output / "cases" / case.scenario.scenario_id
        assert (folder / "inputs.json").read_bytes() == case.input_document
        assert (folder / "reference.json").read_bytes() == case.reference_document
        assert manifest["case_hashes"][case.scenario.scenario_id] == {
            "input_sha256": case.input_sha256,
            "reference_sha256": case.reference_sha256,
        }
        page = (folder / "case.md").read_text()
        assert case.scenario.request in page
        assert "Human review: pending" in page
        blocks = [
            json.loads(block)
            for block in re.findall(r"```json\n(.*?)\n```", page, re.S)
        ]
        candidate_blocks = [
            block
            for block in blocks
            if isinstance(block, dict) and "independent_arithmetic" in block
        ]
        assert len(candidate_blocks) == len(case.reference.candidates)
        for candidate, block in zip(
            case.reference.candidates, candidate_blocks, strict=True
        ):
            assert block["independent_arithmetic"] == score_ticket(
                candidate.tool_arguments, case.scenario
            )
            assert block["provisional_reference"] == candidate.expected.model_dump()
    assert set(manifest["files"]) == {
        str(path.relative_to(output))
        for path in output.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    for relative, digest in manifest["files"].items():
        assert hashlib.sha256((output / relative).read_bytes()).hexdigest() == digest
    rows = _rows(output / "cases.csv")
    assert len(rows) == len(cases)
    for row in rows:
        assert all(
            row[field] == "" for field in ("reviewer", "reviewed_at", "status", "notes")
        )
        assert (output / row["case_path"]).is_file()


def test_blind_materials_hide_expectations_and_leave_every_rating_blank(
    tmp_path: Path,
) -> None:
    """Keep opaque candidates and context separate from the provisional answer key.

    Args:
        tmp_path: New export destination parent.
    """
    output = tmp_path / "review"
    _export(output)
    blind = output / "calibration" / "blind"
    calibration = load_calibration(_CALIBRATION)
    context = load_case(_DEV01)
    combined = "\n".join(
        path.read_text() for path in blind.rglob("*") if path.is_file()
    )
    for forbidden in (
        "case_kind",
        "expected_outcome",
        "score_ranges",
        "reference_expectations",
    ):
        assert forbidden not in combined
    for authored in calibration.candidates:
        assert authored.id not in combined
    assert not list(blind.rglob("*expectation*"))
    rows = _rows(blind / "ratings.csv")
    samples = [row["sample_id"] for row in rows]
    assert samples == sorted(samples) and len(set(samples)) == 4
    private = json.loads(
        (output / "private" / "calibration-expectations.json").read_text()
    )
    assert private["human_review"] == "pending"
    assert set(private["samples"]) == set(samples)
    for row in rows:
        sample = row["sample_id"]
        assert re.fullmatch(r"[0-9a-f]{24}", sample)
        candidate = JudgeInput.model_validate_json(
            (blind / f"{sample}.json").read_text()
        )
        assert candidate.profile == context.scenario.profile.model_dump()
        assert (
            candidate.journal_before_decision
            == context.scenario.journal_before_decision
        )
        assert candidate.acceptance_criteria == context.reference.response_criteria
        assert candidate.reference_evidence == [
            item.model_dump() for item in context.reference.reference_evidence
        ]
        assert candidate.portfolio["equity"] > 0
        assert (blind / f"{sample}.md").is_file()
        assert all(
            value == ""
            for field, value in row.items()
            if field not in {"sample_id", "rubric_version"}
        )
        for dimension in DIMENSIONS:
            assert row[dimension] == row[dimension + "_reason"] == ""
        for index in range(len(candidate.acceptance_criteria)):
            assert (
                row[f"criterion_{index}_met"] == row[f"criterion_{index}_reason"] == ""
            )
        original_id = private["samples"][sample]["candidate_id"]
        assert (
            private["samples"][sample]["score_ranges"]
            == calibration.reference_expectations[original_id].model_dump(mode="json")[
                "score_ranges"
            ]
        )
    rubric = (blind / "judge.md").read_text()
    assert "## Outcome labels" in rubric
    original = (_EVAL / "judge.md").read_text()
    assert (
        original.split("## Prompt constraints\n", 1)[1]
        .split("## Output and failure handling\n", 1)[0]
        .rstrip()
        in rubric
    )
    assert "formal run-agreement CSV" in (blind / "README.md").read_text()


def test_exact_crlf_snapshot_hashes_survive_export(tmp_path: Path) -> None:
    """Preserve original bytes rather than reserializing validated input objects.

    Args:
        tmp_path: Temporary source copy and export parent.
    """
    source = tmp_path / "source"
    shutil.copytree(_DEV01, source)
    for name in ("inputs.json", "reference.json"):
        path = source / name
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    output = tmp_path / "review"
    manifest = _export(
        output, development_paths=[source, _DEV02], calibration_case_path=source
    )
    for name, key in (
        ("inputs.json", "input_sha256"),
        ("reference.json", "reference_sha256"),
    ):
        original = (source / name).read_bytes()
        assert (output / "cases" / "DEV-01" / name).read_bytes() == original
        assert (
            manifest["case_hashes"]["DEV-01"][key]
            == hashlib.sha256(original).hexdigest()
        )


@pytest.mark.parametrize("existing", ["directory", "file", "symlink"])
def test_existing_outputs_are_never_overwritten(tmp_path: Path, existing: str) -> None:
    """Refuse existing directories, files, and dangling links before exporting.

    Args:
        tmp_path: Output parent.
        existing: Existing filesystem entry type to preserve.
    """
    output = tmp_path / "review"
    if existing == "directory":
        output.mkdir()
        (output / "sentinel").write_text("keep")
    elif existing == "file":
        output.write_text("keep")
    else:
        output.symlink_to(tmp_path / "missing")
    with pytest.raises(FileExistsError):
        _export(output)
    assert not (output / "manifest.json").exists()
    if existing == "directory":
        assert (output / "sentinel").read_text() == "keep"
    elif existing == "file":
        assert output.read_text() == "keep"
    else:
        assert output.is_symlink()


def test_repository_destinations_and_symlink_aliases_are_rejected(
    tmp_path: Path,
) -> None:
    """Keep artifacts outside the worktree and other repository roots.

    Args:
        tmp_path: Non-repository directory holding a test repository marker.
    """
    with pytest.raises(ValueError, match="outside Git"):
        _export(_EVAL / "forbidden-review-output")
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".git").write_text("gitdir: metadata")
    alias = tmp_path / "alias"
    alias.symlink_to(repository, target_is_directory=True)
    for output in (repository / "review", alias / "review"):
        with pytest.raises(ValueError, match="outside Git"):
            _export(output)
        assert not output.exists()


def test_duplicate_paths_and_scenario_ids_fail_before_creating_output(
    tmp_path: Path,
) -> None:
    """Resolve aliases and reject duplicate identities even across source copies.

    Args:
        tmp_path: Temporary source aliases and output parent.
    """
    alias = tmp_path / "alias"
    alias.symlink_to(_DEV01, target_is_directory=True)
    with pytest.raises(ValueError, match="Duplicate scenario paths"):
        _export(tmp_path / "paths", development_paths=[_DEV01, alias])
    copied = _copy_case(tmp_path / "copied")
    with pytest.raises(ValueError, match="Duplicate scenario IDs"):
        _export(tmp_path / "ids", development_paths=[_DEV01, copied])
    assert not (tmp_path / "paths").exists()
    assert not (tmp_path / "ids").exists()


@pytest.mark.parametrize(
    "scenario_id", ["../escape", "/absolute", "bad/name", "bad\\name", "."]
)
def test_unsafe_scenario_ids_cannot_become_paths(
    tmp_path: Path, scenario_id: str
) -> None:
    """Reject path-like identifiers before creating any review output.

    Args:
        tmp_path: Temporary invalid source and destination parent.
        scenario_id: Identifier that must never be used as a path.
    """
    source = _copy_case(tmp_path / "source", scenario_id=scenario_id)
    output = tmp_path / "review"
    with pytest.raises(ValueError, match="safe ASCII identifiers"):
        _export(
            output, development_paths=[source, _DEV02], calibration_case_path=source
        )
    assert not output.exists()


def test_wrong_calibration_scenario_and_unsafe_candidate_id_are_rejected(
    tmp_path: Path,
) -> None:
    """Require the correct calibration context and safe authored identifiers.

    Args:
        tmp_path: Invalid calibration file and new output parent.
    """
    with pytest.raises(ValueError, match="scenario and context case disagree"):
        _export(tmp_path / "wrong-context", calibration_case_path=_DEV02)
    document = json.loads(_CALIBRATION.read_text())
    previous = document["candidates"][0]["id"]
    document["candidates"][0]["id"] = "../escape"
    document["reference_expectations"]["../escape"] = document[
        "reference_expectations"
    ].pop(previous)
    calibration = tmp_path / "calibration.json"
    calibration.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="safe ASCII identifiers"):
        _export(tmp_path / "unsafe-candidate", calibration_path=calibration)
    assert not (tmp_path / "wrong-context").exists()
    assert not (tmp_path / "unsafe-candidate").exists()


def test_failed_label_checks_are_exported_without_human_approval(
    tmp_path: Path,
) -> None:
    """Expose inconsistent labels for review instead of silently accepting them.

    Args:
        tmp_path: Modified reference copy and review destination parent.
    """
    source = _copy_case(tmp_path / "source")
    path = source / "reference.json"
    document = json.loads(path.read_text())
    expected = document["candidates"][0]["expected"]
    expected["eligible"] = not expected["eligible"]
    path.write_text(json.dumps(document))
    output = tmp_path / "review"
    manifest = _export(
        output, development_paths=[source, _DEV02], calibration_case_path=source
    )
    assert manifest["validation"]["status"] == "failed"
    assert manifest["validation"]["errors"]
    assert manifest["human_review"] == "pending"
    assert all(row["status"] == "" for row in _rows(output / "cases.csv"))
    assert "Software validation: failed" in (output / "README.md").read_text()
