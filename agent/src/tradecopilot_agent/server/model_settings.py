"""Validation for provider credentials and the selected model."""

from typing import Any

from tradecopilot_agent.models import (
    AppSettings,
    ProviderCredential,
    ProviderCredentialPatch,
    ProviderModel,
)
from tradecopilot_agent.reasoning import normalize_reasoning

SUPPORTED_NPM = frozenset(
    {
        "@ai-sdk/openai",
        "@ai-sdk/openai-compatible",
        "@ai-sdk/anthropic",
        "@ai-sdk/google",
    }
)


def validate_provider_patch(patch: ProviderCredentialPatch) -> None:
    """Check a provider update before it is stored.

    Args:
        patch: The provider fields to store.

    Raises:
        ValueError: When the integration is unsupported, a model repeats, a
            model has no id, or a model cannot call tools.
    """
    if patch.npm not in SUPPORTED_NPM:
        raise ValueError(f"Provider integration {patch.npm!r} is not supported.")
    seen: set[str] = set()
    for model in patch.models:
        if not model.id:
            raise ValueError("Every model needs an id.")
        if model.id in seen:
            raise ValueError(f"Model {model.id!r} is listed twice.")
        seen.add(model.id)
        if not model.tool_call:
            raise ValueError(f"Model {model.id!r} does not support tool calls.")


def resolve_model(
    settings: AppSettings,
) -> tuple[ProviderCredential, ProviderModel] | None:
    """Return the selected provider and model.

    Args:
        settings: Effective settings including providers.

    Returns:
        The pair, or None when nothing usable is selected.
    """
    if not settings.model_provider or not settings.model_id:
        return None
    provider = next(
        (
            item
            for item in settings.providers
            if item.provider_id == settings.model_provider
        ),
        None,
    )
    if provider is None:
        return None
    model = next(
        (item for item in provider.models if item.id == settings.model_id), None
    )
    if model is None:
        return None
    return provider, model


def validate_settings_patch(current: AppSettings, changes: dict[str, Any]) -> None:
    """Check a settings update against the stored providers.

    Args:
        current: Effective settings before the update.
        changes: Fields to change.

    Raises:
        ValueError: When the selection is unusable or the reasoning value is
            not allowed for the selected model.
    """
    merged = current.model_copy(update=changes)
    selection_changed = "model_provider" in changes or "model_id" in changes
    if selection_changed and (merged.model_provider or merged.model_id):
        resolved = resolve_model(merged)
        if resolved is None:
            raise ValueError("The selected model is not configured.")
        provider, model = resolved
        if provider.api_key == "":
            raise ValueError("The selected provider has no API key.")
        if provider.npm not in SUPPORTED_NPM:
            raise ValueError(f"Provider integration {provider.npm!r} is not supported.")
        if not model.tool_call:
            raise ValueError(f"Model {model.id!r} does not support tool calls.")
    if merged.reasoning_effort:
        resolved = resolve_model(merged)
        if resolved is None:
            raise ValueError("Reasoning needs a configured model.")
        _, model = resolved
        if merged.reasoning_effort not in normalize_reasoning(model.reasoning_options):
            raise ValueError(
                f"Reasoning {merged.reasoning_effort!r} is not allowed for "
                f"model {model.id!r}."
            )
