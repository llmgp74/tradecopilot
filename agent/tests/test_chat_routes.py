"""Contract tests for the chat endpoint and approval resume."""

import base64
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
        self.inputs: list[Any] = []
        self.calls = 0

    async def aget_state(self, config: Any) -> SimpleNamespace:
        """Return the configured state snapshot."""
        return self.snapshot

    async def astream(
        self, graph_input: Any, config: Any, **kwargs: Any
    ) -> AsyncIterator[tuple[str, Any]]:
        """Record the graph input and stream one text chunk."""
        self.received = graph_input
        self.inputs.append(graph_input)
        self.calls += 1
        yield (
            "messages",
            (AIMessageChunk(content="ok", id="a1"), {"langgraph_step": 1}),
        )


def _client(tmp_path: Path, graph: StubGraph) -> TestClient:
    settings = Settings(
        db_path=tmp_path / "data.db",
        workspace_path=tmp_path / "workspace",
    )
    app = create_app(settings, graph_factory=lambda _app, _reasoning: graph)
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


def test_two_pending_interrupts_resume_by_id(tmp_path: Path) -> None:
    """LangGraph routes a multi-interrupt resume by interrupt id."""
    calls = [
        {"name": "execute_ticket", "args": {"ticket_id": "t_1"}, "id": "call_1"},
        {"name": "execute_ticket", "args": {"ticket_id": "t_2"}, "id": "call_2"},
    ]
    snapshot = SimpleNamespace(
        values={"messages": [AIMessage(content="", id="a1", tool_calls=calls)]},
        interrupts=(
            Interrupt(
                id="int-1",
                value={
                    "action_requests": [
                        {
                            "name": "execute_ticket",
                            "args": {"ticket_id": "t_1"},
                            "description": "Review",
                        }
                    ]
                },
            ),
            Interrupt(
                id="int-2",
                value={
                    "action_requests": [
                        {
                            "name": "execute_ticket",
                            "args": {"ticket_id": "t_2"},
                            "description": "Review",
                        }
                    ]
                },
            ),
        ),
    )
    graph = StubGraph(snapshot)
    approval = {
        "type": "tool-execute_ticket",
        "state": "approval-responded",
    }
    body = {
        "thread_id": "t1",
        "messages": [
            {
                "id": "a1",
                "role": "assistant",
                "parts": [
                    {
                        **approval,
                        "toolCallId": "call_1",
                        "input": {"ticket_id": "t_1"},
                        "approval": {"id": "call_1", "approved": True},
                    },
                    {
                        **approval,
                        "toolCallId": "call_2",
                        "input": {"ticket_id": "t_2"},
                        "approval": {
                            "id": "call_2",
                            "approved": False,
                            "reason": "not now",
                        },
                    },
                ],
            }
        ],
    }

    with _client(tmp_path, graph) as client:
        response = client.post("/api/chat", json=body)

    assert response.status_code == 200
    assert isinstance(graph.received, Command)
    assert graph.received.resume == {
        "int-1": {"decisions": [{"type": "approve"}]},
        "int-2": {"decisions": [{"type": "reject", "message": "not now"}]},
    }


def test_a_new_message_auto_rejects_the_pending_ticket(tmp_path: Path) -> None:
    """Sending a new message instead of deciding rejects the pending ticket."""
    tool_call = {
        "name": "execute_ticket",
        "args": {"ticket_id": "t_1"},
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
                            "name": "execute_ticket",
                            "args": {"ticket_id": "t_1"},
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
                "id": "u2",
                "role": "user",
                "parts": [{"type": "text", "text": "never mind"}],
            }
        ],
    }

    with _client(tmp_path, graph) as client:
        response = client.post("/api/chat", json=body)

    assert response.status_code == 200
    assert graph.calls == 2
    first, second = graph.inputs
    assert isinstance(first, Command)
    assert first.resume == {
        "decisions": [{"type": "reject", "message": "Superseded by a new message."}]
    }
    assert isinstance(second, dict)
    assert second["messages"][0].content == "never mind"


class FailingStateGraph(StubGraph):
    """A graph double whose state read raises a library error."""

    async def aget_state(self, config: Any) -> SimpleNamespace:
        raise RuntimeError(
            "When there are multiple pending interrupts, you must specify the "
            "interrupt id when resuming."
        )


