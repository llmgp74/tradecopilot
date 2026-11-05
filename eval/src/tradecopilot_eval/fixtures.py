"""Load development inputs without reading evaluator reference answers."""

from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, TypeAdapter, model_validator
from tradecopilot_agent.models import JournalEntry, Profile
from tradecopilot_agent.state import ToolOutput
from tradecopilot_agent.store import Store


class ToolFixture(BaseModel):
    """One frozen response for an exact data-source call.

    Attributes:
        method: DataSource method name, excluding order execution.
        arguments: Normalized arguments expected from the agent tools.
        available_at: Earliest time the entire response was available.
        output: Shared agent ToolOutput, including model-facing summary.
    """

    model_config = ConfigDict(extra="forbid")

    method: Literal[
        "quote",
        "bars",
        "portfolio",
        "positions",
        "fundamentals",
        "filings",
        "xbrl_fact",
        "news",
        "macro",
    ]
    arguments: dict[str, Any]
    available_at: AwareDatetime
    output: ToolOutput


class Scenario(BaseModel):
    """Synthetic development inputs; reference answers belong in another file.

    Profile and journal dates must precede or equal decision_time. The source
    checks tool-response availability before returning either text or evidence.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    scenario_id: str
    split: Literal["development"]
    synthetic: Literal[True]
    decision_time: AwareDatetime
    request: str
    profile: Profile
    journal_before_decision: list[dict[str, Any]]
    tool_fixtures: list[ToolFixture]

    @property
    def as_of(self) -> date:
        """Return the scenario date accepted by the agent interface."""
        return self.decision_time.date()

    @model_validator(mode="after")
    def validate_memory_dates(self) -> "Scenario":
        """Reject malformed journal seeds and memory from after the decision.

        Returns:
            The validated scenario.

        Raises:
            ValueError: A seed lacks a decision id or has an invalid/future date.
        """
        timestamps = [self.profile.updated_at]
        for event in self.journal_before_decision:
            if not event.get("decision_id"):
                raise ValueError("Journal seeds need a decision_id.")
            entry = JournalEntry.model_validate({**event, "id": event["decision_id"]})
            timestamps.append(entry.created_at)
        for timestamp in timestamps:
            if (
                TypeAdapter(AwareDatetime).validate_python(timestamp)
                > self.decision_time
            ):
                raise ValueError("Memory is dated after the scenario decision.")
        return self


def load_scenario(path: Path) -> Scenario:
    """Read one inputs JSON file, without loading its reference answers.

    Args:
        path: Path to inputs.json in a development case directory.

    Returns:
        Validated inputs for the shared agent interface.

    Raises:
        OSError: The file cannot be read.
        ValueError: JSON, shared models, or memory timestamps are invalid.
    """
    return Scenario.model_validate_json(path.read_text(encoding="utf-8"))


def seed_store(scenario: Scenario, run_dir: Path) -> Store:
    """Seed a fresh local agent store without reading credentials or settings.

    Args:
        scenario: Confirmed profile and pre-decision journal inputs.
        run_dir: New directory for this run's database and settings.key.

    Returns:
        A store with the current profile and historical decision snapshots.
        Store stamps the profile with the write time; the original confirmation
        timestamp remains in inputs.json. Journal timestamps are preserved.

    Raises:
        FileExistsError: run_dir already exists; existing runs are never reused.
        OSError: The run directory or database cannot be created.
    """
    run_dir.mkdir(parents=True, exist_ok=False)
    store = Store(run_dir / "data.db")
    store.patch_profile(scenario.profile.model_dump(exclude={"updated_at"}))
    for event in scenario.journal_before_decision:
        store.append_journal(event)
    return store
