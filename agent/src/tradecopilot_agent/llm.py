"""Chat model construction for DeepSeek models on the Anthropic protocol."""

import os
import warnings
from typing import Any, cast

from langchain.chat_models import init_chat_model
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from tradecopilot_agent.models import ProviderCredential
from tradecopilot_agent.reasoning import openrouter_kwargs, reasoning_kwargs

DEEPSEEK_ANTHROPIC_URL = "https://api.deepseek.com/anthropic"
DEEPSEEK_API_URL = "https://api.deepseek.com"
DEEPSEEK_PREFIX = "deepseek"
MAX_TOKENS = 64000

_NPM_INTEGRATION = {
    "@ai-sdk/openai": "openai",
    "@ai-sdk/openai-compatible": "openai",
    "@ai-sdk/anthropic": "anthropic",
    "@ai-sdk/google": "google",
    "@openrouter/ai-sdk-provider": "openai",
}

SUPPORTED_NPM = frozenset(_NPM_INTEGRATION)
"""Provider client packages the app can build. Settings validation uses it."""


class AnthropicCompatibleChat(ChatAnthropic):
    """ChatAnthropic with forced tool choice preserved while thinking."""

    def bind_tools(
        self,
        tools: Any,
        *,
        tool_choice: Any = None,
        **kwargs: Any,
    ) -> Any:
        """Bind tools without dropping a forced tool choice.

        Args:
            tools: Tools to bind.
            tool_choice: Optional forced choice.
            kwargs: Extra binding options.

        Returns:
            The bound runnable.
        """
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore", message="tool_choice is forced but thinking"
            )
            bound = super().bind_tools(tools, tool_choice=tool_choice, **kwargs)
        thinking = (self.thinking or {}).get("type")
        if tool_choice and thinking in ("enabled", "adaptive"):
            if isinstance(tool_choice, str):
                forced = (
                    {"type": tool_choice}
                    if tool_choice in ("any", "auto")
                    else {"type": "tool", "name": tool_choice}
                )
            else:
                forced = tool_choice
            if isinstance(forced, dict) and forced.get("type") in ("any", "tool"):
                bound = bound.bind(tool_choice=forced)
        return bound


class OpenAICompatibleChat(ChatOpenAI):
    """ChatOpenAI that keeps the reasoning text compatible servers return.

    OpenAI reports reasoning through its Responses API, but compatible servers
    such as Qwen on DashScope return a ``reasoning_content`` field that
    ChatOpenAI drops. The chat UI reads that field for the chain-of-thought
    block, so it is copied onto each message and chunk here.
    """

    @staticmethod
    def _reasoning_text(source: Any) -> str:
        """Return the reasoning text from a response message or dict.

        Servers report it under different keys: DashScope sends
        ``reasoning_content``, OpenRouter sends ``reasoning`` or a
        ``reasoning_details`` list.

        Args:
            source: OpenAI message object or its dict form.

        Returns:
            The reasoning text, or an empty string.
        """
        if not isinstance(source, dict):
            dump = getattr(source, "model_dump", None)
            source = dump() if callable(dump) else {}
        value = source.get("reasoning_content")
        if isinstance(value, str) and value:
            return value
        value = source.get("reasoning")
        if isinstance(value, str) and value:
            return value
        details = source.get("reasoning_details")
        if isinstance(details, list):
            parts = [
                text
                for item in details
                if isinstance(item, dict)
                for text in [item.get("text") or item.get("summary")]
                if isinstance(text, str)
            ]
            return "".join(parts)
        return ""

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict[str, Any],
        default_chunk_class: type,
        base_generation_info: dict[str, Any] | None,
    ) -> ChatGenerationChunk | None:
        """Keep the reasoning delta alongside the content delta."""
        generation = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        choices = (
            chunk.get("choices") or (chunk.get("chunk") or {}).get("choices") or []
        )
        if generation is None or not choices:
            return generation
        reasoning = self._reasoning_text(choices[0].get("delta") or {})
        if reasoning:
            generation.message.additional_kwargs["reasoning_content"] = reasoning
        return generation

    def _create_chat_result(
        self,
        response: Any,
        generation_info: dict[str, Any] | None = None,
    ) -> ChatResult:
        """Keep the reasoning text from a complete response."""
        result = super()._create_chat_result(response, generation_info)
        if isinstance(response, dict):
            choices = response.get("choices") or []
            message = choices[0].get("message", {}) if choices else {}
        else:
            choices = getattr(response, "choices", None) or []
            message = choices[0].message if choices else None
        reasoning = self._reasoning_text(message)
        if reasoning and result.generations:
            result.generations[0].message.additional_kwargs["reasoning_content"] = (
                reasoning
            )
        return result


