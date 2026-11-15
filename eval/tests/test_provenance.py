"""Validate local provenance mechanics without asserting source factual accuracy."""

import asyncio
import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from tradecopilot_agent.state import EvidenceRecord
from tradecopilot_eval.fixtures import Scenario
from tradecopilot_eval.provenance import evidence_digest
from tradecopilot_eval.reference import load_case, load_suite
from tradecopilot_eval.reference_review import write_reference_review
from tradecopilot_eval.runner import RunConfig, run_case

_EVAL = Path(__file__).resolve().parents[1]
_DEV01 = _EVAL / "scenarios" / "dev_01_position_cap"
_SOURCE_ID = "test_primary_quote"
_URL = "https://example.test/publisher/release"


def _canonical(record: dict[str, Any]) -> str:
    value = EvidenceRecord.model_validate(record).model_dump(mode="json")
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


@dataclass
class _Bundle:
    directory: Path
    archive: Path
    inputs: dict[str, Any]
    reference: dict[str, Any]
    manifest: dict[str, Any]

    def save(self) -> None:
        """Write the mutable local fixture documents without changing their schema."""
        for name, value in (
            ("inputs.json", self.inputs),
            ("reference.json", self.reference),
            ("provenance.json", self.manifest),
        ):
            (self.directory / name).write_text(
                json.dumps(value, indent=2), encoding="utf-8"
            )


def _bundle(tmp_path: Path) -> _Bundle:
    directory, archive = tmp_path / "case", tmp_path / "archive"
    directory.mkdir()
    (archive / "publisher").mkdir(parents=True)
    snapshot = archive / "publisher" / "release.html"
    snapshot.write_bytes(
        b"<html>Offline provenance test fixture; not a real publication.</html>\n"
    )
    inputs = json.loads((_DEV01 / "inputs.json").read_text())
    reference = json.loads((_DEV01 / "reference.json").read_text())
    inputs.update(synthetic=False, scenario_id="LOCAL-PRIMARY-01")
    reference.update(
        scenario_id=inputs["scenario_id"],
        provenance_status="primary_source_pending_review",
    )
    retrieved_at = "2026-11-10T08:00:00Z"
    records = []
    links = []
    for fixture in inputs["tool_fixtures"]:
        for record in fixture["output"]["evidence"]:
            primary = record["payload"]["kind"] == "quote"
            record["source"] = _SOURCE_ID if primary else "assumed_test_account"
            record["url"] = _URL if primary else None
            if primary:
                record["fetched_at"] = retrieved_at
            records.append(deepcopy(record))
            links.append(
                {
                    "evidence_id": record["id"],
                    "origin": "primary_source" if primary else "scenario_assumption",
                    "source_id": _SOURCE_ID if primary else None,
                    "locator": "Local fixture paragraph"
                    if primary
                    else "Account fixture",
                    "note": "Offline test mapping only."
                    if primary
                    else "Hypothetical account and positions for this scenario.",
                    "evidence_sha256": _canonical(record),
                }
            )
    reference["reference_evidence"] = records
    manifest = {
        "schema_version": 1,
        "scenario_id": inputs["scenario_id"],
        "status": "primary_source_pending_review",
        "sources": [
            {
                "id": _SOURCE_ID,
                "title": "Local test archive",
                "url": _URL,
                "published_date": "2026-09-15",
                "available_at": "2026-09-15T13:59:00Z",
                "availability_basis": "Fixed availability solely for local validation.",
                "retrieved_at": retrieved_at,
                "snapshot_path": "publisher/release.html",
                "sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                "content_type": "text/html",
            }
        ],
        "evidence": links,
    }
    bundle = _Bundle(directory, archive, inputs, reference, manifest)
    bundle.save()
    return bundle


def _suite(bundle: _Bundle) -> Path:
    path = bundle.directory.parent / "suite.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "suite_id": "local-provenance",
                "description": "Offline provenance validation fixture.",
                "scenario_paths": [bundle.directory.name],
                "ablation_scenarios": [],
                "repetitions": 1,
                "conditions": ["none", "prose", "structured", "full"],
                "provenance_status": "primary_source_pending_review",
            }
        )
    )
    return path


def _change_records(bundle: _Bundle, evidence_id: str, field: str, value: Any) -> None:
    for records in (
        bundle.reference["reference_evidence"],
        *[fixture["output"]["evidence"] for fixture in bundle.inputs["tool_fixtures"]],
    ):
        for record in records:
            if record["id"] == evidence_id:
                record[field] = value
    for link in bundle.manifest["evidence"]:
        if link["evidence_id"] == evidence_id:
            record = next(
                item
                for item in bundle.reference["reference_evidence"]
                if item["id"] == evidence_id
            )
            link["evidence_sha256"] = _canonical(record)


