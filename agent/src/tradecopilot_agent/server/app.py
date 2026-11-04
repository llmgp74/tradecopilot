"""FastAPI application exposing the HTTP API."""

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from pydantic import BaseModel

from tradecopilot_agent import __version__
from tradecopilot_agent.agent import build_agent
from tradecopilot_agent.config import Settings, get_settings
from tradecopilot_agent.memory import MemoryConfig
from tradecopilot_agent.models import (
    Health,
    JournalEntry,
    JournalList,
    JournalStatus,
    Portfolio,
    PortfolioRange,
    Profile,
    ProfilePatch,
    ThreadDetail,
    ThreadList,
    ThreadSummary,
)
from tradecopilot_agent.portfolio import PortfolioUnavailable, fetch_portfolio
from tradecopilot_agent.server.ai_sdk.convert import to_ui_messages
from tradecopilot_agent.server.streaming import (
    STREAM_HEADERS,
    sse,
    stream_chat,
)
from tradecopilot_agent.store import Store, ThreadRecord

GraphFactory = Callable[[FastAPI], Any]
PortfolioFetcher = Callable[[Settings, str], Awaitable[Portfolio]]


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
    app.state.store = Store(settings.db_path)
    async with AsyncSqliteSaver.from_conn_string(str(settings.db_path)) as saver:
        await saver.conn.execute("PRAGMA journal_mode=WAL")
        await saver.conn.execute("PRAGMA busy_timeout=5000")
        await saver.setup()
        app.state.checkpointer = saver
        yield


