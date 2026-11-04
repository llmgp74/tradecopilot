"""Convert between AI SDK UI messages and LangChain messages."""

import json
from collections.abc import Sequence
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from tradecopilot_agent.server.ai_sdk.types import ApprovalDescriptor, UIMessage, UIPart
from tradecopilot_agent.server.ai_sdk.utils import (
    message_reasoning,
    message_text,
    tool_args_key,
    tool_call_args,
    tool_call_id,
    tool_call_name,
    tool_error_text,
)

_TOOL_PREFIX = "tool-"


def to_human_message(message: UIMessage) -> HumanMessage:
    """Convert one UI user message to a human message.

    Args:
        message: An AI SDK UI message with role `user`.

    Returns:
        A `HumanMessage` with the user's text and the UI message id.
    """
    parts = message.get("parts")
    text = _text_from_parts(parts if isinstance(parts, list) else [])
    raw_id = message.get("id")
    return HumanMessage(
        content=text,
        id=raw_id if isinstance(raw_id, str) else None,
    )


def to_langchain_messages(
    messages: list[UIMessage],
) -> list[BaseMessage]:
    """Convert a full UI message history to LangChain messages.

    Assistant tool parts become an `AIMessage` with tool calls followed by
    `ToolMessage` results. Reasoning, data, and approval parts are not part
    of the model conversation and are skipped.

    Args:
        messages: AI SDK UI messages.

    Returns:
        LangChain messages in conversation order.
    """
    converted: list[BaseMessage] = []
    for message in messages:
        role = message.get("role")
        parts = message.get("parts")
        if not isinstance(parts, list):
            parts = []
        if role == "user":
            converted.append(to_human_message(message))
        elif role == "system":
            converted.append(SystemMessage(content=_text_from_parts(parts)))
        elif role == "assistant":
            converted.extend(_assistant_messages(message, parts))
    return converted


def _assistant_messages(message: UIMessage, parts: list[UIPart]) -> list[BaseMessage]:
    text = _text_from_parts(parts)
    tool_calls: list[dict[str, Any]] = []
    tool_results: list[ToolMessage] = []

    for part in parts:
        part_type = part.get("type")
        if not isinstance(part_type, str) or not part_type.startswith(_TOOL_PREFIX):
            continue
        call_id = part.get("toolCallId")
        if not isinstance(call_id, str) or not call_id:
            continue
        state = part.get("state")
        tool_calls.append(
            {
                "id": call_id,
                "name": _tool_name(part, part_type),
                "args": part.get("input")
                if isinstance(part.get("input"), dict)
                else {},
                "type": "tool_call",
            }
        )
        if state == "output-available":
            tool_results.append(
                ToolMessage(
                    content=_tool_output(part.get("output")),
                    tool_call_id=call_id,
                    name=_tool_name(part, part_type),
                    id=f"{call_id}-result",
                )
            )
        elif state == "output-error":
            error = part.get("errorText")
            tool_results.append(
                ToolMessage(
                    content=error
                    if isinstance(error, str)
                    else "Tool execution failed",
                    tool_call_id=call_id,
                    name=_tool_name(part, part_type),
                    status="error",
                    id=f"{call_id}-result",
                )
            )

    raw_id = message.get("id")
    assistant = AIMessage(
        content=text,
        tool_calls=tool_calls,
        id=raw_id if isinstance(raw_id, str) else None,
    )
    return [assistant, *tool_results]


def _text_from_parts(parts: list[UIPart]) -> str:
    texts = [
        part["text"]
        for part in parts
        if part.get("type") == "text" and isinstance(part.get("text"), str)
    ]
    return "\n".join(texts)


def _tool_name(part: UIPart, part_type: str) -> str:
    name = part.get("toolName")
    if isinstance(name, str) and name:
        return name
    return part_type.removeprefix(_TOOL_PREFIX)


def _tool_output(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str)


