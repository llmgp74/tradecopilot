"""Contract tests for the chat endpoint and approval resume."""

from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langgraph.types import Command, Interrupt
from tradecopilot_agent import Settings
from tradecopilot_agent.server import create_app


class StubGraph:
    """A graph double that records its input and streams one text chunk."""

    def __init__(self, snapshot: SimpleNamespace | None = None) -> None:
        self.snapshot = snapshot or SimpleNamespace(
            values={"messages": []}, interrupts=()
        )
        self.received: Any = None
        self.calls = 0

    async def aget_state(self, config: Any) -> SimpleNamespace:
        """Return the configured state snapshot."""
        return self.snapshot

    async def astream(
        self, graph_input: Any, config: Any, **kwargs: Any
    ) -> AsyncIterator[tuple[str, Any]]:
        """Record the graph input and stream one text chunk."""
        self.received = graph_input
        self.calls += 1
        yield (
            "messages",
            (AIMessageChunk(content="ok", id="a1"), {"langgraph_step": 1}),
        )


def _client(tmp_path: Path, graph: StubGraph) -> TestClient:
    settings = Settings(db_path=tmp_path / "data.db")
    app = create_app(settings, graph_factory=lambda _app: graph)
    return TestClient(app)


def test_chat_streams_and_passes_only_new_message(tmp_path: Path) -> None:
    """A normal request sends one new human message to the graph."""
    graph = StubGraph()
    with _client(tmp_path, graph) as client:
        response = client.post(
            "/api/chat",
            json={
                "thread_id": "t1",
                "messages": [
                    {
                        "id": "u1",
                        "role": "user",
                        "parts": [{"type": "text", "text": "hi"}],
                    }
                ],
            },
        )

    assert response.status_code == 200
    assert response.headers["x-vercel-ai-ui-message-stream"] == "v1"
    assert "data: [DONE]" in response.text
    assert '"type":"data-thread"' in response.text.replace(" ", "")
    assert isinstance(graph.received, dict)
    message = graph.received["messages"][0]
    assert isinstance(message, HumanMessage)
    assert message.content == "hi"


def test_approval_response_resumes_with_reject(tmp_path: Path) -> None:
    """A tool approval response resumes the graph with a decision."""
    tool_call = {
        "name": "execute_order",
        "args": {"qty": 10},
        "id": "call_1",
        "type": "tool_call",
    }
    snapshot = SimpleNamespace(
        values={"messages": [AIMessage(content="", id="a1", tool_calls=[tool_call])]},
        interrupts=(
            Interrupt(
                id="int-1",
                value={
                    "action_requests": [
                        {
                            "name": "execute_order",
                            "args": {"qty": 10},
                            "description": "Review",
                        }
                    ]
                },
            ),
        ),
    )
    graph = StubGraph(snapshot)
    body = {
        "thread_id": "t1",
        "messages": [
            {
                "id": "u1",
                "role": "user",
                "parts": [{"type": "text", "text": "buy"}],
            },
            {
                "id": "a1",
                "role": "assistant",
                "parts": [
                    {
                        "type": "tool-execute_order",
                        "toolCallId": "call_1",
                        "state": "approval-responded",
                        "input": {"qty": 10},
                        "approval": {
                            "id": "call_1",
                            "approved": False,
                            "reason": "too big",
                        },
                    }
                ],
            },
        ],
    }

    with _client(tmp_path, graph) as client:
        response = client.post("/api/chat", json=body)

    assert response.status_code == 200
    assert isinstance(graph.received, Command)
    assert graph.received.resume == {
        "decisions": [{"type": "reject", "message": "too big"}]
    }


def test_mismatched_approval_returns_error_part(tmp_path: Path) -> None:
    """An approval for a different tool call does not resume the graph."""
    tool_call = {
        "name": "execute_order",
        "args": {"qty": 10},
        "id": "call_1",
        "type": "tool_call",
    }
    snapshot = SimpleNamespace(
        values={"messages": [AIMessage(content="", id="a1", tool_calls=[tool_call])]},
        interrupts=(
            Interrupt(
                id="int-1",
                value={
                    "action_requests": [
                        {
                            "name": "execute_order",
                            "args": {"qty": 10},
                            "description": "Review",
                        }
                    ]
                },
            ),
        ),
    )
    graph = StubGraph(snapshot)
    body = {
        "thread_id": "t1",
        "messages": [
            {
                "id": "a1",
                "role": "assistant",
                "parts": [
                    {
                        "type": "tool-execute_order",
                        "toolCallId": "call_1",
                        "state": "approval-responded",
                        "input": {"qty": 10},
                        "approval": {
                            "id": "call_999",
                            "approved": True,
                        },
                    }
                ],
            }
        ],
    }

    with _client(tmp_path, graph) as client:
        response = client.post("/api/chat", json=body)

    assert response.status_code == 200
    assert '"type":"error"' in response.text.replace(" ", "")
    assert graph.calls == 0
