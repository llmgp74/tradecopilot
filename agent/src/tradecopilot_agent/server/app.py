"""FastAPI application exposing the HTTP API."""

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from pydantic import BaseModel

from tradecopilot_agent import __version__
from tradecopilot_agent.agent import build_agent
from tradecopilot_agent.config import Settings, get_settings
from tradecopilot_agent.llm import build_provider_model
from tradecopilot_agent.memory import MemoryConfig
from tradecopilot_agent.models import (
    AppSettings,
    AppSettingsPatch,
    Health,
    JournalEntry,
    JournalList,
    JournalStatus,
    Portfolio,
    PortfolioRange,
    Profile,
    ProfilePatch,
    ProviderCredential,
    ProviderCredentialPatch,
    ThreadDetail,
    ThreadList,
    ThreadSummary,
)
from tradecopilot_agent.outcomes import attach_outcomes
from tradecopilot_agent.portfolio import PortfolioUnavailable, fetch_portfolio
from tradecopilot_agent.promotion import derive_suggestions
from tradecopilot_agent.server.ai_sdk.convert import to_ui_messages
from tradecopilot_agent.server.model_settings import (
    resolve_model,
    validate_provider_patch,
    validate_settings_patch,
)
from tradecopilot_agent.server.streaming import (
    STREAM_HEADERS,
    sse,
    stream_chat,
)
from tradecopilot_agent.sources import LiveSource
from tradecopilot_agent.store import Store, ThreadRecord
from tradecopilot_agent.web import build_web_search

