"""Build the agent graph shared by the live app and the evaluation harness."""

from datetime import date
from typing import Any

from deepagents import create_deep_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    TodoListMiddleware,
)
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from tradecopilot_agent.claims import build_extractor
from tradecopilot_agent.config import get_settings
from tradecopilot_agent.data import DataSource
from tradecopilot_agent.memory import MemoryConfig
from tradecopilot_agent.middleware import (
    AnnotationMiddleware,
    TodoStreamMiddleware,
    ToolAvailabilityMiddleware,
    ToolResultMiddleware,
    TradingMemoryMiddleware,
    TurnMiddleware,
)
from tradecopilot_agent.prompt import SYSTEM_PROMPT
from tradecopilot_agent.state import TradingState
from tradecopilot_agent.tools import build_tools

MODEL_CALL_LIMIT = 20


def build_agent(
    config: MemoryConfig,
    source: DataSource,
    as_of: date | None = None,
    *,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    model: str | None = None,
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
        model: ``provider:model`` override. Falls back to ``AGENT_MODEL``.

    Returns:
        The compiled agent graph.

    Raises:
        RuntimeError: If no model is provided or configured.
    """
    model_name = model or get_settings().agent_model
    if model_name is None:
        raise RuntimeError(
            "AGENT_MODEL is not set. Provide a provider:model string, "
            "for example anthropic:claude-sonnet-5."
        )

    extract_claims = build_extractor(model_name)
    middleware: list[AgentMiddleware[Any, Any, Any]] = [
        TurnMiddleware(),
        TradingMemoryMiddleware(config),
        ToolAvailabilityMiddleware(source),
        ToolResultMiddleware(as_of),
        AnnotationMiddleware(extract_claims),
        TodoStreamMiddleware(),
        TodoListMiddleware(),
        ModelCallLimitMiddleware(run_limit=MODEL_CALL_LIMIT, exit_behavior="end"),
    ]
    return create_deep_agent(
        model=model_name,
        tools=build_tools(source, config.store, as_of, extract_claims),
        system_prompt=SYSTEM_PROMPT,
        middleware=middleware,
        state_schema=TradingState,
        checkpointer=checkpointer,
    )
