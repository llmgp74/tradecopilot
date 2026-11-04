"""Contract tests for the AI SDK UI message stream adapter."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langgraph.types import Interrupt
from tradecopilot_agent.server.ai_sdk.adapter import to_ui_message_stream
from tradecopilot_agent.server.ai_sdk.convert import (
    to_human_message,
    to_langchain_messages,
)

Event = tuple[str, Any]


async def _events(items: list[Event]) -> AsyncIterator[Event]:
    for item in items:
        yield item


def _parts(items: list[Event], **kwargs: Any) -> list[dict[str, Any]]:
    async def collect() -> list[dict[str, Any]]:
        return [
            part
            async for part in to_ui_message_stream(
                _events(items), message_id="assistant-1", **kwargs
            )
        ]

    return asyncio.run(collect())


def test_text_round_trip() -> None:
    """Text deltas become one text part bounded by step parts."""
    parts = _parts(
        [
            (
                "messages",
                (AIMessageChunk(content="Hel", id="m1"), {"langgraph_step": 1}),
            ),
            (
                "messages",
                (AIMessageChunk(content="lo", id="m1"), {"langgraph_step": 1}),
            ),
            ("values", {"messages": [AIMessage(content="Hello", id="m1")]}),
        ]
    )

    assert [part["type"] for part in parts] == [
        "start",
        "start-step",
        "text-start",
        "text-delta",
        "text-delta",
        "text-end",
        "finish-step",
        "finish",
    ]
    assert parts[3]["delta"] == "Hel"


def test_reasoning_closes_before_text() -> None:
    """Reasoning deltas are closed when the answer text starts."""
    parts = _parts(
        [
            (
                "messages",
                (
                    AIMessageChunk(
                        content=[{"type": "thinking", "thinking": "plan"}],
                        id="m1",
                    ),
                    {"langgraph_step": 1},
                ),
            ),
            (
                "messages",
                (AIMessageChunk(content="Answer", id="m1"), {"langgraph_step": 1}),
            ),
            ("values", {"messages": [AIMessage(content="Answer", id="m1")]}),
        ]
    )

    assert [part["type"] for part in parts[:8]] == [
        "start",
        "start-step",
        "reasoning-start",
        "reasoning-delta",
        "reasoning-end",
        "text-start",
        "text-delta",
        "text-end",
    ]
    assert parts[3]["delta"] == "plan"


def test_tool_call_and_result() -> None:
    """A streamed tool call becomes start, delta, available, and output parts."""
    start_chunk = AIMessageChunk(
        content="",
        id="m1",
        tool_call_chunks=[
            {
                "name": "get_quote",
                "args": "",
                "id": "call_1",
                "index": 0,
                "type": "tool_call_chunk",
            }
        ],
    )
    args_chunk = AIMessageChunk(
        content="",
        id="m1",
        tool_call_chunks=[
            {
                "name": None,
                "args": '{"ticker":"AAPL"}',
                "id": None,
                "index": 0,
                "type": "tool_call_chunk",
            }
        ],
    )
    final = AIMessage(
        content="",
        id="m1",
        tool_calls=[
            {
                "name": "get_quote",
                "args": {"ticker": "AAPL"},
                "id": "call_1",
                "type": "tool_call",
            }
        ],
    )

    parts = _parts(
        [
            ("messages", (start_chunk, {"langgraph_step": 1})),
            ("messages", (args_chunk, {"langgraph_step": 1})),
            ("values", {"messages": [final]}),
            (
                "messages",
                (
                    ToolMessage(
                        content="price 101", tool_call_id="call_1", name="get_quote"
                    ),
                    {"langgraph_step": 2},
                ),
            ),
        ]
    )

    types = [part["type"] for part in parts]
    assert types.count("tool-input-start") == 1
    assert types.count("tool-input-delta") == 1
    assert types.count("tool-input-available") == 1
    assert types.count("finish-step") == 2
    assert "tool-output-available" in types
    available = next(part for part in parts if part["type"] == "tool-input-available")
    assert available["input"] == {"ticker": "AAPL"}


def test_custom_data_part_keeps_id() -> None:
    """A custom payload with an id becomes a persistent data part."""
    parts = _parts([("custom", {"type": "todos", "id": "todos-1", "todos": ["check"]})])

    part = next(part for part in parts if part["type"] == "data-todos")
    assert part["id"] == "todos-1"
    assert part["data"]["todos"] == ["check"]
    assert "transient" not in part


def test_interrupt_emits_approval_request() -> None:
    """An interrupt becomes a tool approval request matched to the tool call."""
    start_chunk = AIMessageChunk(
        content="",
        id="m1",
        tool_call_chunks=[
            {
                "name": "execute_order",
                "args": "",
                "id": "call_1",
                "index": 0,
                "type": "tool_call_chunk",
            }
        ],
    )
    args_chunk = AIMessageChunk(
        content="",
        id="m1",
        tool_call_chunks=[
            {
                "name": None,
                "args": '{"qty":10}',
                "id": None,
                "index": 0,
                "type": "tool_call_chunk",
            }
        ],
    )
    final = AIMessage(
        content="",
        id="m1",
        tool_calls=[
            {
                "name": "execute_order",
                "args": {"qty": 10},
                "id": "call_1",
                "type": "tool_call",
            }
        ],
    )
    interrupt = Interrupt(
        id="int-1",
        value={
            "action_requests": [
                {
                    "name": "execute_order",
                    "args": {"qty": 10},
                    "description": "Review the ticket",
                }
            ]
        },
    )
    seen: list[tuple[dict[str, Any], dict[str, Any]]] = []

    def descriptor(state: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
        seen.append((state, request))
        return {"ticket": request["args"]}

    parts = _parts(
        [
            ("messages", (start_chunk, {"langgraph_step": 1})),
            ("messages", (args_chunk, {"langgraph_step": 1})),
            ("values", {"messages": [final]}),
            ("values", {"messages": [final], "__interrupt__": (interrupt,)}),
        ],
        approval_descriptor=descriptor,
    )

    approval = next(part for part in parts if part["type"] == "tool-approval-request")
    assert approval["approvalId"] == "call_1"
    assert approval["toolCallId"] == "call_1"
    assert approval["reason"] == "Review the ticket"
    assert approval["approvalDescriptor"] == {"ticket": {"qty": 10}}
    assert seen


def test_to_human_message_uses_ui_id() -> None:
    """A UI user message keeps its id and text."""
    message = to_human_message(
        {
            "id": "u1",
            "role": "user",
            "parts": [{"type": "text", "text": "hello"}],
        }
    )

    assert isinstance(message, HumanMessage)
    assert message.id == "u1"
    assert message.content == "hello"


def test_to_langchain_messages_rebuilds_tool_history() -> None:
    """Assistant tool parts become an AI message and a tool message."""
    messages = to_langchain_messages(
        [
            {
                "id": "u1",
                "role": "user",
                "parts": [{"type": "text", "text": "quote"}],
            },
            {
                "id": "a1",
                "role": "assistant",
                "parts": [
                    {"type": "text", "text": "checking"},
                    {
                        "type": "tool-get_quote",
                        "toolCallId": "call_1",
                        "state": "output-available",
                        "input": {"ticker": "AAPL"},
                        "output": {"price": 101},
                    },
                ],
            },
        ]
    )

    assert isinstance(messages[0], HumanMessage)
    assert isinstance(messages[1], AIMessage)
    assert messages[1].tool_calls[0]["id"] == "call_1"
    assert isinstance(messages[2], ToolMessage)
    assert messages[2].tool_call_id == "call_1"


def test_resume_reemits_unfinished_tool_call() -> None:
    """A resumed run re-emits the unanswered tool call before its result."""
    parts = _parts(
        [],
        unfinished_tool_calls=[
            {
                "name": "execute_order",
                "args": {"qty": 10},
                "id": "call_1",
                "type": "tool_call",
            }
        ],
    )

    assert [part["type"] for part in parts] == [
        "start",
        "tool-input-start",
        "tool-input-available",
        "finish",
    ]


def test_values_recovery_skips_history() -> None:
    """A resumed run does not re-emit tool calls from checkpointed history."""
    final = AIMessage(
        content="",
        id="m1",
        tool_calls=[
            {
                "name": "execute_order",
                "args": {"qty": 10},
                "id": "call_1",
                "type": "tool_call",
            }
        ],
    )

    parts = _parts(
        [("values", {"messages": [final]})],
        history_message_ids={"m1"},
    )

    assert not any(part["type"] == "tool-input-available" for part in parts)
