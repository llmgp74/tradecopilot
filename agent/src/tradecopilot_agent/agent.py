"""Build the agent graph shared by the live app and the evaluation harness."""

from datetime import UTC, date, datetime, time
from typing import Any

from deepagents import create_deep_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    TodoListMiddleware,
)
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from tradecopilot_agent.config import get_settings
from tradecopilot_agent.data import DataSource
from tradecopilot_agent.llm import build_chat_model
from tradecopilot_agent.memory import MemoryConfig
from tradecopilot_agent.middleware import (
    TodoStreamMiddleware,
    ToolAvailabilityMiddleware,
    ToolResultMiddleware,
    TradingMemoryMiddleware,
    TurnMiddleware,
)
from tradecopilot_agent.prompt import SYSTEM_PROMPT, WEB_SEARCH_PROMPT
from tradecopilot_agent.state import TradingState
from tradecopilot_agent.tools import build_tools
from tradecopilot_agent.web import WebSearch

MODEL_CALL_LIMIT = 20


def build_agent(
    config: MemoryConfig,
    source: DataSource,
    as_of: date | None = None,
    *,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    model: str | BaseChatModel | None = None,
    decision_time: datetime | None = None,
    web_search: WebSearch | None = None,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """Build one agent graph for a memory condition and a data source.

    Args:
        config: Memory condition and backing store.
        source: Data source the tools are bound to.
        as_of: Evaluation cutoff. Tools must not use data dated after it.
            ``None`` means live use.
        checkpointer: Persists threads and interrupts. The server passes the
            shared SQLite saver. The evaluation harness passes a saver bound
            to its scenario database, or ``None`` for single-shot runs.
        model: ``provider:model`` override or a constructed chat model. Falls
            back to ``AGENT_MODEL`` when omitted. A local model avoids provider
            construction, but must support tool binding.
        decision_time: Timezone-aware cutoff for journal retrieval. If omitted,
            ``as_of`` uses that UTC day's end; live runs use the current time.
        web_search: Web search provider. The tool is hidden when omitted.

    Returns:
        The compiled agent graph.

    Raises:
        RuntimeError: If no model is provided or configured.
        ValueError: If ``decision_time`` has no timezone.
    """
    if decision_time is not None and (
        decision_time.tzinfo is None or decision_time.utcoffset() is None
    ):
        raise ValueError("decision_time must include a timezone.")
    memory_time = decision_time
    if memory_time is None and as_of is not None:
        memory_time = datetime.combine(as_of, time.max, tzinfo=UTC)

    if isinstance(model, BaseChatModel):
        chat_model = model
    else:
        model_name = model or get_settings().agent_model
        if model_name is None:
            raise RuntimeError(
                "AGENT_MODEL is not set. Provide a provider:model string, "
                "for example anthropic:claude-sonnet-5."
            )
        chat_model = build_chat_model(model_name)
    middleware: list[AgentMiddleware[Any, Any, Any]] = [
        TurnMiddleware(),
        TradingMemoryMiddleware(config, decision_time=memory_time),
        ToolAvailabilityMiddleware(source),
        ToolResultMiddleware(as_of),
        TodoStreamMiddleware(),
        TodoListMiddleware(),
        ModelCallLimitMiddleware(run_limit=MODEL_CALL_LIMIT, exit_behavior="end"),
    ]
    return create_deep_agent(
        model=chat_model,
        tools=build_tools(source, config.store, as_of, searcher=web_search),
        system_prompt=SYSTEM_PROMPT
        + (WEB_SEARCH_PROMPT if web_search is not None else ""),
        middleware=middleware,
        state_schema=TradingState,
        checkpointer=checkpointer,
    )
