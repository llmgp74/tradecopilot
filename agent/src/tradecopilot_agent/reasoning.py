"""Reasoning option normalization and provider-specific request kwargs.

The catalog describes reasoning with three option shapes: effort levels, a
toggle, or a token budget. This module flattens them to one list for the UI and
translates a chosen value to the keyword each LangChain integration accepts.
"""

from typing import Any

_ANTHROPIC_EFFORT = frozenset({"max", "xhigh", "high", "medium", "low"})
_GOOGLE_EFFORT = frozenset({"minimal", "low", "medium", "high"})
_OPENROUTER_EFFORT = frozenset({"minimal", "low", "medium", "high"})


def _effort_option(options: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the effort option, when present.

    Args:
        options: Catalog reasoning options.

    Returns:
        The effort option, or None.
    """
    return next((item for item in options if item.get("type") == "effort"), None)


def _budget_option(options: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the budget option, when present.

    Args:
        options: Catalog reasoning options.

    Returns:
        The budget option, or None.
    """
    return next((item for item in options if item.get("type") == "budget_tokens"), None)


def normalize_reasoning(options: list[dict[str, Any]]) -> list[str]:
    """Flatten catalog options to the composer's choice list.

    Args:
        options: Catalog reasoning options for one model.

    Returns:
        ``off`` when the model supports it, then effort values in catalog
        order, or ``on`` for toggle-only models, or the three budget levels.
    """
    effort = _effort_option(options)
    has_toggle = any(item.get("type") == "toggle" for item in options)
    if effort is not None:
        values = [str(value) for value in effort.get("values", []) if value != "none"]
        allow_off = has_toggle or "none" in effort.get("values", [])
        return (["off"] if allow_off else []) + values
    if has_toggle:
        return ["off", "on"]
    if _budget_option(options) is not None:
        return ["off", "low", "medium", "high"]
    return []


def budget_for(value: str, option: dict[str, Any]) -> int:
    """Map a level to a token budget inside the model's range.

    Args:
        value: ``low``, ``medium``, or ``high``.
        option: Budget option with ``min`` and optional ``max``.

    Returns:
        The token count. A missing maximum is four times the minimum.
    """
    minimum = int(option.get("min", 1024))
    maximum = int(option.get("max", minimum * 4))
    if value == "low":
        return minimum
    if value == "high":
        return maximum
    return (minimum + maximum) // 2


def _clamp_effort(value: str, allowed: frozenset[str]) -> str:
    """Move a value into an integration's accepted levels.

    Args:
        value: Chosen level.
        allowed: Levels the integration accepts.

    Returns:
        The value, or the nearest accepted level.
    """
    if value in allowed:
        return value
    if value in {"max", "xhigh"}:
        return "high"
    return "low"


def openrouter_kwargs(value: str, options: list[dict[str, Any]]) -> dict[str, Any]:
    """Translate a choice to OpenRouter's ``reasoning`` request object.

    OpenRouter normalizes reasoning across providers, so one object covers
    every model on the service: ``enabled`` turns thinking on or off, and
    ``effort`` or ``max_tokens`` sets how much thinking is allowed.

    Args:
        value: Normalized choice, empty for the provider default.
        options: Catalog reasoning options for the selected model.

    Returns:
        Keyword arguments for the chat model constructor.
    """
    if not value:
        return {}
    if value == "off":
        return {"reasoning": {"enabled": False}}
    if value == "on":
        return {"reasoning": {"enabled": True}}
    if _effort_option(options) is None and _budget_option(options) is not None:
        budget = _budget_option(options)
        assert budget is not None
        return {"reasoning": {"max_tokens": budget_for(value, budget)}}
    return {"reasoning": {"effort": _clamp_effort(value, _OPENROUTER_EFFORT)}}


def reasoning_kwargs(
    integration: str, value: str, options: list[dict[str, Any]]
) -> dict[str, Any]:
    """Translate a chosen value to request keyword arguments.

    Args:
        integration: ``openai``, ``anthropic``, ``google``, or ``deepseek``.
        value: Normalized choice, empty for the provider default.
        options: Catalog reasoning options for the selected model.

    Returns:
        Keyword arguments for the chat model constructor.
    """
    if not value:
        return {}
    if value == "off":
        if integration == "deepseek":
            return {"thinking": {"type": "disabled"}}
        if integration == "anthropic":
            return {"thinking": {"type": "disabled"}}
        if integration == "google":
            return {"thinking_budget": 0}
        return {}
    if value == "on":
        if integration == "deepseek":
            return {"thinking": {"type": "enabled"}}
        return {}
    if integration == "deepseek":
        return {"thinking": {"type": "enabled"}}
    if integration == "anthropic":
        if _effort_option(options) is not None:
            return {"reasoning_effort": _clamp_effort(value, _ANTHROPIC_EFFORT)}
        budget = _budget_option(options)
        if budget is not None:
            return {
                "thinking": {
                    "type": "enabled",
                    "budget_tokens": budget_for(value, budget),
                }
            }
        return {}
    if integration == "google":
        if _effort_option(options) is not None:
            return {"reasoning_effort": _clamp_effort(value, _GOOGLE_EFFORT)}
        budget = _budget_option(options)
        if budget is not None:
            return {"thinking_budget": budget_for(value, budget)}
        return {}
    return {"reasoning_effort": value}
