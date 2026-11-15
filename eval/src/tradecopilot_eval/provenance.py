"""Check local evidence archives and mappings without asserting factual accuracy."""

import hashlib
import json
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal
from urllib.parse import urldefrag

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    TypeAdapter,
    field_validator,
    model_validator,
)
from tradecopilot_agent.state import EvidenceRecord

from tradecopilot_eval.fixtures import Scenario

_Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
_Hash = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
_ASSUMED_PREFIXES = ("synthetic_", "assumed_")


class SourceArchive(BaseModel):
    """One declared publication and an external, locally archived snapshot."""

    model_config = ConfigDict(extra="forbid")

    id: _Text
    title: _Text
    url: _Text
    published_date: date
    available_at: AwareDatetime
    availability_basis: _Text
    retrieved_at: AwareDatetime
    snapshot_path: _Text
    sha256: _Hash
    content_type: _Text

    @field_validator("url")
    @classmethod
    def public_http_url(cls, value: str) -> str:
        """Require an HTTP(S) publication URL without embedded credentials."""
        parsed = TypeAdapter(HttpUrl).validate_python(value)
        if parsed.username or parsed.password:
            raise ValueError("Source URLs must not contain credentials.")
        return value

    @field_validator("snapshot_path")
    @classmethod
    def relative_snapshot_path(cls, value: str) -> str:
        """Reject absolute paths, traversal, and platform-dependent separators."""
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or "\\" in value
            or ":" in value
            or any(part in {"", ".", ".."} for part in value.split("/"))
        ):
            raise ValueError("snapshot_path must be a safe relative POSIX path.")
        return value

    @model_validator(mode="after")
    def consistent_dates_and_identity(self) -> "SourceArchive":
        """Keep publication, availability, and retrieval metadata chronological."""
        if self.id.startswith(_ASSUMED_PREFIXES):
            raise ValueError("Primary source IDs must not use assumption prefixes.")
        if self.published_date > self.available_at.date():
            raise ValueError("Source availability cannot precede publication.")
        if self.retrieved_at.date() < self.published_date:
            raise ValueError("Source retrieval cannot precede publication.")
        return self


class EvidenceOrigin(BaseModel):
    """A record's declared origin and an optional canonical-content binding."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: _Text
    origin: Literal["primary_source", "scenario_assumption"]
    source_id: _Text | None
    locator: _Text
    note: _Text
    evidence_sha256: _Hash | None = None

    @model_validator(mode="after")
    def consistent_origin(self) -> "EvidenceOrigin":
        """Require source links for primary records and none for assumptions."""
        if (self.origin == "primary_source") != (self.source_id is not None):
            raise ValueError("Only primary_source evidence must identify a source.")
        return self


class ProvenanceManifest(BaseModel):
    """Unreviewed publication metadata; validation does not prove source facts."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    scenario_id: _Text
    status: Literal["primary_source_pending_review"]
    sources: list[SourceArchive] = Field(min_length=1)
    evidence: list[EvidenceOrigin] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_complete_links(self) -> "ProvenanceManifest":
        """Reject duplicate IDs and unknown or unused source declarations."""
        sources = [source.id for source in self.sources]
        evidence = [entry.evidence_id for entry in self.evidence]
        if len(set(sources)) != len(sources) or len(set(evidence)) != len(evidence):
            raise ValueError("Duplicate provenance source or evidence IDs.")
        used = {entry.source_id for entry in self.evidence if entry.source_id}
        if used != set(sources):
            raise ValueError("Provenance has unknown or unused source IDs.")
        return self


