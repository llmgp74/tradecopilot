"""Helpers for translating LangGraph messages and events."""

import json
from typing import Any

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    ToolMessage,
)
from langchain_core.messages.tool import ToolCall

from tradecopilot_agent.server.ai_sdk.types import GraphEvent

_THINKING_BLOCKS = frozenset({"thinking", "reasoning"})


def parse_langgraph_event(
    event: GraphEvent,
) -> tuple[tuple[str, ...] | None, str, Any]:
    """Split a LangGraph stream event into namespace, mode, and data.

    Args:
        event: A `(mode, data)` tuple, or a `(namespace, mode, data)` tuple
            when streaming subgraphs.

    Returns:
        The namespace path, the stream mode, and the event payload. The
        namespace is `None` when the event has no namespace.
    """
    if len(event) == 3:
        raw_namespace, mode, data = event
        return _namespace(raw_namespace), str(mode), data
    mode, data = event
    return None, str(mode), data


def _namespace(value: Any) -> tuple[str, ...] | None:
    if not isinstance(value, (tuple, list)):
        return None
    return tuple(str(segment) for segment in value)


def message_id(message: BaseMessage, fallback: str) -> str:
    """Return a stable message id for a streamed chunk.

    Args:
        message: The streamed message.
        fallback: Id used when the message has none.

    Returns:
        The message id.
    """
    return message.id or fallback


def message_text(message: BaseMessage) -> str:
    """Extract answer text from a message chunk.

    Args:
        message: The streamed message.

    Returns:
        The text content, without reasoning blocks.
    """
    text = getattr(message, "text", None)
    if isinstance(text, str) and text:
        return text
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(
        block["text"]
        for block in content
        if isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    )


def message_reasoning(message: BaseMessage) -> str:
    """Extract reasoning text from a message chunk.

    Args:
        message: The streamed message.

    Returns:
        The reasoning text, or an empty string when there is none.
    """
    parts: list[str] = []
    raw_blocks: list[Any] = []
    content = message.content
    if isinstance(content, list):
        raw_blocks.extend(content)
    else:
        raw_blocks.extend(message.content_blocks)
    for block in raw_blocks:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type in _THINKING_BLOCKS:
            _append_text(parts, block)
        elif block_type == "non_standard":
            value = block.get("value")
            if isinstance(value, dict) and value.get("type") in _THINKING_BLOCKS:
                _append_text(parts, value)
    if parts:
        return "".join(parts)

    for key in ("reasoning_content", "reasoning"):
        value = message.additional_kwargs.get(key)
        if isinstance(value, str):
            return value
    return ""


def _append_text(parts: list[str], block: dict[Any, Any]) -> None:
    for key in ("thinking", "reasoning", "text"):
        value = block.get(key)
        if isinstance(value, str):
            parts.append(value)
            return


def is_tool_message(message: BaseMessage) -> bool:
    """Return whether the message is a tool result."""
    return isinstance(message, ToolMessage)


def tool_error_text(content: Any) -> str:
    """Render a tool error payload as text.

    Args:
        content: The tool message content.

    Returns:
        A string for the AI SDK error part.
    """
    if isinstance(content, str):
        return content
    return json.dumps(content, default=str)


def tool_args_key(name: str, args: Any) -> str:
    """Build a lookup key from a tool name and its arguments.

    Args:
        name: Tool name.
        args: Tool arguments.

    Returns:
        A stable key for matching interrupts to streamed tool calls.
    """
    return f"{name}:{json.dumps(args, sort_keys=True, default=str)}"


def tool_call_id(
    call: ToolCall | dict[str, Any],
) -> str | None:
    """Return a tool call id when present."""
    value = call.get("id")
    return value if isinstance(value, str) and value else None


def tool_call_name(
    call: ToolCall | dict[str, Any],
) -> str:
    """Return a tool call name, defaulting to `unknown`."""
    value = call.get("name")
    return value if isinstance(value, str) and value else "unknown"


def tool_call_args(
    call: ToolCall | dict[str, Any],
) -> dict[str, Any]:
    """Return tool call arguments as a dictionary."""
    value = call.get("args")
    return value if isinstance(value, dict) else {}


def target_message(
    data: dict[str, Any],
) -> AIMessage | None:
    """Return the last assistant message from a values payload.

    Args:
        data: The values event payload.

    Returns:
        The last `AIMessage`, or `None` when there is none.
    """
    messages = data.get("messages")
    if not isinstance(messages, list):
        return None
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return message
    return None


def is_ai_chunk(message: BaseMessage) -> bool:
    """Return whether the message is a streaming assistant chunk."""
    return isinstance(message, AIMessageChunk)