def test_primary_case_preserves_exact_manifest_and_late_retrieval(
    tmp_path: Path,
) -> None:
    """Accept an archived source with later retrieval while retaining pending review."""
    bundle = _bundle(tmp_path)
    path = bundle.directory / "provenance.json"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    case = load_case(bundle.directory, evidence_root=bundle.archive)
    assert case.scenario.synthetic is False
    assert case.reference.provenance_status == "primary_source_pending_review"
    assert case.provenance is not None
    assert case.provenance.status == "primary_source_pending_review"
    assert case.provenance_document == path.read_bytes()
    assert case.provenance_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert case.source_hashes == {_SOURCE_ID: bundle.manifest["sources"][0]["sha256"]}
    assert str(bundle.archive) not in path.read_text()


def test_evidence_hash_is_canonical_and_optional(tmp_path: Path) -> None:
    """Bind normalized record contents independently of dictionary key ordering."""
    bundle = _bundle(tmp_path)
    raw = bundle.reference["reference_evidence"][0]
    record = EvidenceRecord.model_validate(raw)
    assert evidence_digest(record) == _canonical(raw)
    assert evidence_digest(
        EvidenceRecord.model_validate(dict(reversed(list(raw.items()))))
    ) == _canonical(raw)
    for item in bundle.manifest["evidence"]:
        del item["evidence_sha256"]
    bundle.save()
    assert (
        load_case(bundle.directory, evidence_root=bundle.archive).provenance is not None
    )


def test_primary_fetch_time_cannot_be_backdated(tmp_path: Path) -> None:
    """Reject a backdated fetch even when its changed record hash is valid."""
    bundle = _bundle(tmp_path)
    evidence_id = bundle.manifest["evidence"][0]["evidence_id"]
    _change_records(bundle, evidence_id, "fetched_at", "2026-09-15T13:59:00Z")
    bundle.save()
    with pytest.raises(ValueError):
        load_case(bundle.directory, evidence_root=bundle.archive)


def test_primary_fetch_time_accepts_an_equivalent_timezone(tmp_path: Path) -> None:
    """Compare instants rather than textual timezone notation for archive retrieval."""
    bundle = _bundle(tmp_path)
    evidence_id = bundle.manifest["evidence"][0]["evidence_id"]
    _change_records(bundle, evidence_id, "fetched_at", "2026-11-10T16:00:00+08:00")
    bundle.save()
    case = load_case(bundle.directory, evidence_root=bundle.archive)
    assert case.provenance is not None
    record = next(
        item for item in case.reference.reference_evidence if item.id == evidence_id
    )
    assert record.fetched_at == "2026-11-10T16:00:00+08:00"


def test_legacy_synthetic_cases_need_no_manifest_or_archive() -> None:
    """Keep existing synthetic inputs loadable without additional local files."""
    case = load_case(_DEV01)
    assert case.scenario.synthetic is True
    assert case.provenance is None
    assert case.provenance_document == b""
    assert case.provenance_sha256 is None
    assert case.source_hashes == {}


@pytest.mark.parametrize("value", [0, 1, "false", "true"])
def test_synthetic_flag_requires_a_real_boolean(value: Any) -> None:
    """Reject string and numeric flags instead of silently relabeling provenance."""
    data = json.loads((_DEV01 / "inputs.json").read_text())
    data["synthetic"] = value
    with pytest.raises(ValueError):
        Scenario.model_validate(data)


@pytest.mark.parametrize("missing", ["manifest", "root", "archive"])
def test_real_source_case_requires_manifest_and_local_archive(
    tmp_path: Path, missing: str
) -> None:
    """Refuse unverified source references without fetching replacement content."""
    bundle = _bundle(tmp_path)
    root: Path | None = bundle.archive
    if missing == "manifest":
        (bundle.directory / "provenance.json").unlink()
    elif missing == "root":
        root = None
    else:
        (bundle.archive / "publisher" / "release.html").unlink()
    with pytest.raises((ValueError, OSError)):
        load_case(bundle.directory, evidence_root=root)


