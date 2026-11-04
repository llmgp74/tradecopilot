"""Wire message types and mutable state for the stream adapter."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessageChunk

type UIMessage = dict[str, Any]
type UIMessageChunk = dict[str, Any]
type UIPart = dict[str, Any]
type GraphEvent = tuple[str, Any]
type ApprovalDescriptor = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


@dataclass
class MessageSeen:
    """Tracks which parts of a streamed message have been opened."""

    text: bool = False
    reasoning: bool = False
    tools: set[str] = field(default_factory=set)


@dataclass
class LangGraphEventState:
    """Mutable state carried across one graph stream.

    Attributes:
        seen: Open text, reasoning, and tool parts by message id.
        concat: Accumulated chunks by message id, used to recover tool calls
            from the final `values` event.
        tool_info: Tool id and name by message id and chunk index. Later
            chunks carry arguments without repeating the id.
        emitted_tool_calls: Tool ids whose input lifecycle has started.
        emitted_tool_inputs: Tool ids whose full input has been emitted.
        emitted_tool_outputs: Tool ids whose result has been emitted.
        emitted_approvals: Tool ids whose approval request has been emitted.
        emitted_tool_calls_by_key: Tool call ids by tool name and arguments,
            used to match an interrupt to the streamed call.
        current_step: Current LangGraph step, from message metadata.
        step_started: Whether a `start-step` part has been emitted.
    """

    seen: dict[str, MessageSeen] = field(default_factory=dict)
    concat: dict[str, AIMessageChunk] = field(default_factory=dict)
    tool_info: dict[str, dict[int, tuple[str, str]]] = field(default_factory=dict)
    emitted_tool_calls: set[str] = field(default_factory=set)
    emitted_tool_inputs: set[str] = field(default_factory=set)
    emitted_tool_outputs: set[str] = field(default_factory=set)
    emitted_approvals: set[str] = field(default_factory=set)
    emitted_tool_calls_by_key: dict[str, str] = field(default_factory=dict)
    current_step: int | None = None
    step_started: bool = False
