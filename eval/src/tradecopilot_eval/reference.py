"""Evaluator-only reference labels and a reproducible experiment schedule."""

import hashlib
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    model_validator,
)
from tradecopilot_agent.memory import MemoryCondition
from tradecopilot_agent.state import Claim, EvidenceRecord

from tradecopilot_eval.fixtures import Scenario, load_scenario


class ReferenceModel(BaseModel):
    """Reject misspelled reference fields instead of silently dropping labels."""

    model_config = ConfigDict(extra="forbid")


class ExpectedTicket(ReferenceModel):
    """Independently specified outcome for a predefined ticket."""

    violation_codes: list[str]
    eligible: bool
    resulting_position_value_usd: float | None = None
    resulting_weight_pct: float | None = None


class TicketCase(ReferenceModel):
    """A fixed tool call and its expected rule outcome."""

    id: str
    tool_arguments: dict[str, Any]
    expected: ExpectedTicket


class ClaimProbe(ReferenceModel):
    """An independently labeled claim for direct verifier checks."""

    id: str
    claim: Claim
    expected_verdict: Literal["supported", "contradicted", "unchecked", "unverifiable"]
    evidence_ids: list[str]


class Reference(ReferenceModel):
    """Reference context for scorers, never passed to the trading agent."""

    schema_version: Literal[1] = 1
    scenario_id: str
    split: Literal["development", "evaluation"]
    category: str = "portfolio"
    authorship: str = "Predefined synthetic reference labels."
    provenance_status: str = "synthetic_pending_review"
    calculation: dict[str, float] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    candidates: list[TicketCase] = Field(default_factory=list)
    claim_probes: list[ClaimProbe] = Field(default_factory=list)
    response_criteria: list[str]
    acceptable_outcomes: list[str] = Field(
        default_factory=lambda: ["recommendation", "no_trade", "needs_information"]
    )
    reference_evidence: list[EvidenceRecord] = Field(default_factory=list)


class Case(ReferenceModel):
    """Loaded inputs and labels, kept separate at the agent boundary."""

    scenario: Scenario
    reference: Reference
    input_sha256: str
    reference_sha256: str
    input_document: bytes = b""
    reference_document: bytes = b""


def file_digest(path: Path) -> str:
    """Return the SHA-256 of a file's exact bytes; propagate read errors."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_case(directory: Path) -> Case:
    """Load and cross-check a case, including reference evidence identifiers.

    Args:
        directory: Directory containing inputs.json and reference.json.

    Returns:
        Inputs, independent labels, and hashes for a run manifest.

    Raises:
        ValueError: Identifiers, splits, evidence, or reference links disagree.
        OSError: A case file cannot be read.
    """
    inputs = directory / "inputs.json"
    labels = directory / "reference.json"
    scenario = load_scenario(inputs)
    reference = Reference.model_validate_json(labels.read_text(encoding="utf-8"))
    if (scenario.scenario_id, scenario.split) != (
        reference.scenario_id,
        reference.split,
    ):
        raise ValueError("Case input and reference identifiers or splits disagree.")
    if not reference.reference_evidence:
        catalog = {
            item.id: item
            for fixture in scenario.tool_fixtures
            for item in fixture.output.evidence
        }
        reference.reference_evidence = list(catalog.values())
    ids = [record.id for record in reference.reference_evidence]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate reference evidence IDs.")
    time_parser = TypeAdapter(AwareDatetime)
    source_records: dict[str, EvidenceRecord] = {}
    for fixture in scenario.tool_fixtures:
        if fixture.available_at > scenario.decision_time:
            raise ValueError("A fixture was unavailable at the decision time.")
        for record in fixture.output.evidence:
            existing = source_records.get(record.id)
            if existing is not None and existing != record:
                raise ValueError("Conflicting fixture records share an evidence ID.")
            source_records[record.id] = record
    for record in [*source_records.values(), *reference.reference_evidence]:
        if record.published_at is None:
            raise ValueError("Frozen evidence requires a publication timestamp.")
        if time_parser.validate_python(record.published_at) > scenario.decision_time:
            raise ValueError("Evidence was unavailable at the decision time.")
    for record in reference.reference_evidence:
        if record.id in source_records and source_records[record.id] != record:
            raise ValueError("Reference and tool evidence disagree for the same ID.")
    for probe in reference.claim_probes:
        if not set(probe.evidence_ids) <= set(ids):
            raise ValueError(f"Unknown reference evidence in {probe.id}.")
    return Case(
        scenario=scenario,
        reference=reference,
        input_sha256=file_digest(inputs),
        reference_sha256=file_digest(labels),
        input_document=inputs.read_bytes(),
        reference_document=labels.read_bytes(),
    )


class Suite(ReferenceModel):
    """A fixed full-system screening and repeated memory comparison schedule."""

    schema_version: Literal[1] = 1
    suite_id: str
    description: str
    scenario_paths: list[str]
    ablation_scenarios: list[str]
    repetitions: int = Field(ge=1, le=100)
    conditions: list[MemoryCondition]
    full_condition: Literal["full"] = "full"
    seed: int = 74
    provenance_status: str = "synthetic_pending_review"

    @model_validator(mode="after")
    def check_conditions(self) -> "Suite":
        """Require each of the four memory conditions exactly once."""
        if sorted(self.conditions) != ["full", "none", "prose", "structured"]:
            raise ValueError("The comparison needs all four distinct conditions.")
        if len(set(self.ablation_scenarios)) != len(self.ablation_scenarios):
            raise ValueError("Repeated ablation scenario identifiers.")
        return self


def load_suite(path: Path) -> tuple[Suite, list[Case]]:
    """Load a suite and reject duplicate cases or unknown comparison members.

    Args:
        path: Suite JSON; scenario paths resolve relative to this file.

    Returns:
        The schedule and loaded cases in declared order.

    Raises:
        OSError: A required file cannot be read.
        ValueError: Case or schedule validation fails.
    """
    suite = Suite.model_validate_json(path.read_text(encoding="utf-8"))
    cases = [load_case(path.parent / relative) for relative in suite.scenario_paths]
    ids = [case.scenario.scenario_id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Suite contains duplicate scenario IDs.")
    if not set(suite.ablation_scenarios) <= set(ids):
        raise ValueError("Ablation scenario is absent from the suite.")
    return suite, cases
