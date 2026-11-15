"""Persisted evaluation records; missing observations remain null."""

from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field
from tradecopilot_agent.memory import MemoryCondition


class Record(BaseModel):
    """Forbid unknown fields in files used for reporting."""

    model_config = ConfigDict(extra="forbid")


class Proposal(Record):
    """One original tool call paired with its result by call ID."""

    call_id: str
    message_index: int
    arguments: dict[str, Any]
    output: dict[str, Any] | None = None
    capture_error: str | None = None


PROJECTION_VERSION: Final = "visible-response-v2"


class PlanItem(Record):
    """The two fields displayed for a step in the chat plan."""

    content: str
    status: str


class ChatAnswer(Record):
    """Final assistant text and plan displayed for a frozen evaluation turn."""

    text: str = ""
    todos: list[PlanItem] = Field(default_factory=list)


class VisibleResponse(Record):
    """Archived v1 projection, including fields taken directly from graph state."""

    text: str = ""
    draft_recommendation: dict[str, Any] | None = None
    portfolio_impact: dict[str, Any] | None = None
    verification: list[dict[str, Any]] = Field(default_factory=list)
    todos: list[dict[str, Any]] = Field(default_factory=list)


class Usage(Record):
    """Usage reported by model callbacks during a run."""

    model_calls: int = 0
    calls_with_usage: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    elapsed_seconds: float | None = None


class RunRecord(Record):
    """One isolated trial, including partial traces when a run fails."""

    schema_version: Literal[1] = 1
    run_id: str
    scenario_id: str
    condition: MemoryCondition
    phase: Literal["screening", "ablation", "single"]
    repetition: int
    mode: Literal["scripted", "model"]
    model_id: str
    model_family: str
    status: Literal["ok", "agent_error", "timeout", "invalid_output"]
    errors: list[str] = Field(default_factory=list)
    initial_proposal_ids: list[str] = Field(default_factory=list)
    proposals: list[Proposal] = Field(default_factory=list)
    final_response: ChatAnswer | VisibleResponse = Field(default_factory=ChatAnswer)
    final_draft: dict[str, Any] | None = None
    trace: list[dict[str, Any]] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    tool_errors: list[dict[str, Any]] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    metadata: dict[str, Any] = Field(default_factory=dict)
    scores: dict[str, Any] = Field(default_factory=dict)
    judge: dict[str, Any] | None = None
