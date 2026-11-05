"""Chat model construction for DeepSeek models on the Anthropic protocol."""

from typing import Any, cast

import pytest
from langchain_core.tools import tool
from tradecopilot_agent.llm import (
    DEEPSEEK_ANTHROPIC_URL,
    MAX_TOKENS,
    AnthropicCompatibleChat,
    build_chat_model,
)


@tool
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


def test_deepseek_model_uses_the_anthropic_protocol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """anthropic:deepseek* builds the compatible client."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "key")
    monkeypatch.delenv("DEEPSEEK_ANTHROPIC_BASE_URL", raising=False)

    model = build_chat_model("anthropic:deepseek-flash")

    assert isinstance(model, AnthropicCompatibleChat)
    assert model.anthropic_api_url == DEEPSEEK_ANTHROPIC_URL
    assert model.max_tokens == MAX_TOKENS
    assert model.thinking == {"type": "enabled"}
    assert model.anthropic_api_key.get_secret_value() == "key"


def test_deepseek_requires_its_own_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """A DeepSeek spec needs DEEPSEEK_API_KEY."""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        build_chat_model("anthropic:deepseek-flash")


def test_forced_tool_choice_survives_thinking(monkeypatch: pytest.MonkeyPatch) -> None:
    """Structured output keeps its forced tool choice."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "key")
    model = build_chat_model("anthropic:deepseek-flash")

    bound = model.bind_tools([add], tool_choice="any")

    assert cast(Any, bound).kwargs.get("tool_choice") == {"type": "any"}
