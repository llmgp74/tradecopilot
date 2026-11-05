"""Middleware that adds memory, availability, evidence, and annotation.

Only the tool artifact is trusted for state updates. Tool content is written by
the tool itself; nothing here parses model-facing text.
"""

import re
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.config import get_stream_writer
from langgraph.types import Command

from tradecopilot_agent.claims import match_claims
from tradecopilot_agent.data import DataSource
from tradecopilot_agent.memory import MemoryConfig
from tradecopilot_agent.state import (
    TURN_FIELDS,
    Claim,
    ToolOutput,
    TradingState,
)
from tradecopilot_agent.tools import (
    EVIDENCE_TOOL_NAMES,
    GATHER_BUDGET,
    TOOL_CAPABILITIES,
    TRADING_TOOL_NAMES,
)

_TICKER = re.compile(r"\b[A-Z]{1,5}\b")
_JOURNAL_LIMIT = 10


def request_tickers(text: str, known: set[str]) -> list[str]:
    """Return known tickers mentioned in the text.

    Args:
        text: The latest user message.
        known: Tickers already known to the app.

    Returns:
        Matched tickers in text order, without duplicates.
    """
    return list(
        dict.fromkeys(token for token in _TICKER.findall(text) if token in known)
    )


def render_memory(
    condition: str, profile: dict[str, Any], entries: list[dict[str, Any]]
) -> str:
    """Render the memory block for one model call.

    Args:
        condition: One of none, prose, structured, or full.
        profile: The ground-truth profile.
        entries: Recent decisions for full memory.

    Returns:
        The text appended to the system prompt. Empty for no memory.
    """
    if condition == "none":
        return ""
    execution = profile.get("execution", {})
    if condition == "prose":
        return (
            "The user is a {risk} investor with a {horizon} horizon. "
            "Single positions should stay under {cap} percent. "
            "Avoid: {avoid}. Watchlist: {watch}."
        ).format(
            risk=profile.get("risk_band", "moderate"),
            horizon=profile.get("horizon", "weeks"),
            cap=profile.get("position_cap_pct", 10),
            avoid=", ".join(profile.get("sector_exclusions", [])) or "nothing",
            watch=", ".join(profile.get("watchlist", [])) or "nothing",
        )
    structured = "\n".join(
        [
            "User profile (structured):",
            f"risk_band: {profile.get('risk_band', 'moderate')}",
            f"position_cap_pct: {profile.get('position_cap_pct', 10)}",
            "sector_exclusions: "
            + (", ".join(profile.get("sector_exclusions", [])) or "none"),
            f"horizon: {profile.get('horizon', 'weeks')}",
            "watchlist: " + (", ".join(profile.get("watchlist", [])) or "none"),
            "execution: autonomous={}, max_order_notional={}".format(
                bool(execution.get("autonomous", False)),
                execution.get("max_order_notional", 0),
            ),
        ]
    )
    if condition != "full" or not entries:
        return structured
    lines = [structured, "Recent decisions:"]
    for entry in entries:
        legs = ", ".join(
            f"{leg.get('side')} {leg.get('qty')} {leg.get('ticker')}"
            for leg in entry.get("legs", [])
        )
        line = (
            f"- {entry.get('id')} {str(entry.get('created_at', ''))[:10]} "
            f"{entry.get('status')} {legs}: {entry.get('thesis', '')}"
        )
        if entry.get("rejection_reason"):
            line += f" (reason: {entry['rejection_reason']})"
        lines.append(line)
    return "\n".join(lines)


