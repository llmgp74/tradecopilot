from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from pydantic import BaseModel

from tradecopilot_agent.agent import build_agent
from tradecopilot_agent.config import Settings, get_settings
from tradecopilot_agent.memory import MemoryConfig
from tradecopilot_agent.server.streaming import (
    STREAM_HEADERS,
    sse,
    stream_chat,
)

GraphFactory = Callable[[FastAPI], Any]


class ChatRequest(BaseModel):
    """The AI SDK chat request plus the thread id.

    Attributes:
        thread_id: Existing conversation thread. A thread is created when
            omitted.
        messages: Full UI message history from `useChat`.
        trigger: AI SDK request trigger, kept for wire compatibility.
        messageId: Assistant message id, kept for wire compatibility.
    """

    thread_id: str | None = None
    messages: list[dict[str, Any]]
    trigger: str | None = None
    messageId: str | None = None


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Prepare the database and checkpointer before serving requests.

    Args:
        app: Application whose state holds the settings.

    Yields:
        Control back to the server for the lifetime of the process.
    """
    settings: Settings = app.state.settings
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(settings.db_path)) as saver:
        await saver.conn.execute("PRAGMA journal_mode=WAL")
        await saver.conn.execute("PRAGMA busy_timeout=5000")
        await saver.setup()
        app.state.checkpointer = saver
        yield


def create_app(
    settings: Settings | None = None,
    graph_factory: GraphFactory | None = None,
) -> FastAPI:
    """Create the server application.

    Args:
        settings: Configuration override. Environment settings when omitted.
        graph_factory: Builds the graph on first use. Tests inject a stub;
            production builds the DeepAgents graph.

    Returns:
        The configured application.
    """
    app = FastAPI(title="TradeCopilot", lifespan=_lifespan)
    app.state.settings = settings or get_settings()
    app.state.graph_factory = graph_factory
    app.state.graph = None

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        """Report that the server is running.

        Returns:
            A fixed status payload.
        """
        return {"status": "ok"}

    @app.post("/api/chat")
    async def chat(body: ChatRequest) -> StreamingResponse:
        """Stream one graph turn as an AI SDK UI message stream.

        Args:
            body: AI SDK chat request.

        Returns:
            Server-Sent Events carrying UI message parts.

        Raises:
            HTTPException: When the agent model is not configured.
        """
        try:
            graph = _get_graph(app)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        thread_id = body.thread_id or uuid4().hex
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        parts = stream_chat(
            graph,
            body.messages,
            thread_id,
            config,
            approval_descriptor=_approval_descriptor,
        )
        return StreamingResponse(
            sse(parts),
            media_type="text/event-stream",
            headers=STREAM_HEADERS,
        )

    _mount_ui(app)
    return app


def _get_graph(app: FastAPI) -> Any:
    """Return the shared graph, building it on first use.

    Args:
        app: Application holding the factory and checkpointer.

    Returns:
        The compiled graph.
    """
    graph = app.state.graph
    if graph is not None:
        return graph
    factory: GraphFactory = app.state.graph_factory or _default_graph
    graph = factory(app)
    app.state.graph = graph
    return graph


def _default_graph(app: FastAPI) -> Any:
    """Build the DeepAgents graph with the application checkpointer.

    Args:
        app: Application holding the settings and checkpointer.

    Returns:
        The compiled graph.

    Raises:
        RuntimeError: If `AGENT_MODEL` is not configured.
    """
    config = MemoryConfig(condition="full", store=_UnusedStore())
    return build_agent(
        config,
        _UnusedSource(),
        checkpointer=app.state.checkpointer,
    )


def _approval_descriptor(
    state: dict[str, Any], request: dict[str, Any]
) -> dict[str, Any]:
    """Build the payload rendered by the approval card.

    Args:
        state: Graph state at the interrupt.
        request: Interrupt action request.

    Returns:
        The ticket and the available decision context.
    """
    raw_args = request.get("args")
    ticket = raw_args if isinstance(raw_args, dict) else {}
    return {
        "ticket": ticket,
        "rationale": state.get("draft_recommendation"),
        "verification": state.get("verification"),
        "portfolio_impact": state.get("portfolio_impact"),
    }


class _UnusedStore:
    """Stand-in until the SQLite memory store is implemented."""


class _UnusedSource:
    """Stand-in until the live data source is implemented."""


def _mount_ui(app: FastAPI) -> None:
    """Serve the built frontend when it is present.

    Args:
        app: Application to mount the frontend on.
    """
    ui_dist: Path = app.state.settings.ui_dist
    if ui_dist.is_dir():
        app.mount("/", StaticFiles(directory=ui_dist, html=True), name="ui")
        return

    @app.get("/", response_class=HTMLResponse)
    async def missing_ui() -> str:
        """Explain how to produce the missing frontend build.

        Returns:
            A short HTML hint.
        """
        return (
            "<p>UI build not found. Build the frontend under "
            "<code>ui/</code> first.</p>"
        )