GraphFactory = Callable[[FastAPI, str], Any]
PortfolioFetcher = Callable[[AppSettings, str], Awaitable[Portfolio]]


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
    reasoning: str | None = None
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
    # The desktop webview origin differs from the agent origin, so the app
    # must answer CORS preflight for it. No cookies are used.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "tauri://localhost",
            "http://tauri.localhost",
            "http://localhost:1420",
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = settings or get_settings()
    app.state.graph_factory = graph_factory
    app.state.portfolio_fetcher = portfolio_fetcher or fetch_portfolio
    app.state.graphs = {}

    @app.get("/api/health", response_model=Health)
    async def health() -> Health:
        """Report that the server is running and which model it uses.

        Returns:
            The readiness payload.
        """
        effective = _effective_settings(app)
        return Health(
            status="ok",
            model_provider=effective.model_provider,
            model_id=effective.model_id,
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
        effective = _effective_settings(app)
        reasoning = body.reasoning or ""
        if body.reasoning is not None:
            try:
                validate_settings_patch(effective, {"reasoning_effort": reasoning})
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            graph = _get_graph(app, reasoning)
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
            graph = _get_graph(app, "")
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
            return await fetcher(_effective_settings(app), range_)
        except PortfolioUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/settings", response_model=AppSettings)
    async def get_app_settings(response: Response) -> AppSettings:
        """Return the effective application settings.

        Args:
            response: Response used to disable caching.

        Returns:
            The effective settings, with secrets in plaintext.
        """
        response.headers["Cache-Control"] = "no-store"
        return _effective_settings(app)

    @app.patch("/api/settings", response_model=AppSettings)
    async def update_app_settings(
        body: AppSettingsPatch, response: Response
    ) -> AppSettings:
        """Apply a partial settings update.

        Args:
            body: Fields to change. Omitted fields are untouched.
            response: Response used to disable caching.

        Returns:
            The effective settings after the update.
        """
        changes = {
            key: value
            for key, value in body.model_dump(exclude_unset=True).items()
            if value is not None
        }
        # The saved reasoning default belongs to the selected model. Switching
        # models drops it instead of rejecting the switch because the old value
        # is missing from the new model's options.
        if (
            "model_provider" in changes or "model_id" in changes
        ) and "reasoning_effort" not in changes:
            changes["reasoning_effort"] = ""
        try:
            validate_settings_patch(_effective_settings(app), changes)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        app.state.store.patch_settings(changes)
        # The graph captures the model, its reasoning, and the search key when
        # it is built.
        if {
            "model_provider",
            "model_id",
            "reasoning_effort",
            "exa_api_key",
        } & changes.keys():
            app.state.graphs.clear()
        response.headers["Cache-Control"] = "no-store"
        return _effective_settings(app)

    @app.put("/api/providers/{provider_id}", response_model=AppSettings)
    async def put_provider(
        provider_id: str, body: ProviderCredentialPatch, response: Response
    ) -> AppSettings:
        """Store one provider and its configured models.

        Args:
            provider_id: Catalog provider id.
            body: Credentials and model list.
            response: Response used to disable caching.

        Returns:
            The effective settings after the update.

        Raises:
            HTTPException: 400 when the provider payload is invalid.
        """
        try:
            validate_provider_patch(body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        app.state.store.upsert_provider(
            ProviderCredential(
                provider_id=provider_id,
                api_key=body.api_key,
                base_url=body.base_url,
                npm=body.npm,
                models=body.models,
            )
        )
        app.state.graphs.clear()
        response.headers["Cache-Control"] = "no-store"
        return _effective_settings(app)

    @app.delete("/api/providers/{provider_id}", response_model=AppSettings)
    async def delete_provider(provider_id: str, response: Response) -> AppSettings:
        """Delete one provider and its configured models.

        Args:
            provider_id: Catalog provider id.
            response: Response used to disable caching.

        Returns:
            The effective settings after the deletion.
        """
        app.state.store.delete_provider(provider_id)
        app.state.graphs.clear()
        response.headers["Cache-Control"] = "no-store"
        return _effective_settings(app)

    @app.get("/api/profile", response_model=Profile)
    async def get_profile() -> Profile:
        """Return the user profile and its suggestions.

        Returns:
            The full profile.
        """
        return _profile_payload(app)

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
        app.state.store.patch_profile(changes)
        return _profile_payload(app)

    @app.post("/api/profile/suggestions/{key}/dismiss", status_code=204)
    async def dismiss_suggestion(key: str) -> Response:
        """Remember that the user declined a profile suggestion.

        Args:
            key: Stable suggestion key from the profile response.

        Returns:
            An empty response.
        """
        app.state.store.dismiss_suggestion(key)
        return Response(status_code=204)

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
        rows = attach_outcomes(rows, app.state.store)
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


def _profile_payload(app: FastAPI) -> Profile:
    """Read the profile and attach the suggestions derived from the journal.

    Args:
        app: Application whose state holds the store.

    Returns:
        The profile with current suggestions.
    """
    profile = app.state.store.get_profile()
    rows, _ = app.state.store.list_journal(page_no=1, page_size=10_000)
    suggestions = derive_suggestions(
        rows,
        profile,
        app.state.store.dismissed_suggestion_keys(),
        datetime.now(tz=UTC),
    )
    return Profile.model_validate({**profile, "suggestions": suggestions})


def _get_graph(app: FastAPI, reasoning: str) -> Any:
    """Return the graph for the effective reasoning value, building it once.

    Args:
        app: Application holding the factory and checkpointer.
        reasoning: Per-turn override, empty to use the saved default.

    Returns:
        The compiled graph.
    """
    effective = reasoning or _effective_settings(app).reasoning_effort
    graph = app.state.graphs.get(effective)
    if graph is not None:
        return graph
    factory: GraphFactory = app.state.graph_factory or _default_graph
    graph = factory(app, effective)
    app.state.graphs[effective] = graph
    return graph


def _default_graph(app: FastAPI, reasoning: str) -> Any:
    """Build the DeepAgents graph with the application checkpointer.

    Args:
        app: Application holding the settings and checkpointer.
        reasoning: Effective reasoning value.

    Returns:
        The compiled graph.

    Raises:
        RuntimeError: When no model is configured.
    """
    effective = _effective_settings(app)
    resolved = resolve_model(effective)
    if resolved is None:
        raise RuntimeError("No model is configured. Choose one in Settings.")
    credential, model = resolved
    chat_model = build_provider_model(
        effective.model_provider, model.id, credential, reasoning
    )
    config = MemoryConfig(condition="full", store=app.state.store)
    return build_agent(
        config,
        LiveSource(lambda: _effective_settings(app)),
        checkpointer=app.state.checkpointer,
        model=chat_model,
        web_search=build_web_search(
            effective.model_provider,
            credential.api_key,
            effective.exa_api_key,
        ),
    )


def _effective_settings(app: FastAPI) -> AppSettings:
    """Return the stored settings. Credentials never come from the environment.

    Args:
        app: Application holding the store.

    Returns:
        The stored settings with provider credentials.
    """
    settings: AppSettings = app.state.store.get_settings()
    return settings


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
    ticket = state.get("pending_ticket")
    if not isinstance(ticket, dict):
        return {"error": "No matching pending ticket."}
    if isinstance(raw_args, dict) and raw_args.get("ticket_id") != ticket.get("id"):
        return {"error": "No matching pending ticket."}
    return {
        "ticket": ticket,
        "rationale": state.get("draft_recommendation"),
        "portfolio_impact": state.get("portfolio_impact"),
    }


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