def artifact_updates(output: ToolOutput, as_of: date | None) -> dict[str, Any]:
    """Translate a tool artifact into state updates.

    Args:
        output: The artifact returned by a trading tool.
        as_of: Evaluation cutoff, or ``None`` for live runs.

    Returns:
        A partial state update. Empty when the artifact carries nothing.
    """
    updates: dict[str, Any] = {}
    records = [
        record for record in output.evidence if _in_cutoff(record.published_at, as_of)
    ]
    if records:
        updates["evidence"] = {
            record.id: record.model_dump(mode="json") for record in records
        }
    if output.proposal is not None:
        proposal = output.proposal
        updates["pending_ticket"] = proposal
        updates["draft_recommendation"] = {
            "ticket_id": proposal.get("id"),
            "legs": proposal.get("legs", []),
            "thesis": proposal.get("thesis", ""),
            "horizon": proposal.get("horizon", "weeks"),
        }
    if output.portfolio_impact is not None:
        updates["portfolio_impact"] = output.portfolio_impact
    if output.verification:
        updates["verification"] = output.verification
    if output.ticket_done:
        updates["pending_ticket"] = None
    return updates


def _in_cutoff(published_at: str | None, as_of: date | None) -> bool:
    if as_of is None or published_at is None:
        return True
    try:
        return date.fromisoformat(published_at[:10]) <= as_of
    except ValueError:
        return True


def budget_denied(state: dict[str, Any], tool_name: str) -> bool:
    """Return whether the gather budget blocks this tool call."""
    return (
        tool_name in EVIDENCE_TOOL_NAMES
        and int(state.get("gather_calls", 0)) >= GATHER_BUDGET
    )


def annotate(
    text: str,
    evidence: dict[str, Any],
    extract: Callable[[str], list[Claim]],
) -> list[dict[str, Any]]:
    """Extract and check the claims in a final answer.

    Args:
        text: The assistant answer.
        evidence: The ledger.
        extract: Claim extractor.

    Returns:
        Verdicts with the answer scope, or one ``unavailable`` entry when the
        extractor fails.
    """
    if not text.strip():
        return []
    try:
        claims = extract(text)
        return match_claims(claims, evidence, scope="answer")
    except Exception:
        return [{"scope": "answer", "status": "unavailable"}]


def _available(source: DataSource) -> tuple[set[str], set[str]]:
    capabilities = set(source.capabilities())
    available = {
        name
        for name, capability in TOOL_CAPABILITIES.items()
        if not capability or capability in capabilities
    }
    hidden = set(TRADING_TOOL_NAMES - available)
    return available, hidden


class TurnMiddleware(AgentMiddleware[TradingState, Any, Any]):
    """Clears turn-scoped state when a new user message starts."""

    def before_agent(self, state: TradingState, runtime: Any) -> dict[str, Any] | None:
        """Clear proposal state at the start of a new turn.

        Args:
            state: Current graph state.
            runtime: Runtime context.

        Returns:
            The cleared fields, or ``None`` when resuming an approval.
        """
        messages = state.get("messages", [])
        if not messages or not isinstance(messages[-1], HumanMessage):
            return None
        return dict(TURN_FIELDS)


class TradingMemoryMiddleware(AgentMiddleware[TradingState, Any, Any]):
    """Injects the memory block for the configured condition."""

    def __init__(self, config: MemoryConfig) -> None:
        """Store the memory configuration.

        Args:
            config: Condition and store.
        """
        super().__init__()
        self.config = config

    def wrap_model_call(self, request: Any, handler: Any) -> Any:
        """Append the memory block to the system prompt.

        Args:
            request: Model request.
            handler: Next handler.

        Returns:
            The model response.
        """
        block = self._block(request)
        if not block:
            return handler(request)
        prompt = request.system_prompt or ""
        return handler(request.override(system_prompt=f"{prompt}\n\n{block}"))

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        """Async version of ``wrap_model_call``."""
        block = self._block(request)
        if not block:
            return await handler(request)
        prompt = request.system_prompt or ""
        return await handler(request.override(system_prompt=f"{prompt}\n\n{block}"))

    def _block(self, request: Any) -> str:
        if self.config.condition == "none":
            return ""
        profile = self.config.store.get_profile()
        entries: list[dict[str, Any]] = []
        if self.config.condition == "full":
            text = _last_user_text(request)
            known = set(profile.get("watchlist", []))
            state = getattr(request, "state", {}) or {}
            known.update(_ledger_tickers(state.get("evidence", {})))
            tickers = request_tickers(text, known)
            if tickers:
                since = (datetime.now(tz=UTC).date() - timedelta(days=90)).isoformat()
                entries = self.config.store.recent_journal(
                    tickers, since=since, limit=_JOURNAL_LIMIT
                )
        return render_memory(self.config.condition, profile, entries)