def build_chat_model(spec: str) -> BaseChatModel:
    """Build the chat model for a provider:model spec.

    Args:
        spec: ``provider:model`` string.

    Returns:
        The chat model. ``anthropic:deepseek*`` uses the Anthropic protocol
        against DeepSeek's endpoint with thinking enabled.

    Raises:
        RuntimeError: If a DeepSeek spec is used without ``DEEPSEEK_API_KEY``.
    """
    provider, _, model_id = spec.partition(":")
    if provider == "anthropic" and model_id.startswith(DEEPSEEK_PREFIX):
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not set.")
        model_object = cast(Any, AnthropicCompatibleChat)(
            model=model_id,
            anthropic_api_url=os.environ.get(
                "DEEPSEEK_ANTHROPIC_BASE_URL", DEEPSEEK_ANTHROPIC_URL
            ),
            api_key=api_key,
            thinking={"type": "enabled"},
            temperature=0,
            max_tokens=MAX_TOKENS,
        )
        return cast(BaseChatModel, model_object)
    return init_chat_model(spec)


def integration_for(provider: str, npm: str) -> str | None:
    """Map a catalog provider to the LangChain integration.

    Args:
        provider: Catalog provider id.
        npm: Catalog client package.

    Returns:
        ``openai``, ``anthropic``, ``google``, ``deepseek``, or None.
    """
    if provider == DEEPSEEK_PREFIX:
        return "deepseek"
    return _NPM_INTEGRATION.get(npm)


def build_provider_model(
    provider: str,
    model_id: str,
    credential: ProviderCredential,
    reasoning: str,
) -> BaseChatModel:
    """Build a chat model from stored provider credentials.

    Args:
        provider: Catalog provider id.
        model_id: Catalog model id.
        credential: Stored key, base URL, integration, and models.
        reasoning: Normalized reasoning value, empty for the provider default.

    Returns:
        The constructed chat model.

    Raises:
        ValueError: When the integration is unsupported.
    """
    integration = integration_for(provider, credential.npm)
    if integration is None:
        raise ValueError(f"Provider integration {credential.npm!r} is not supported.")
    entry = next((model for model in credential.models if model.id == model_id), None)
    options = entry.reasoning_options if entry is not None else []
    if provider == "openrouter":
        kwargs = openrouter_kwargs(reasoning, options)
    else:
        kwargs = reasoning_kwargs(integration, reasoning, options)

    if integration == "deepseek":
        if not reasoning:
            kwargs = {"thinking": {"type": "enabled"}}
        base_url = credential.base_url.rstrip("/")
        if base_url in ("", DEEPSEEK_API_URL):
            base_url = DEEPSEEK_ANTHROPIC_URL
        return cast(
            BaseChatModel,
            cast(Any, AnthropicCompatibleChat)(
                model=model_id,
                anthropic_api_url=base_url,
                api_key=SecretStr(credential.api_key),
                temperature=0,
                max_tokens=MAX_TOKENS,
                **kwargs,
            ),
        )
    if integration == "openai":
        return OpenAICompatibleChat(
            model=model_id,
            api_key=SecretStr(credential.api_key),
            base_url=credential.base_url or None,
            **kwargs,
        )
    if integration == "anthropic":
        return ChatAnthropic(
            model_name=model_id,
            api_key=SecretStr(credential.api_key),
            base_url=credential.base_url or None,
            **kwargs,
        )
    return ChatGoogleGenerativeAI(
        model=model_id,
        google_api_key=credential.api_key,
        **kwargs,
    )
