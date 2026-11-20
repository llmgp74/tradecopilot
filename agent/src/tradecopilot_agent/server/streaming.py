"""Graph input selection and SSE framing for the chat endpoint."""

import json
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.messages.tool import ToolCall
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from tradecopilot_agent.server.ai_sdk.adapter import (
    INTERNAL_ERROR_MESSAGE,
    to_ui_message_stream,
)
from tradecopilot_agent.server.ai_sdk.convert import to_human_message
from tradecopilot_agent.server.ai_sdk.types import (
    ApprovalDescriptor,
    UIMessage,
    UIMessageChunk,
)
from tradecopilot_agent.server.ai_sdk.utils import (
    tool_args_key,
    tool_call_args,
    tool_call_id,
    tool_call_name,
)

STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "x-vercel-ai-ui-message-stream": "v1",
}

AUTO_REJECT_REASON = "Superseded by a new message."

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GraphTurn:
    """One graph invocation and the state facts the adapter needs.

    Attributes:
        graph_input: New user message or a resume command.
        history_ids: Message ids already checkpointed before this run.
        unfinished_tool_calls: Tool calls without a result in the checkpoint.
            A resumed run re-emits their input so the upcoming result has a
            matching part in the new assistant message.
    """

    graph_input: dict[str, Any] | Command[Any]
    history_ids: set[str]
    unfinished_tool_calls: list[ToolCall]


async def sse(parts: AsyncIterator[UIMessageChunk]) -> AsyncIterator[str]:
    """Frame UI message parts as Server-Sent Events.

    Args:
        parts: UI message stream parts.

    Yields:
        SSE frames, ending with the `[DONE]` marker.
    """
    async for part in parts:
        payload = json.dumps(part, separators=(",", ":"), default=str)
        yield f"data: {payload}\n\n"
    yield "data: [DONE]\n\n"


async def stream_chat(
    graph: Any,
    messages: list[UIMessage],
    thread_id: str,
    config: RunnableConfig,
    approval_descriptor: ApprovalDescriptor | None = None,
) -> AsyncIterator[UIMessageChunk]:
    """Run one graph turn and stream its UI message parts.

    Args:
        graph: Compiled graph with an SQLite checkpointer.
        messages: UI messages from the AI SDK request.
        thread_id: Conversation thread id.
        config: Runnable config carrying the thread id.
        approval_descriptor: Builds the descriptor for approval requests.

    Yields:
        UI message stream parts.
    """
    assistant_id = f"msg-{uuid4().hex}"
    thread_part: UIMessageChunk = {
        "type": "data-thread",
        "data": {"thread_id": thread_id},
        "transient": True,
    }
    try:
        snapshot = await graph.aget_state(config)
        if _needs_auto_reject(snapshot, messages):
            resume = reject_resume(snapshot)
            async for _ in graph.astream(
                Command(resume=resume), config, stream_mode=["values"]
            ):
                pass
        turn = await _resolve_input(graph, messages, config, snapshot)
    except ValueError as exc:
        yield {"type": "start", "messageId": assistant_id}
        yield thread_part
        yield {"type": "error", "errorText": str(exc)}
        yield {"type": "finish"}
        return
    except Exception:
        logger.exception("Chat input resolution failed")
        yield {"type": "start", "messageId": assistant_id}
        yield thread_part
        yield {"type": "error", "errorText": INTERNAL_ERROR_MESSAGE}
        yield {"type": "finish"}
        return

    events = graph.astream(
        turn.graph_input,
        config,
        stream_mode=["messages", "values", "custom"],
        subgraphs=False,
    )
    async for part in to_ui_message_stream(
        events,
        message_id=assistant_id,
        history_message_ids=turn.history_ids,
        unfinished_tool_calls=turn.unfinished_tool_calls,
        approval_descriptor=approval_descriptor,
        start_parts=[thread_part],
    ):
        yield part


def _needs_auto_reject(snapshot: Any, messages: list[UIMessage]) -> bool:
    """Whether a new user message arrives while an approval is pending.

    The user did not approve or reject; the pending ticket is rejected so the
    conversation can continue instead of blocking on a decision.

    Args:
        snapshot: Graph state snapshot.
        messages: UI messages from the request.

    Returns:
        True when a new message supersedes a pending approval.
    """
    if not messages or messages[-1].get("role") != "user":
        return False
    return bool(_actionable_interrupts(getattr(snapshot, "interrupts", ())))


async def _resolve_input(
    graph: Any,
    messages: list[UIMessage],
    config: RunnableConfig,
    snapshot: Any,
) -> GraphTurn:
    values = getattr(snapshot, "values", {})
    history_ids = _message_ids(values)
    responses = find_approval_responses(messages)
    if responses:
        resume = build_resume(snapshot, responses)
        return GraphTurn(
            graph_input=Command(resume=resume),
            history_ids=history_ids,
            unfinished_tool_calls=_unfinished_tool_calls(values),
        )
    human = to_human_message(last_user_message(messages))
    return GraphTurn(
        graph_input={"messages": [human]},
        history_ids=history_ids,
        unfinished_tool_calls=[],
    )


def find_approval_responses(
    messages: list[UIMessage],
) -> list[dict[str, Any]]:
    """Return tool approval responses from the last assistant message.

    Args:
        messages: UI messages from the request.

    Returns:
        Approval response parts, or an empty list.
    """
    if not messages:
        return []
    last = messages[-1]
    if last.get("role") != "assistant":
        return []
    parts = last.get("parts")
    if not isinstance(parts, list):
        return []
    responses: list[dict[str, Any]] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        if part.get("state") != "approval-responded":
            continue
        approval = part.get("approval")
        if not isinstance(approval, dict):
            continue
        approval_id = approval.get("id")
        if not isinstance(approval_id, str) or not approval_id:
            continue
        responses.append(
            {
                "approvalId": approval_id,
                "approved": approval.get("approved") is True,
                "reason": approval.get("reason"),
            }
        )
    return responses


