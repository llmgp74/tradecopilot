"""Convert AI SDK UI messages to LangChain messages."""

import json
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from tradecopilot_agent.server.ai_sdk.types import UIMessage, UIPart

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