def evidence_digest(record: EvidenceRecord) -> str:
    """Hash an evidence record's canonical validated JSON representation.

    Args:
        record: Shared evidence record, including metadata and payload.

    Returns:
        SHA-256 of sorted, compact, ASCII JSON encoded as UTF-8.

    Raises:
        ValueError: The record contains a non-finite numeric value.
    """
    canonical = json.dumps(
        record.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _url(value: str | None) -> str:
    if value is None:
        raise ValueError("Primary evidence requires its publication URL.")
    return urldefrag(str(TypeAdapter(HttpUrl).validate_python(value)))[0].rstrip("/")


def _check_archive(source: SourceArchive, root: Path) -> None:
    path = (root / source.snapshot_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Snapshot path escapes evidence_root.")
    if not path.is_file():
        raise ValueError(f"Missing source archive: {source.snapshot_path}")
    if hashlib.sha256(path.read_bytes()).hexdigest() != source.sha256:
        raise ValueError(f"Source archive SHA-256 mismatch: {source.id}")


def _check_record(
    entry: EvidenceOrigin,
    record: EvidenceRecord,
    sources: dict[str, SourceArchive],
) -> None:
    if entry.evidence_sha256 and evidence_digest(record) != entry.evidence_sha256:
        raise ValueError(f"Evidence content SHA-256 mismatch: {record.id}")
    if entry.origin == "scenario_assumption":
        if not record.source.startswith(_ASSUMED_PREFIXES) or record.url is not None:
            raise ValueError(
                "Assumed records need an assumption source prefix and no URL."
            )
        return
    if record.payload.get("kind") == "account" or record.tool in {
        "get_portfolio",
        "get_positions",
    }:
        raise ValueError(
            "Account and portfolio records must remain scenario assumptions."
        )
    assert entry.source_id is not None
    source = sources[entry.source_id]
    if record.source != source.id or _url(record.url) != _url(source.url):
        raise ValueError(
            f"Evidence source or URL does not match provenance: {record.id}"
        )
    fetched = TypeAdapter(AwareDatetime).validate_python(record.fetched_at)
    if fetched != source.retrieved_at:
        raise ValueError(
            f"Evidence fetched_at must match source retrieved_at: {record.id}"
        )
    published = TypeAdapter(AwareDatetime).validate_python(record.published_at)
    if published > source.available_at:
        raise ValueError(
            f"Evidence publication is after source availability: {record.id}"
        )
    if published.date() < source.published_date:
        raise ValueError(f"Evidence publication precedes the source date: {record.id}")
    if source.retrieved_at < published:
        raise ValueError(f"Source retrieval precedes evidence publication: {record.id}")


def load_provenance(
    path: Path,
    scenario: Scenario,
    records: dict[str, EvidenceRecord],
    *,
    evidence_root: Path | None,
) -> tuple[ProvenanceManifest, bytes]:
    """Validate a manifest and local source archives before exposing a real case.

    Args:
        path: The case's adjacent provenance.json file.
        scenario: Validated scenario and its decision cutoff.
        records: Union of tool and reference records, keyed by evidence ID.
        evidence_root: Explicit root of external archive files; never persisted.

    Returns:
        Validated manifest and its exact original bytes. These mechanical checks
        establish file and mapping consistency, not source authenticity or facts.

    Raises:
        ValueError: An archive, mapping, date, or source declaration is invalid.
        OSError: A required manifest cannot be read.
    """
    if evidence_root is None:
        raise ValueError("Real-source cases require an explicit evidence_root archive.")
    root = evidence_root.resolve()
    if not root.is_dir():
        raise ValueError("evidence_root must be an existing archive directory.")
    document = path.read_bytes()
    manifest = ProvenanceManifest.model_validate_json(document)
    if manifest.scenario_id != scenario.scenario_id:
        raise ValueError("Provenance scenario ID does not match the case.")
    if {entry.evidence_id for entry in manifest.evidence} != set(records):
        raise ValueError(
            "Provenance must cover exactly all tool and reference evidence IDs."
        )
    sources = {source.id: source for source in manifest.sources}
    for source in manifest.sources:
        if source.available_at > scenario.decision_time:
            raise ValueError("A provenance source was unavailable at decision time.")
        _check_archive(source, root)
    entries = {entry.evidence_id: entry for entry in manifest.evidence}
    for entry in manifest.evidence:
        _check_record(entry, records[entry.evidence_id], sources)
    for fixture in scenario.tool_fixtures:
        for record in fixture.output.evidence:
            source_id = entries[record.id].source_id
            if source_id and fixture.available_at < sources[source_id].available_at:
                raise ValueError("A fixture cannot be available before its source.")
    return manifest, document