def test_internal_errors_are_hidden_from_the_ui(tmp_path: Path, caplog: Any) -> None:
    """A graph failure shows a general message and logs the details."""
    graph = FailingStateGraph()
    body = {
        "thread_id": "t1",
        "messages": [
            {
                "id": "u1",
                "role": "user",
                "parts": [{"type": "text", "text": "hi"}],
            }
        ],
    }

    with _client(tmp_path, graph) as client:
        response = client.post("/api/chat", json=body)

    assert response.status_code == 200
    assert "unexpected error" in response.text
    assert "multiple pending interrupts" not in response.text
    assert "multiple pending interrupts" in caplog.text


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


def test_approval_resumes_when_the_args_gained_a_purpose(tmp_path: Path) -> None:
    """The call id, not the argument shape, matches the response."""
    tool_call = {
        "name": "execute_ticket",
        "args": {"ticket_id": "t1", "purpose": "Place the ticket"},
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
                            "name": "execute_ticket",
                            "args": {"ticket_id": "t1"},
                            "description": "Review",
                            "tool_call_id": "call_1",
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
            {"id": "u1", "role": "user", "parts": [{"type": "text", "text": "buy"}]},
            {
                "id": "a1",
                "role": "assistant",
                "parts": [
                    {
                        "type": "tool-execute_ticket",
                        "toolCallId": "call_1",
                        "state": "approval-responded",
                        "input": {"ticket_id": "t1"},
                        "approval": {"id": "call_1", "approved": True},
                    }
                ],
            },
        ],
    }

    with _client(tmp_path, graph) as client:
        response = client.post("/api/chat", json=body)

    assert response.status_code == 200
    assert isinstance(graph.received, Command)
    assert graph.received.resume == {"decisions": [{"type": "approve"}]}


def test_settings_change_clears_cached_graphs(tmp_path: Path) -> None:
    """A permission change rebuilds the graph on the next turn."""
    graph = StubGraph()
    with _client(tmp_path, graph) as client:
        client.app.state.graphs["x"] = object()
        response = client.patch(
            "/api/settings",
            json={"tool_permissions": {"execute": "auto"}},
        )

    assert response.status_code == 200
    assert client.app.state.graphs == {}


def test_non_ticket_interrupt_has_no_ticket_error() -> None:
    """The in-row approval does not use the ticket descriptor."""
    from tradecopilot_agent.server.app import _approval_descriptor

    assert (
        _approval_descriptor({}, {"name": "execute", "args": {"command": "ls"}}) == {}
    )


def test_chat_copies_attachments_into_the_workspace(tmp_path: Path) -> None:
    """A file part is stored under the thread and named in the message."""
    graph = StubGraph()
    payload = base64.b64encode(b"a,b\n1,2\n").decode()
    with _client(tmp_path, graph) as client:
        response = client.post(
            "/api/chat",
            json={
                "thread_id": "t1",
                "messages": [
                    {
                        "id": "u1",
                        "role": "user",
                        "parts": [
                            {"type": "text", "text": "Analyze this"},
                            {
                                "type": "file",
                                "filename": "pnl.csv",
                                "mediaType": "text/csv",
                                "url": f"data:text/csv;base64,{payload}",
                            },
                        ],
                    }
                ],
            },
        )

    assert response.status_code == 200
    copies = list((tmp_path / "workspace" / "uploads" / "t1").glob("*-pnl.csv"))
    assert len(copies) == 1
    message = graph.received["messages"][0]
    assert isinstance(message, HumanMessage)
    assert "Attached file: /uploads/t1/" in message.content


def test_chat_rejects_a_traversal_thread_id(tmp_path: Path) -> None:
    """The thread id becomes a directory name, so it is validated."""
    graph = StubGraph()
    with _client(tmp_path, graph) as client:
        response = client.post(
            "/api/chat",
            json={
                "thread_id": "../escape",
                "messages": [
                    {
                        "id": "u1",
                        "role": "user",
                        "parts": [{"type": "text", "text": "hi"}],
                    }
                ],
            },
        )

    assert response.status_code == 422
    assert graph.received is None
