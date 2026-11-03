from datetime import date
from typing import Any

from deepagents import create_deep_agent
from langgraph.graph.state import CompiledStateGraph

from tradecopilot_agent.config import get_settings
from tradecopilot_agent.data import DataSource
from tradecopilot_agent.memory import MemoryConfig

SYSTEM_PROMPT = "You are TradeCopilot, a single-user trading co-pilot."


def build_agent(
    config: MemoryConfig,
    source: DataSource,
    as_of: date | None = None,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """Build one agent graph for a memory condition and a data source.

    Tools and middleware are added behind this signature, so callers never
    change as features land.

    Args:
        config: Memory condition and backing store.
        source: Data source the tools are bound to.
        as_of: Evaluation cutoff. Tools must not use data dated after it.
            ``None`` means live use.

    Returns:
        The compiled agent graph.

    Raises:
        RuntimeError: If ``AGENT_MODEL`` is not configured.
    """
    model = get_settings().agent_model
    if model is None:
        raise RuntimeError(
            "AGENT_MODEL is not set. Provide a provider:model string, "
            "for example anthropic:claude-sonnet-5."
        )

    return create_deep_agent(
        model=model,
        tools=[],
        system_prompt=SYSTEM_PROMPT,
    )