def last_user_message(messages: list[UIMessage]) -> UIMessage:
    """Return the last message when it is a user message.

    Args:
        messages: UI messages from the request.

    Returns:
        The last user message.

    Raises:
        ValueError: If the last message is not from the user.
    """
    if not messages or messages[-1].get("role") != "user":
        raise ValueError("The last message must be a user message.")
    return messages[-1]


def build_resume(snapshot: Any, responses: list[dict[str, Any]]) -> dict[str, Any]:
    """Map UI approval responses to a LangGraph resume value.

    Each interrupt carries its own action requests, so decisions are grouped
    per interrupt. One interrupt resumes with the decisions object. Two or more
    need a mapping keyed by interrupt id, which is how LangGraph tells them
    apart.

    Args:
        snapshot: Graph state snapshot containing pending interrupts.
        responses: Tool approval response parts.

    Returns:
        The resume value for ``Command``.

    Raises:
        ValueError: If no interrupt is actionable, an interrupt has no id, or
            a response cannot be matched to a tool call.
    """
    interrupts = _actionable_interrupts(getattr(snapshot, "interrupts", ()))
    if not interrupts:
        raise ValueError("No approval is pending for this thread.")
    assistant = _last_ai_message(getattr(snapshot, "values", {}))
    by_id = {
        approval_id: response
        for response in responses
        if (approval_id := _approval_id(response)) is not None
    }

    def decisions_for(interrupt: Any) -> list[dict[str, Any]]:
        decisions: list[dict[str, Any]] = []
        for request in _action_requests(interrupt):
            call_id = _request_call_id(request, assistant)
            response = by_id.get(call_id) if call_id is not None else None
            if response is None:
                raise ValueError(
                    "Approval response does not match a pending tool call."
                )
            decisions.append(_decision(response))
        return decisions

    return _group_resume(interrupts, decisions_for)


def reject_resume(snapshot: Any) -> Any:
    """Build the resume value that rejects every pending approval.

    Args:
        snapshot: Graph state snapshot containing pending interrupts.

    Returns:
        The resume value for ``Command``.

    Raises:
        ValueError: If no interrupt is pending or it has no id.
    """
    interrupts = _actionable_interrupts(getattr(snapshot, "interrupts", ()))
    if not interrupts:
        raise ValueError("No approval is pending for this thread.")
    return _group_resume(
        interrupts,
        lambda interrupt: [
            {"type": "reject", "message": AUTO_REJECT_REASON}
            for _ in _action_requests(interrupt)
        ],
    )


def _group_resume(
    interrupts: list[Any],
    decisions_for: Callable[[Any], list[dict[str, Any]]],
) -> dict[str, Any]:
    by_interrupt: dict[str, dict[str, Any]] = {}
    for interrupt in interrupts:
        interrupt_id = getattr(interrupt, "id", None)
        if not isinstance(interrupt_id, str) or not interrupt_id:
            raise ValueError("Cannot identify the pending interrupt.")
        by_interrupt[interrupt_id] = {"decisions": decisions_for(interrupt)}
    if len(by_interrupt) == 1:
        return next(iter(by_interrupt.values()))
    return by_interrupt


def _actionable_interrupts(interrupts: Any) -> list[Any]:
    return [interrupt for interrupt in interrupts or () if _action_requests(interrupt)]


def _action_requests(interrupt: Any) -> list[dict[str, Any]]:
    value = getattr(interrupt, "value", None)
    if not isinstance(value, dict):
        return []
    raw = value.get("action_requests")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _last_ai_message(values: Any) -> AIMessage | None:
    if not isinstance(values, dict):
        return None
    messages = values.get("messages")
    if not isinstance(messages, list):
        return None
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return message
    return None


def _request_call_id(
    request: dict[str, Any],
    assistant: AIMessage | None,
) -> str | None:
    explicit = request.get("tool_call_id")
    if isinstance(explicit, str) and explicit:
        return explicit
    name = request.get("name")
    raw_args = request.get("args") or request.get("arguments")
    args = raw_args if isinstance(raw_args, dict) else {}
    if assistant is None:
        return None
    key = tool_args_key(str(name), args)
    for call in assistant.tool_calls:
        if tool_args_key(tool_call_name(call), tool_call_args(call)) == key:
            return tool_call_id(call)
    return None


def _approval_id(response: dict[str, Any]) -> str | None:
    value = response.get("approvalId")
    return value if isinstance(value, str) and value else None


def _decision(response: dict[str, Any]) -> dict[str, Any]:
    if response.get("approved") is True:
        return {"type": "approve"}
    reason = response.get("reason")
    message = reason if isinstance(reason, str) and reason else "Rejected"
    return {"type": "reject", "message": message}


def _message_ids(values: Any) -> set[str]:
    if not isinstance(values, dict):
        return set()
    messages = values.get("messages")
    if not isinstance(messages, list):
        return set()
    return {
        message.id
        for message in messages
        if isinstance(message, BaseMessage) and message.id is not None
    }


def _unfinished_tool_calls(values: Any) -> list[ToolCall]:
    if not isinstance(values, dict):
        return []
    messages = values.get("messages")
    if not isinstance(messages, list):
        return []
    completed = {
        message.tool_call_id for message in messages if isinstance(message, ToolMessage)
    }
    calls: list[ToolCall] = []
    for message in messages:
        if isinstance(message, AIMessage):
            calls.extend(
                call for call in message.tool_calls if call.get("id") not in completed
            )
    return calls
