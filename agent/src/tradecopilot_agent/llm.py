"""Chat model construction for DeepSeek models on the Anthropic protocol."""

import os
import warnings
from typing import Any, cast

from langchain.chat_models import init_chat_model
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel

DEEPSEEK_ANTHROPIC_URL = "https://api.deepseek.com/anthropic"
DEEPSEEK_PREFIX = "deepseek"
MAX_TOKENS = 64000


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
