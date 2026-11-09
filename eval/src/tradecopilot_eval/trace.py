"""Keep pre-check proposals and tool artifacts without inferring hidden output."""

from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
    message_to_dict,
)

from tradecopilot_eval.records import Proposal, VisibleResponse


def capture_proposals(messages: list[BaseMessage]) -> tuple[list[Proposal], list[str]]:
    """Pair all proposal attempts in the current turn, preserving parallel calls.

    Args:
        messages: Returned graph messages, possibly including earlier turns.

    Returns:
        All attempts and the IDs in the first proposing assistant message.
        Missing/duplicate call IDs or artifacts remain explicit capture errors.
    """
    start = max(
        (i + 1 for i, item in enumerate(messages) if isinstance(item, HumanMessage)),
        default=0,
    )
    attempts: list[Proposal] = []
    first_ids: list[str] = []
    results: dict[str, list[ToolMessage]] = {}
    for item in messages[start:]:
        if isinstance(item, ToolMessage):
            results.setdefault(item.tool_call_id, []).append(item)
    for index, item in enumerate(messages[start:], start=start):
        if not isinstance(item, AIMessage):
            continue
        batch: list[str] = []
        for call in item.tool_calls:
            if call.get("name") != "propose_ticket":
                continue
            call_id = str(call.get("id") or f"missing-id-{index}-{len(batch)}")
            matches = results.get(call_id, [])
            error = None
            output = None
            if not call.get("id"):
                error = "missing_call_id"
            elif len(matches) != 1:
                error = "missing_or_duplicate_tool_result"
            elif not isinstance(matches[0].artifact, dict):
                error = "missing_tool_artifact"
            else:
                output = dict(matches[0].artifact)
            attempts.append(
                Proposal(
                    call_id=call_id,
                    message_index=index,
                    arguments=dict(call["args"]),
                    output=output,
                    capture_error=error,
                )
            )
            batch.append(call_id)
        if batch and not first_ids:
            first_ids = batch
    seen: set[str] = set()
    for attempt in attempts:
        if attempt.call_id in seen:
            for duplicate in attempts:
                if duplicate.call_id == attempt.call_id:
                    duplicate.capture_error = "duplicate_proposal_call_id"
        seen.add(attempt.call_id)
    return attempts, first_ids


def response_projection(state: dict[str, Any]) -> VisibleResponse:
    """Return the last answer and the five visible contract fields.

    Args:
        state: Final or latest available graph state.

    Returns:
        A versioned-by-run-metadata projection with no private memory labels.
    """
    messages = list(state.get("messages", []))
    text = ""
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            break
        if isinstance(message, AIMessage) and not message.tool_calls:
            content = message.content
            if isinstance(content, str):
                text = content
            else:
                text = "\n".join(
                    part if isinstance(part, str) else str(part.get("text", ""))
                    for part in content
                )
            break
    return VisibleResponse(
        text=text,
        draft_recommendation=state.get("draft_recommendation"),
        portfolio_impact=state.get("portfolio_impact"),
        verification=state.get("verification", []),
        todos=state.get("todos", []),
    )


def serialize_trace(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    """Serialize complete messages, retaining tool-call IDs and artifacts."""
    return [message_to_dict(message) for message in messages]
