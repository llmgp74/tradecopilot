"""Translate LangGraph stream events into AI SDK UI message parts.

The translation mirrors the LangGraph path of the official
``@ai-sdk/langchain`` adapter. Namespaces are parsed and attached as provider
metadata, but tool and message ids are deduplicated globally because this
server runs one agent.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Iterator, Sequence, Set
from typing import Any, cast

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.messages.tool import ToolCall

from tradecopilot_agent.server.ai_sdk.types import (
    ApprovalDescriptor,
    GraphEvent,
    LangGraphEventState,
    MessageSeen,
    UIMessageChunk,
)
from tradecopilot_agent.server.ai_sdk.utils import (
    is_ai_chunk,
    is_tool_message,
    message_id,
    message_reasoning,
    message_text,
    parse_langgraph_event,
    tool_args_key,
    tool_call_args,
    tool_call_id,
    tool_call_name,
    tool_error_text,
)

logger = logging.getLogger(__name__)

_NAMESPACED_PARTS = frozenset(
    {
        "text-start",
        "text-delta",
        "text-end",
        "reasoning-start",
        "reasoning-delta",
        "reasoning-end",
        "tool-input-start",
        "tool-input-available",
        "tool-output-available",
        "tool-output-error",
    }
)


async def to_ui_message_stream(
    stream: AsyncIterator[GraphEvent],
    *,
    message_id: str,
    history_message_ids: Set[str] = frozenset(),
    unfinished_tool_calls: Sequence[ToolCall | dict[str, Any]] = (),
    approval_descriptor: ApprovalDescriptor | None = None,
    start_parts: Sequence[UIMessageChunk] = (),
) -> AsyncIterator[UIMessageChunk]:
    """Convert a LangGraph event stream to AI SDK UI message parts.

    Args:
        stream: Events from `graph.astream` with `messages`, `values`, and
            `custom` modes.
        message_id: Id to use for the assistant message.
        history_message_ids: Message ids already present in the checkpoint
            before this run. They are not re-emitted.
        unfinished_tool_calls: Tool calls without a result in the checkpoint.
            A resumed run re-emits their input before the streamed result.
        approval_descriptor: Builds the descriptor attached to a tool approval
            request from the current graph state.
        start_parts: Extra parts emitted right after the `start` part.

    Yields:
        AI SDK UI message stream parts.
    """
    yield {"type": "start", "messageId": message_id}
    for part in start_parts:
        yield dict(part)

    state = LangGraphEventState()
    for call in unfinished_tool_calls:
        for part in _tool_input_parts(call, state):
            yield part

    try:
        async for event in stream:
            namespace, mode, data = parse_langgraph_event(event)
            for part in _process_event(
                mode,
                data,
                state,
                history_message_ids,
                approval_descriptor,
            ):
                yield _with_namespace(part, namespace)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("Chat stream failed")
        yield {"type": "error", "errorText": str(exc)}

    for part in _close_open(state):
        yield part
    if state.step_started:
        yield {"type": "finish-step"}
    yield {"type": "finish"}


def _process_event(
    mode: str,
    data: Any,
    state: LangGraphEventState,
    history_message_ids: Set[str],
    approval_descriptor: ApprovalDescriptor | None,
) -> Iterator[UIMessageChunk]:
    if mode == "messages":
        yield from _process_message_event(data, state)
    elif mode == "values":
        yield from _process_values_event(
            data, state, history_message_ids, approval_descriptor
        )
    elif mode == "custom":
        yield from _process_custom_event(data)


def _process_message_event(
    data: Any, state: LangGraphEventState
) -> Iterator[UIMessageChunk]:
    if not isinstance(data, (tuple, list)) or len(data) != 2:
        return
    message, metadata = data
    if not isinstance(message, BaseMessage):
        return
    meta = metadata if isinstance(metadata, dict) else {}
    yield from _step_parts(state, meta)

    stream_id = message_id(message, "message")
    if is_ai_chunk(message):
        chunk = cast(AIMessageChunk, message)
        previous = state.concat.get(stream_id)
        combined = previous + chunk if previous is not None else chunk
        state.concat[stream_id] = combined
        if chunk.tool_call_chunks:
            yield from _process_tool_chunks(chunk, stream_id, state)
            return

        reasoning = message_reasoning(chunk)
        if reasoning:
            seen = _seen(state, stream_id)
            if not seen.reasoning:
                seen.reasoning = True
                yield {"type": "reasoning-start", "id": stream_id}
            yield {
                "type": "reasoning-delta",
                "id": stream_id,
                "delta": reasoning,
            }

        text = message_text(chunk)
        if text:
            seen = _seen(state, stream_id)
            if seen.reasoning and not seen.text:
                seen.reasoning = False
                yield {"type": "reasoning-end", "id": stream_id}
            if not seen.text:
                seen.text = True
                yield {"type": "text-start", "id": stream_id}
            yield {"type": "text-delta", "id": stream_id, "delta": text}
    elif is_tool_message(message):
        yield from _tool_output_parts(message, state)


def _process_tool_chunks(
    chunk: AIMessageChunk, stream_id: str, state: LangGraphEventState
) -> Iterator[UIMessageChunk]:
    seen = _seen(state, stream_id)
    calls = state.tool_info.setdefault(stream_id, {})
    for raw in chunk.tool_call_chunks:
        raw_index = raw.get("index")
        index = raw_index if isinstance(raw_index, int) else 0
        raw_id = raw.get("id")
        raw_name = raw.get("name")
        stored = calls.get(index)
        if isinstance(raw_id, str) and raw_id:
            stored = (
                raw_id,
                raw_name
                if isinstance(raw_name, str) and raw_name
                else (stored[1] if stored is not None else "unknown"),
            )
            calls[index] = stored
        if stored is None:
            continue

        call_id, name = stored
        if call_id not in seen.tools:
            seen.tools.add(call_id)
            if call_id not in state.emitted_tool_calls:
                state.emitted_tool_calls.add(call_id)
                yield {
                    "type": "tool-input-start",
                    "toolCallId": call_id,
                    "toolName": name,
                    "dynamic": True,
                }

        args = raw.get("args")
        if isinstance(args, str) and args:
            yield {
                "type": "tool-input-delta",
                "toolCallId": call_id,
                "inputTextDelta": args,
            }


def _tool_output_parts(
    message: BaseMessage, state: LangGraphEventState
) -> Iterator[UIMessageChunk]:
    call_id = getattr(message, "tool_call_id", None)
    if not isinstance(call_id, str) or not call_id:
        return
    if call_id in state.emitted_tool_outputs:
        return
    state.emitted_tool_outputs.add(call_id)
    if getattr(message, "status", None) == "error":
        yield {
            "type": "tool-output-error",
            "toolCallId": call_id,
            "errorText": tool_error_text(message.content),
        }
    else:
        yield {
            "type": "tool-output-available",
            "toolCallId": call_id,
            "output": message.content,
        }


def _process_values_event(
    data: Any,
    state: LangGraphEventState,
    history_message_ids: Set[str],
    approval_descriptor: ApprovalDescriptor | None,
) -> Iterator[UIMessageChunk]:
    if not isinstance(data, dict):
        return
    yield from _finalize_seen(state)
    yield from _recover_tool_calls(data, state, history_message_ids)
    yield from _process_interrupts(data, state, approval_descriptor)


def _finalize_seen(state: LangGraphEventState) -> Iterator[UIMessageChunk]:
    for stream_id, seen in list(state.seen.items()):
        if seen.text:
            seen.text = False
            yield {"type": "text-end", "id": stream_id}
        yield from _emit_tool_inputs(stream_id, state)
        if seen.reasoning:
            seen.reasoning = False
            yield {"type": "reasoning-end", "id": stream_id}
        state.seen.pop(stream_id, None)
        state.concat.pop(stream_id, None)


def _emit_tool_inputs(
    stream_id: str, state: LangGraphEventState
) -> Iterator[UIMessageChunk]:
    combined = state.concat.get(stream_id)
    if combined is None:
        return
    for call in combined.tool_calls:
        yield from _tool_input_parts(call, state)


def _tool_input_parts(
    call: ToolCall | dict[str, Any], state: LangGraphEventState
) -> Iterator[UIMessageChunk]:
    call_id = tool_call_id(call)
    if call_id is None or call_id in state.emitted_tool_inputs:
        return
    name = tool_call_name(call)
    args = tool_call_args(call)
    if call_id not in state.emitted_tool_calls:
        state.emitted_tool_calls.add(call_id)
        yield {
            "type": "tool-input-start",
            "toolCallId": call_id,
            "toolName": name,
            "dynamic": True,
        }
    state.emitted_tool_inputs.add(call_id)
    state.emitted_tool_calls_by_key[tool_args_key(name, args)] = call_id
    yield {
        "type": "tool-input-available",
        "toolCallId": call_id,
        "toolName": name,
        "input": args,
        "dynamic": True,
    }


def _recover_tool_calls(
    data: dict[str, Any],
    state: LangGraphEventState,
    history_message_ids: Set[str],
) -> Iterator[UIMessageChunk]:
    messages = data.get("messages")
    if not isinstance(messages, list):
        return
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        if message.id is not None and message.id in history_message_ids:
            continue
        for call in message.tool_calls:
            call_id = tool_call_id(call)
            if call_id is None:
                continue
            key = tool_args_key(tool_call_name(call), tool_call_args(call))
            state.emitted_tool_calls_by_key.setdefault(key, call_id)
            yield from _tool_input_parts(call, state)


def _process_interrupts(
    data: dict[str, Any],
    state: LangGraphEventState,
    approval_descriptor: ApprovalDescriptor | None,
) -> Iterator[UIMessageChunk]:
    raw_interrupts = data.get("__interrupt__")
    if not isinstance(raw_interrupts, (list, tuple)):
        return
    for interrupt in raw_interrupts:
        value = getattr(interrupt, "value", None)
        if not isinstance(value, dict):
            continue
        requests = value.get("action_requests")
        if not isinstance(requests, list):
            continue
        interrupt_id = getattr(interrupt, "id", "interrupt")
        for index, request in enumerate(requests):
            if not isinstance(request, dict):
                continue
            yield from _approval_parts(
                request,
                f"{interrupt_id}-{index}",
                data,
                state,
                approval_descriptor,
            )


def _approval_parts(
    request: dict[str, Any],
    fallback_id: str,
    state_data: dict[str, Any],
    state: LangGraphEventState,
    approval_descriptor: ApprovalDescriptor | None,
) -> Iterator[UIMessageChunk]:
    raw_name = request.get("name")
    name = raw_name if isinstance(raw_name, str) and raw_name else "unknown"
    raw_args = request.get("args") or request.get("arguments")
    args = raw_args if isinstance(raw_args, dict) else {}
    key = tool_args_key(name, args)
    call_id = state.emitted_tool_calls_by_key.get(key) or f"approval-{fallback_id}"
    if call_id in state.emitted_approvals:
        return

    if call_id not in state.emitted_tool_calls:
        state.emitted_tool_calls.add(call_id)
        yield {
            "type": "tool-input-start",
            "toolCallId": call_id,
            "toolName": name,
            "dynamic": True,
        }
    if call_id not in state.emitted_tool_inputs:
        state.emitted_tool_inputs.add(call_id)
        state.emitted_tool_calls_by_key[key] = call_id
        yield {
            "type": "tool-input-available",
            "toolCallId": call_id,
            "toolName": name,
            "input": args,
            "dynamic": True,
        }

    descriptor = (
        approval_descriptor(state_data, request)
        if approval_descriptor is not None
        else {}
    )
    raw_reason = request.get("description")
    reason = (
        raw_reason
        if isinstance(raw_reason, str) and raw_reason
        else "Approval required"
    )
    state.emitted_approvals.add(call_id)
    yield {
        "type": "tool-approval-request",
        "approvalId": call_id,
        "toolCallId": call_id,
        "reason": reason,
        "approvalDescriptor": descriptor,
    }


def _process_custom_event(data: Any) -> Iterator[UIMessageChunk]:
    name = "custom"
    part_id: str | None = None
    if isinstance(data, dict):
        raw_type = data.get("type")
        if isinstance(raw_type, str) and raw_type:
            name = raw_type
        raw_id = data.get("id")
        if isinstance(raw_id, str) and raw_id:
            part_id = raw_id
    part: UIMessageChunk = {"type": f"data-{name}", "data": data}
    if part_id is not None:
        part["id"] = part_id
    else:
        part["transient"] = True
    yield part


def _step_parts(
    state: LangGraphEventState, metadata: dict[str, Any]
) -> Iterator[UIMessageChunk]:
    step = metadata.get("langgraph_step")
    if not isinstance(step, int):
        return
    if not state.step_started:
        state.step_started = True
        state.current_step = step
        yield {"type": "start-step"}
    elif step != state.current_step:
        yield from _close_open(state)
        yield {"type": "finish-step"}
        yield {"type": "start-step"}
        state.current_step = step


def _close_open(state: LangGraphEventState) -> Iterator[UIMessageChunk]:
    for stream_id, seen in state.seen.items():
        if seen.text:
            seen.text = False
            yield {"type": "text-end", "id": stream_id}
        if seen.reasoning:
            seen.reasoning = False
            yield {"type": "reasoning-end", "id": stream_id}


def _seen(state: LangGraphEventState, stream_id: str) -> MessageSeen:
    return state.seen.setdefault(stream_id, MessageSeen())


def _with_namespace(
    part: UIMessageChunk, namespace: tuple[str, ...] | None
) -> UIMessageChunk:
    part_type = str(part.get("type"))
    if namespace is None or not (
        part_type in _NAMESPACED_PARTS or part_type.startswith("data-")
    ):
        return part
    tagged = dict(part)
    tagged["providerMetadata"] = {"langchain": {"namespace": list(namespace)}}
    return tagged