class ToolAvailabilityMiddleware(AgentMiddleware[TradingState, Any, Any]):
    """Hides unconfigured trading tools and refuses direct calls to them."""

    def __init__(self, source: DataSource) -> None:
        """Bind the middleware to the data source.

        Args:
            source: Provider data whose capabilities change at runtime.
        """
        super().__init__()
        self.source = source

    def wrap_model_call(self, request: Any, handler: Any) -> Any:
        """Filter the model tool list and note hidden sources.

        Args:
            request: Model request.
            handler: Next handler.

        Returns:
            The model response.
        """
        available, hidden = _available(self.source)
        tools = [
            tool
            for tool in request.tools
            if getattr(tool, "name", "") not in TRADING_TOOL_NAMES
            or getattr(tool, "name", "") in available
        ]
        prompt = request.system_prompt or ""
        if hidden:
            labels = ", ".join(sorted(hidden))
            prompt = f"{prompt}\n\nUnavailable trading tools: {labels}."
        return handler(request.override(tools=tools, system_prompt=prompt))

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        """Async version of ``wrap_model_call``."""
        available, hidden = _available(self.source)
        tools = [
            tool
            for tool in request.tools
            if getattr(tool, "name", "") not in TRADING_TOOL_NAMES
            or getattr(tool, "name", "") in available
        ]
        prompt = request.system_prompt or ""
        if hidden:
            labels = ", ".join(sorted(hidden))
            prompt = f"{prompt}\n\nUnavailable trading tools: {labels}."
        return await handler(request.override(tools=tools, system_prompt=prompt))

    def wrap_tool_call(self, request: Any, handler: Any) -> Any:
        """Refuse a direct call to an unavailable trading tool."""
        return self._guard(request, handler)

    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        """Async version of ``wrap_tool_call``."""
        denied = self._denied(request)
        if denied is not None:
            return denied
        return await handler(request)

    def _guard(self, request: Any, handler: Any) -> Any:
        denied = self._denied(request)
        return denied if denied is not None else handler(request)

    def _denied(self, request: Any) -> ToolMessage | None:
        call = getattr(request, "tool_call", {}) or {}
        name = str(call.get("name", ""))
        if name not in TRADING_TOOL_NAMES:
            return None
        available, _ = _available(self.source)
        if name in available:
            return None
        return ToolMessage(
            content=f"{name} is not available. Configure its provider in settings.",
            tool_call_id=str(call.get("id", "")),
        )


class ToolResultMiddleware(AgentMiddleware[TradingState, Any, Any]):
    """Records artifacts and enforces the gather budget."""

    def __init__(self, as_of: date | None) -> None:
        """Store the evaluation cutoff.

        Args:
            as_of: Cutoff date, or ``None`` for live runs.
        """
        super().__init__()
        self.as_of = as_of

    def wrap_tool_call(self, request: Any, handler: Any) -> Any:
        """Record the tool artifact into state."""
        return self._consume(request, handler)

    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        """Async version of ``wrap_tool_call``."""
        state = dict(getattr(request, "state", {}) or {})
        call = getattr(request, "tool_call", {}) or {}
        name = str(call.get("name", ""))
        if budget_denied(state, name):
            return ToolMessage(
                content="Evidence budget reached. Answer with what you have.",
                tool_call_id=str(call.get("id", "")),
            )
        result = await handler(request)
        return _with_updates(result, state, name, self.as_of)

    def _consume(self, request: Any, handler: Any) -> Any:
        state = dict(getattr(request, "state", {}) or {})
        call = getattr(request, "tool_call", {}) or {}
        name = str(call.get("name", ""))
        if budget_denied(state, name):
            return ToolMessage(
                content="Evidence budget reached. Answer with what you have.",
                tool_call_id=str(call.get("id", "")),
            )
        result = handler(request)
        return _with_updates(result, state, name, self.as_of)