def to_ui_messages(
    values: dict[str, Any],
    interrupts: Sequence[Any] = (),
    approval_descriptor: ApprovalDescriptor | None = None,
) -> list[UIMessage]:
    """Convert checkpointed graph state to AI SDK UI messages.

    Tool results are attached to their call, pending interrupts become
    ``approval-requested`` parts, and the verification and todo channels become
    data parts on the last assistant message.

    Args:
        values: Graph state, holding the ``messages`` channel.
        interrupts: Pending interrupts from the state snapshot.
        approval_descriptor: Builds the approval payload from state and an
            action request.

    Returns:
        UI messages in conversation order.
    """
    raw_messages = values.get("messages")
    messages: list[BaseMessage] = (
        [message for message in raw_messages if isinstance(message, BaseMessage)]
        if isinstance(raw_messages, list)
        else []
    )
    outputs = {
        message.tool_call_id: message
        for message in messages
        if isinstance(message, ToolMessage) and message.tool_call_id
    }

    ui_messages: list[UIMessage] = []
    parts_by_key: dict[str, dict[str, Any]] = {}
    for index, message in enumerate(messages):
        if isinstance(message, ToolMessage):
            continue
        message_id = message.id or f"msg-{index}"
        if isinstance(message, HumanMessage):
            ui_messages.append(_user_message(message_id, message))
        elif isinstance(message, SystemMessage):
            ui_messages.append(_system_message(message_id, message))
        elif isinstance(message, AIMessage):
            parts = _assistant_parts(message, outputs, parts_by_key)
            ui_messages.append({"id": message_id, "role": "assistant", "parts": parts})

    for interrupt in interrupts:
        value = getattr(interrupt, "value", None)
        if not isinstance(value, dict):
            continue
        requests = value.get("action_requests")
        if not isinstance(requests, list):
            continue
        interrupt_id = getattr(interrupt, "id", "interrupt")
        for request_index, request in enumerate(requests):
            if not isinstance(request, dict):
                continue
            _apply_approval(
                request,
                f"approval-{interrupt_id}-{request_index}",
                values,
                ui_messages,
                parts_by_key,
                approval_descriptor,
            )

    _append_data_part(ui_messages, "verification", values.get("verification"), "claims")
    _append_data_part(ui_messages, "todos", values.get("todos"), "todos")
    return ui_messages


def _user_message(message_id: str, message: BaseMessage) -> UIMessage:
    return {
        "id": message_id,
        "role": "user",
        "parts": [{"type": "text", "text": message_text(message)}],
    }


def _system_message(message_id: str, message: BaseMessage) -> UIMessage:
    return {
        "id": message_id,
        "role": "system",
        "parts": [{"type": "text", "text": message_text(message)}],
    }


def _assistant_parts(
    message: AIMessage,
    outputs: dict[str, ToolMessage],
    parts_by_key: dict[str, dict[str, Any]],
) -> list[UIPart]:
    parts: list[UIPart] = []
    reasoning = message_reasoning(message)
    if reasoning:
        parts.append({"type": "reasoning", "text": reasoning})
    text = message_text(message)
    if text:
        parts.append({"type": "text", "text": text})
    for call in message.tool_calls:
        call_id = tool_call_id(call)
        if call_id is None:
            continue
        name = tool_call_name(call)
        args = tool_call_args(call)
        part: dict[str, Any] = {
            "type": f"{_TOOL_PREFIX}{name}",
            "toolCallId": call_id,
            "state": "input-available",
            "input": args,
        }
        output = outputs.get(call_id)
        if output is not None:
            if getattr(output, "status", None) == "error":
                part["state"] = "output-error"
                part["errorText"] = tool_error_text(output.content)
            else:
                part["state"] = "output-available"
                part["output"] = output.content
        parts.append(part)
        parts_by_key[tool_args_key(name, args)] = part
    return parts


def _apply_approval(
    request: dict[str, Any],
    fallback_id: str,
    values: dict[str, Any],
    ui_messages: list[UIMessage],
    parts_by_key: dict[str, dict[str, Any]],
    approval_descriptor: ApprovalDescriptor | None,
) -> None:
    raw_name = request.get("name")
    name = raw_name if isinstance(raw_name, str) and raw_name else "unknown"
    raw_args = request.get("args") or request.get("arguments")
    args = raw_args if isinstance(raw_args, dict) else {}
    key = tool_args_key(name, args)
    part = parts_by_key.get(key)
    if part is None:
        call_id = fallback_id
        part = {
            "type": f"{_TOOL_PREFIX}{name}",
            "toolCallId": call_id,
            "input": args,
        }
        _last_assistant_parts(ui_messages).append(part)
    call_id = str(part["toolCallId"])
    descriptor = (
        approval_descriptor(values, request) if approval_descriptor is not None else {}
    )
    part["state"] = "approval-requested"
    part["approval"] = {"id": call_id, **descriptor}
    parts_by_key[key] = part


def _append_data_part(
    ui_messages: list[UIMessage],
    name: str,
    payload: Any,
    key: str,
) -> None:
    if not isinstance(payload, list) or not payload:
        return
    for message in reversed(ui_messages):
        if message.get("role") != "assistant":
            continue
        parts = message.get("parts")
        if isinstance(parts, list):
            parts.append({"type": f"data-{name}", "data": {"type": name, key: payload}})
        return


def _last_assistant_parts(ui_messages: list[UIMessage]) -> list[UIPart]:
    for message in reversed(ui_messages):
        if message.get("role") == "assistant":
            parts = message.get("parts")
            if isinstance(parts, list):
                return parts
    parts = []
    ui_messages.append({"id": "msg-approval", "role": "assistant", "parts": parts})
    return parts