def test_modified_archive_or_evidence_is_rejected(tmp_path: Path) -> None:
    """Detect byte tampering and changed record values independently of mapping IDs."""
    bundle = _bundle(tmp_path)
    snapshot = bundle.archive / "publisher" / "release.html"
    original = snapshot.read_bytes()
    snapshot.write_bytes(original + b"changed")
    with pytest.raises(ValueError):
        load_case(bundle.directory, evidence_root=bundle.archive)
    snapshot.write_bytes(original)
    for records in (
        bundle.reference["reference_evidence"],
        bundle.inputs["tool_fixtures"][0]["output"]["evidence"],
    ):
        records[0]["payload"]["price"] = 101
    bundle.save()
    with pytest.raises(ValueError):
        load_case(bundle.directory, evidence_root=bundle.archive)


@pytest.mark.parametrize(
    "path",
    [
        "../release.html",
        "/absolute.html",
        "publisher/../../escape.html",
        "publisher\\release.html",
        "C:\\release.html",
    ],
)
def test_snapshot_paths_cannot_escape_archive(tmp_path: Path, path: str) -> None:
    """Reject absolute, parent-traversal, and platform-ambiguous snapshot paths."""
    bundle = _bundle(tmp_path)
    bundle.manifest["sources"][0]["snapshot_path"] = path
    bundle.save()
    with pytest.raises(ValueError):
        load_case(bundle.directory, evidence_root=bundle.archive)


def test_snapshot_symlink_cannot_escape_archive(tmp_path: Path) -> None:
    """Check resolved containment even when the archive hash matches the target."""
    bundle = _bundle(tmp_path)
    snapshot = bundle.archive / "publisher" / "release.html"
    outside = tmp_path / "outside.html"
    outside.write_bytes(snapshot.read_bytes())
    snapshot.unlink()
    snapshot.symlink_to(outside)
    with pytest.raises(ValueError):
        load_case(bundle.directory, evidence_root=bundle.archive)


@pytest.mark.parametrize(
    "problem",
    [
        "missing_evidence",
        "unknown_evidence",
        "duplicate_evidence",
        "duplicate_source",
        "unused_source",
        "unknown_source",
        "no_primary",
    ],
)
def test_evidence_and_source_mappings_are_complete_and_unambiguous(
    tmp_path: Path, problem: str
) -> None:
    """Require exact evidence coverage and one usable mapping per source ID."""
    bundle = _bundle(tmp_path)
    links, sources = bundle.manifest["evidence"], bundle.manifest["sources"]
    if problem == "missing_evidence":
        links.pop()
    elif problem == "unknown_evidence":
        links.append({**links[-1], "evidence_id": "unknown"})
    elif problem == "duplicate_evidence":
        links.append(deepcopy(links[0]))
    elif problem == "duplicate_source":
        sources.append(deepcopy(sources[0]))
    elif problem == "unused_source":
        sources.append({**sources[0], "id": "unused"})
    elif problem == "unknown_source":
        links[0]["source_id"] = "missing"
    else:
        _change_records(bundle, links[0]["evidence_id"], "source", "assumed_quote")
        _change_records(bundle, links[0]["evidence_id"], "url", None)
        links[0].update(
            origin="scenario_assumption", source_id=None, note="Hypothetical quote."
        )
        sources.clear()
    bundle.save()
    with pytest.raises(ValueError):
        load_case(bundle.directory, evidence_root=bundle.archive)


def test_reference_only_evidence_also_requires_coverage(tmp_path: Path) -> None:
    """Cover the union of agent-visible and evaluator-only evidence records."""
    bundle = _bundle(tmp_path)
    extra = deepcopy(bundle.reference["reference_evidence"][-1])
    extra["id"] = "REFERENCE-ONLY"
    bundle.reference["reference_evidence"].append(extra)
    bundle.save()
    with pytest.raises(ValueError):
        load_case(bundle.directory, evidence_root=bundle.archive)
    bundle.manifest["evidence"].append(
        {
            **bundle.manifest["evidence"][-1],
            "evidence_id": extra["id"],
            "evidence_sha256": _canonical(extra),
        }
    )
    bundle.save()
    assert (
        load_case(bundle.directory, evidence_root=bundle.archive).provenance is not None
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("available_at", "2026-09-16T00:00:00Z"),
        ("available_at", "2026-09-15T13:58:00Z"),
        ("available_at", "2026-09-15T13:59:00"),
        ("published_date", "2026-09-16"),
        ("retrieved_at", "2026-09-14T00:00:00Z"),
        ("retrieved_at", "2026-11-10T08:00:00"),
        ("availability_basis", " "),
        ("title", " "),
        ("url", "file:///private/source.html"),
        ("sha256", "not-a-hash"),
    ],
)
def test_source_dates_and_required_descriptions_are_validated(
    tmp_path: Path, field: str, value: str
) -> None:
    """Reject future or ambiguous availability and incomplete source descriptors."""
    bundle = _bundle(tmp_path)
    bundle.manifest["sources"][0][field] = value
    bundle.save()
    with pytest.raises(ValueError):
        load_case(bundle.directory, evidence_root=bundle.archive)