def create_app(
    settings: Settings | None = None,
    graph_factory: GraphFactory | None = None,
    portfolio_fetcher: PortfolioFetcher | None = None,
) -> FastAPI:
    """Create the server application.

    Args:
        settings: Configuration override. Environment settings when omitted.
        graph_factory: Builds the graph on first use. Tests inject a stub;
            production builds the DeepAgents graph.
        portfolio_fetcher: Loads the portfolio. Tests inject a stub;
            production calls the broker.

    Returns:
        The configured application.
    """
    app = FastAPI(
        title="TradeCopilot API",
        version=__version__,
        description="Single-user local trading co-pilot.",
        lifespan=_lifespan,
    )
    app.state.settings = settings or get_settings()
    app.state.graph_factory = graph_factory
    app.state.portfolio_fetcher = portfolio_fetcher or fetch_portfolio
    app.state.graph = None

    @app.get("/api/health", response_model=Health)
    async def health() -> Health:
        """Report that the server is running and which model it uses.

        Returns:
            The readiness payload.
        """
        return Health(
            status="ok",
            agent_model=app.state.settings.agent_model or "",
        )

    @app.post(
        "/api/chat",
        summary="Stream one agent turn",
        response_class=StreamingResponse,
        responses={
            200: {
                "description": (
                    "AI SDK UI message stream. One JSON part per frame, "
                    "terminated by data: [DONE]."
                ),
                "content": {"text/event-stream": {"schema": {"type": "string"}}},
            }
        },
    )
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
        app.state.store.upsert_thread(thread_id, _thread_title(body.messages))
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

    @app.get("/api/threads", response_model=ThreadList)
    async def list_threads(
        page_no: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> ThreadList:
        """List conversation threads, newest first.

        Args:
            page_no: One-based page number.
            page_size: Rows per page.

        Returns:
            One page of thread metadata.
        """
        records, total = app.state.store.list_threads(page_no, page_size)
        return ThreadList(
            items=[_thread_summary(record) for record in records],
            page_no=page_no,
            page_size=page_size,
            total=total,
        )

    @app.get("/api/threads/{thread_id}", response_model=ThreadDetail)
    async def get_thread(thread_id: str) -> ThreadDetail:
        """Return one thread with its rehydrated messages.

        Args:
            thread_id: Conversation thread id.

        Returns:
            Thread metadata and AI SDK UI messages.

        Raises:
            HTTPException: 404 when the thread does not exist, or 503 when
                the agent model is not configured.
        """
        record = app.state.store.get_thread(thread_id)
        if record is None:
            raise HTTPException(status_code=404, detail="thread not found")
        try:
            graph = _get_graph(app)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        snapshot = await graph.aget_state(config)
        values = getattr(snapshot, "values", None)
        if not isinstance(values, dict) or not values.get("messages"):
            raise HTTPException(status_code=404, detail="thread not found")
        messages = to_ui_messages(
            values,
            getattr(snapshot, "interrupts", ()) or (),
            _approval_descriptor,
        )
        return ThreadDetail(
            thread_id=record.thread_id,
            title=record.title,
            created_at=record.created_at,
            updated_at=record.updated_at,
            messages=messages,
        )

    @app.get("/api/portfolio", response_model=Portfolio)
    async def get_portfolio(
        range_: Annotated[PortfolioRange, Query(alias="range")] = "1M",
    ) -> Portfolio:
        """Return the current account, positions, and equity history.

        Args:
            range_: Equity curve window.

        Returns:
            The normalized portfolio.

        Raises:
            HTTPException: 503 when the broker is unavailable.
        """
        fetcher: PortfolioFetcher = app.state.portfolio_fetcher
        try:
            return await fetcher(app.state.settings, range_)
        except PortfolioUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/profile", response_model=Profile)
    async def get_profile() -> Profile:
        """Return the user profile.

        Returns:
            The full profile.
        """
        return Profile.model_validate(app.state.store.get_profile())

    @app.patch("/api/profile", response_model=Profile)
    async def patch_profile(body: ProfilePatch) -> Profile:
        """Apply a partial profile update.

        Args:
            body: Fields to change. Omitted fields are untouched.

        Returns:
            The full profile after the update.
        """
        changes = {
            key: value
            for key, value in body.model_dump(exclude_unset=True).items()
            if value is not None
        }
        return Profile.model_validate(app.state.store.patch_profile(changes))

    @app.get("/api/journal", response_model=JournalList)
    async def list_journal(
        page_no: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=200)] = 50,
        status: JournalStatus | None = None,
        ticker: str | None = None,
        from_date: Annotated[date | None, Query(alias="from")] = None,
        to_date: Annotated[date | None, Query(alias="to")] = None,
    ) -> JournalList:
        """List decision journal entries, newest first.

        Args:
            page_no: One-based page number.
            page_size: Rows per page.
            status: Exact status filter.
            ticker: Case-insensitive ticker filter.
            from_date: Inclusive lower bound on the creation date.
            to_date: Inclusive upper bound on the creation date.

        Returns:
            One page of journal entries.
        """
        rows, total = app.state.store.list_journal(
            page_no=page_no,
            page_size=page_size,
            status=status,
            ticker=ticker,
            from_date=from_date,
            to_date=to_date,
        )
        return JournalList(
            items=[JournalEntry.model_validate(row) for row in rows],
            page_no=page_no,
            page_size=page_size,
            total=total,
        )

    _mount_ui(app)
    return app


def _thread_title(messages: list[dict[str, Any]]) -> str:
    """Build a thread title from the first user message.

    Args:
        messages: UI messages from the chat request.

    Returns:
        The first user text, trimmed to 60 characters, or a default.
    """
    for message in messages:
        if message.get("role") != "user":
            continue
        parts = message.get("parts")
        if not isinstance(parts, list):
            continue
        text = " ".join(
            part["text"]
            for part in parts
            if isinstance(part, dict)
            and part.get("type") == "text"
            and isinstance(part.get("text"), str)
        )
        title = " ".join(text.split())
        if title:
            return title[:60]
    return "New conversation"


def _thread_summary(record: ThreadRecord) -> ThreadSummary:
    return ThreadSummary(
        thread_id=record.thread_id,
        title=record.title,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


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
        The ticket and the decision context.
    """
    raw_args = request.get("args")
    ticket = raw_args if isinstance(raw_args, dict) else {}
    return {
        "ticket": ticket,
        "rationale": state.get("draft_recommendation"),
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
            A short hint.
        """
        return "Error: UI build not found."
