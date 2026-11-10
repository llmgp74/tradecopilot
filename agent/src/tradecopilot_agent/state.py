"""Domain models and the agent graph state."""

from typing import Annotated, Any, Literal, NotRequired

from deepagents import DeepAgentState
from pydantic import BaseModel, Field

EVIDENCE_CAP = 200

Side = Literal["buy", "sell"]
VerdictKind = Literal["supported", "contradicted", "unchecked", "unverifiable"]
ClaimKind = Literal["numeric", "filing", "news", "opinion"]


class EvidenceRecord(BaseModel):
    """One tool result with provenance.

    Attributes:
        id: Stable id derived from the tool, args, source, and publish time.
        tool: Tool name that produced the record.
        args: Normalized tool arguments.
        source: Provider name, or ``portfolio_simulation`` for computed facts.
        url: Human-readable source when the provider offers one.
        published_at: Source timestamp, ISO 8601.
        fetched_at: Time the record was fetched, ISO 8601.
        stale: Whether the record is too old for its purpose.
        payload: The fact, trimmed for the ledger.
    """

    id: str
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    source: str
    url: str | None = None
    published_at: str | None = None
    fetched_at: str
    stale: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)


class ToolOutput(BaseModel):
    """What every trading tool returns.

    Attributes:
        summary: Compact text for the model.
        evidence: Records to append to the ledger.
        error: Set when the source could not answer.
    """

    summary: str
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    error: str | None = None
    proposal: dict[str, Any] | None = None
    portfolio_impact: dict[str, Any] | None = None
    verification: list[dict[str, Any]] = Field(default_factory=list)
    ticket_done: bool = False


class Claim(BaseModel):
    """One factual assertion extracted from prose."""

    text: str
    kind: ClaimKind
    ticker: str | None = None
    tag: str | None = None
    value: float | None = None
    unit: str | None = None
    period: str | None = None
    accession: str | None = None
    filing_type: str | None = None
    date: str | None = None
    evidence_hint: str | None = None


class OrderLeg(BaseModel):
    """One order inside a ticket."""

    ticker: str
    side: Side
    qty: float


class OrderTicket(BaseModel):
    """A proposed set of legs awaiting approval."""

    id: str
    legs: list[OrderLeg]
    thesis: str
    horizon: str
    created_at: str


def merge_evidence(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge ledger records and drop the oldest beyond the cap.

    Args:
        current: Records already in state.
        incoming: Records added by this update.

    Returns:
        The merged ledger, capped to the newest records.
    """
    merged = {**current, **incoming}
    if len(merged) <= EVIDENCE_CAP:
        return merged
    return dict(list(merged.items())[-EVIDENCE_CAP:])


def merge_verdicts(current: list[Any], incoming: list[Any]) -> list[Any]:
    """Merge verdicts by claim text, with the newest verdict winning.

    The claim checker may run more than once in a turn, for example when the
    model checks a first batch, gathers more evidence, then checks the rest.
    Replacing the whole channel would lose the earlier batches.

    Args:
        current: Verdicts already in state.
        incoming: New verdicts, each with a ``text``.

    Returns:
        The combined list, with one entry per claim text.
    """
    merged: dict[str, Any] = {
        str(item.get("text")): item for item in current if isinstance(item, dict)
    }
    for item in incoming:
        if isinstance(item, dict):
            merged[str(item.get("text"))] = item
    return list(merged.values())


class TradingState(DeepAgentState):
    """Graph state shared by tools, middleware, and the server."""

    evidence: NotRequired[Annotated[dict[str, Any], merge_evidence]]
    draft_recommendation: NotRequired[dict[str, Any] | None]
    verification: NotRequired[Annotated[list[Any], merge_verdicts]]
    portfolio_impact: NotRequired[dict[str, Any] | None]
    pending_ticket: NotRequired[dict[str, Any] | None]
    todos_snapshot: NotRequired[list[Any]]


TURN_FIELDS: dict[str, Any] = {
    "draft_recommendation": None,
    "portfolio_impact": None,
    "pending_ticket": None,
    "verification": [],
}
"""State values cleared when a new user turn starts."""