@pytest.mark.parametrize(
    ("index", "field", "value"),
    [
        (0, "source", "different_source"),
        (0, "url", "https://example.test/wrong-release"),
        (1, "source", "unmarked_account"),
        (1, "url", "https://example.test/claimed-account"),
    ],
)
def test_record_source_identity_matches_its_origin(
    tmp_path: Path, index: int, field: str, value: str
) -> None:
    """Keep assumption records visibly distinct from named primary-source records."""
    bundle = _bundle(tmp_path)
    evidence_id = bundle.manifest["evidence"][index]["evidence_id"]
    _change_records(bundle, evidence_id, field, value)
    bundle.save()
    with pytest.raises(ValueError):
        load_case(bundle.directory, evidence_root=bundle.archive)


@pytest.mark.parametrize(
    ("index", "field", "value"),
    [
        (0, "origin", "trusted"),
        (0, "locator", " "),
        (1, "note", " "),
        (1, "source_id", _SOURCE_ID),
    ],
)
def test_origins_locators_and_assumption_notes_cannot_be_faked(
    tmp_path: Path, index: int, field: str, value: str
) -> None:
    """Require explicit origins and descriptions without granting approval."""
    bundle = _bundle(tmp_path)
    bundle.manifest["evidence"][index][field] = value
    bundle.save()
    with pytest.raises(ValueError):
        load_case(bundle.directory, evidence_root=bundle.archive)


@pytest.mark.parametrize(
    "target", ["manifest_scenario", "manifest_status", "reference_status"]
)
def test_provenance_cannot_claim_another_case_or_completed_review(
    tmp_path: Path, target: str
) -> None:
    """Keep the current provenance boundary explicitly pending human review."""
    bundle = _bundle(tmp_path)
    if target == "manifest_scenario":
        bundle.manifest["scenario_id"] = "OTHER-CASE"
    elif target == "manifest_status":
        bundle.manifest["status"] = "reviewed"
    else:
        bundle.reference["provenance_status"] = "reviewed"
    bundle.save()
    with pytest.raises(ValueError):
        load_case(bundle.directory, evidence_root=bundle.archive)


def test_suite_and_run_keep_verified_provenance_outside_agent_messages(
    tmp_path: Path,
) -> None:
    """Propagate archive validation and persist provenance without exposing its map."""
    bundle = _bundle(tmp_path)
    suite = _suite(bundle)
    with pytest.raises((ValueError, OSError)):
        load_suite(suite)
    _, cases = load_suite(suite, evidence_root=bundle.archive)
    case = cases[0]
    output = tmp_path / "run"
    record = asyncio.run(run_case(case, output, RunConfig()))
    assert record.status == "ok", record.errors
    assert (output / "provenance.json").read_bytes() == case.provenance_document
    assert record.metadata["provenance_sha256"] == case.provenance_sha256
    assert record.metadata["source_hashes"] == case.source_hashes
    trace = json.dumps(record.trace)
    assert "snapshot_path" not in trace
    assert case.provenance_sha256 is not None
    assert case.provenance_sha256 not in trace
    assert str(bundle.archive) not in json.dumps(record.model_dump(mode="json"))


def test_review_export_preserves_provenance_and_distinguishes_mixed_inputs(
    tmp_path: Path,
) -> None:
    """Retain the archived mapping while leaving calibration expectations private."""
    bundle = _bundle(tmp_path)
    output = tmp_path / "review"
    manifest = write_reference_review(
        _suite(bundle),
        [_DEV01],
        _EVAL / "calibration" / "dev01.json",
        _DEV01,
        output,
        evidence_root=bundle.archive,
    )
    case = load_case(bundle.directory, evidence_root=bundle.archive)
    folder = output / "cases" / case.scenario.scenario_id
    assert (folder / "provenance.json").read_bytes() == case.provenance_document
    assert case.provenance_sha256 is not None
    assert case.provenance_sha256 in json.dumps(manifest)
    assert "All inputs are synthetic" not in (folder / "case.md").read_text()
    assert (
        "All cases and predefined examples are synthetic"
        not in (output / "README.md").read_text()
    )
    blind = "\n".join(
        path.read_text()
        for path in (output / "calibration" / "blind").rglob("*")
        if path.is_file()
    )
    assert "snapshot_path" not in blind
    assert "reference_expectations" not in blind