def _with_updates(
    result: Any, state: dict[str, Any], tool_name: str, as_of: date | None
) -> Any:
    if not isinstance(result, ToolMessage):
        return result
    artifact = result.artifact
    updates: dict[str, Any] = {}
    if isinstance(artifact, dict):
        try:
            updates = artifact_updates(ToolOutput.model_validate(artifact), as_of)
        except ValueError:
            updates = {}
    if tool_name in EVIDENCE_TOOL_NAMES:
        updates["gather_calls"] = int(state.get("gather_calls", 0)) + 1
    if not updates:
        return result
    return Command(update={**updates, "messages": [result]})


class AnnotationMiddleware(AgentMiddleware[TradingState, Any, Any]):
    """Checks the claims in the final answer."""

    def __init__(self, extract: Callable[[str], list[Claim]]) -> None:
        """Store the claim extractor.

        Args:
            extract: Callable that turns prose into claims.
        """
        super().__init__()
        self.extract = extract

    def after_agent(self, state: TradingState, runtime: Any) -> dict[str, Any] | None:
        """Emit answer verdicts after the agent finishes.

        Args:
            state: Final graph state.
            runtime: Runtime context.

        Returns:
            The verification channel update, or ``None`` when there is no text.
        """
        text = _last_answer_text(state)
        if not text:
            return None
        verdicts = annotate(text, state.get("evidence", {}), self.extract)
        if not verdicts:
            return None
        writer = get_stream_writer()
        writer({"type": "verification", "claims": verdicts})
        return {"verification": verdicts}

    async def aafter_agent(
        self, state: TradingState, runtime: Any
    ) -> dict[str, Any] | None:
        """Async version of ``after_agent``."""
        return self.after_agent(state, runtime)


class TodoStreamMiddleware(AgentMiddleware[TradingState, Any, Any]):
    """Streams the todo list as a data part when it changes."""

    def after_model(self, state: TradingState, runtime: Any) -> dict[str, Any] | None:
        """Emit todos when the list changed.

        Args:
            state: Current graph state.
            runtime: Runtime context.

        Returns:
            The snapshot update, or ``None`` when nothing changed.
        """
        todos = state.get("todos") or []
        if todos == state.get("todos_snapshot"):
            return None
        if todos:
            get_stream_writer()({"type": "todos", "todos": todos})
        return {"todos_snapshot": todos}

    async def aafter_model(
        self, state: TradingState, runtime: Any
    ) -> dict[str, Any] | None:
        """Async version of ``after_model``."""
        return self.after_model(state, runtime)


def _ledger_tickers(evidence: dict[str, Any]) -> set[str]:
    tickers: set[str] = set()
    for record in evidence.values():
        payload = record.get("payload") if isinstance(record, dict) else None
        if not isinstance(payload, dict):
            continue
        for position in payload.get("positions", []) or []:
            if isinstance(position, dict) and position.get("ticker"):
                tickers.add(str(position["ticker"]).upper())
    return tickers


def _last_user_text(request: Any) -> str:
    messages = getattr(request, "messages", []) or []
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            content = message.content
            return content if isinstance(content, str) else str(content)
    return ""


def _last_answer_text(state: TradingState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, AIMessage):
            if message.tool_calls:
                continue
            content = message.content
            return content if isinstance(content, str) else str(content)
    return ""
