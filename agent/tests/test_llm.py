"""Chat model construction for DeepSeek models on the Anthropic protocol."""

from typing import Any, cast

import pytest
from langchain_core.tools import tool
from tradecopilot_agent.llm import (
    DEEPSEEK_ANTHROPIC_URL,
    MAX_TOKENS,
    AnthropicCompatibleChat,
    build_chat_model,
    build_provider_model,
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


def test_openai_model_uses_stored_key_base_url_and_reasoning() -> None:
    """Construction takes the key, base URL, and reasoning from the row."""
    from tradecopilot_agent.models import ProviderCredential, ProviderModel

    credential = ProviderCredential(
        provider_id="openrouter",
        api_key="sk-x",
        base_url="https://openrouter.ai/api/v1",
        npm="@ai-sdk/openai-compatible",
        models=[
            ProviderModel(
                id="m",
                name="M",
                reasoning_options=[
                    {"type": "effort", "values": ["low", "high"]},
                ],
            )
        ],
    )

    model = build_provider_model("openrouter", "m", credential, "high")

    assert model.model_name == "m"
    assert cast(Any, model).reasoning == {"effort": "high"}
    assert str(model.openai_api_base) == "https://openrouter.ai/api/v1"
    assert model.openai_api_key.get_secret_value() == "sk-x"


def test_openai_compatible_model_keeps_reasoning_content() -> None:
    """Qwen-style reasoning_content survives into the streamed chunk."""
    from langchain_core.messages import AIMessageChunk
    from tradecopilot_agent.llm import OpenAICompatibleChat

    model = OpenAICompatibleChat(model="qwen3.8-flash", api_key="k")
    chunk = {
        "choices": [{"delta": {"reasoning_content": "weighing the trade"}}],
        "usage": None,
    }

    generation = model._convert_chunk_to_generation_chunk(chunk, AIMessageChunk, None)

    assert generation is not None
    assert (
        generation.message.additional_kwargs["reasoning_content"]
        == "weighing the trade"
    )


def _openrouter_credential() -> Any:
    from tradecopilot_agent.models import ProviderCredential, ProviderModel

    return ProviderCredential(
        provider_id="openrouter",
        api_key="sk-o",
        base_url="https://openrouter.ai/api/v1",
        npm="@openrouter/ai-sdk-provider",
        models=[
            ProviderModel(
                id="openai/gpt-5.1",
                name="GPT-5.1",
                reasoning_options=[
                    {"type": "effort", "values": ["none", "low", "medium", "high"]}
                ],
            )
        ],
    )


def test_openrouter_reasoning_off_is_sent_as_an_object() -> None:
    """OpenRouter turns thinking off through its own reasoning field."""
    from langchain_core.messages import HumanMessage

    model = build_provider_model(
        "openrouter", "openai/gpt-5.1", _openrouter_credential(), "off"
    )

    payload = cast(Any, model)._get_request_payload([HumanMessage("hi")])

    assert payload["reasoning"] == {"enabled": False}


def test_openrouter_effort_maps_to_the_reasoning_field() -> None:
    """An effort level becomes OpenRouter's reasoning effort."""
    from langchain_core.messages import HumanMessage

    model = build_provider_model(
        "openrouter", "openai/gpt-5.1", _openrouter_credential(), "high"
    )

    payload = cast(Any, model)._get_request_payload([HumanMessage("hi")])

    assert payload["reasoning"] == {"effort": "high"}


def test_openai_compatible_model_keeps_openrouter_reasoning() -> None:
    """OpenRouter's reasoning delta becomes the chain-of-thought text."""
    from langchain_core.messages import AIMessageChunk
    from tradecopilot_agent.llm import OpenAICompatibleChat

    model = OpenAICompatibleChat(model="m", api_key="k")
    chunk = {"choices": [{"delta": {"reasoning": "step one"}}], "usage": None}

    generation = model._convert_chunk_to_generation_chunk(chunk, AIMessageChunk, None)

    assert generation is not None
    assert generation.message.additional_kwargs["reasoning_content"] == "step one"


def test_deepseek_uses_the_anthropic_protocol() -> None:
    """The deepseek provider id maps to the Anthropic-compatible client."""
    from tradecopilot_agent.models import ProviderCredential, ProviderModel

    credential = ProviderCredential(
        provider_id="deepseek",
        api_key="sk-d",
        npm="@ai-sdk/openai-compatible",
        models=[ProviderModel(id="deepseek-flash", name="DeepSeek Flash")],
    )

    model = build_provider_model("deepseek", "deepseek-flash", credential, "off")

    assert isinstance(model, AnthropicCompatibleChat)
    assert model.thinking == {"type": "disabled"}


def test_unsupported_npm_is_rejected() -> None:
    """A provider outside the allowlist cannot be constructed."""
    from tradecopilot_agent.models import ProviderCredential

    credential = ProviderCredential(
        provider_id="azure", api_key="k", npm="@ai-sdk/azure"
    )

    with pytest.raises(ValueError, match="not supported"):
        build_provider_model("azure", "m", credential, "")


def test_deepseek_catalog_base_url_maps_to_the_anthropic_endpoint() -> None:
    """The catalog API root is not the Anthropic-compatible endpoint."""
    from tradecopilot_agent.models import ProviderCredential, ProviderModel

    credential = ProviderCredential(
        provider_id="deepseek",
        api_key="k",
        base_url="https://api.deepseek.com",
        npm="@ai-sdk/openai-compatible",
        models=[ProviderModel(id="deepseek-flash", name="DeepSeek Flash")],
    )

    model = build_provider_model("deepseek", "deepseek-flash", credential, "")

    assert model.anthropic_api_url == DEEPSEEK_ANTHROPIC_URL
