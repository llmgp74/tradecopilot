"""Reasoning option normalization and provider kwargs."""

from tradecopilot_agent.reasoning import (
    budget_for,
    normalize_reasoning,
    reasoning_kwargs,
)


def test_off_follows_none_or_toggle() -> None:
    """Off is offered only when the model declares it or has a toggle."""
    assert normalize_reasoning([{"type": "effort", "values": ["none", "low"]}]) == [
        "off",
        "low",
    ]
    assert normalize_reasoning(
        [
            {"type": "effort", "values": ["low", "max"]},
            {"type": "toggle"},
        ]
    ) == ["off", "low", "max"]
    assert normalize_reasoning([{"type": "effort", "values": ["low", "high"]}]) == [
        "low",
        "high",
    ]
    assert normalize_reasoning([{"type": "toggle"}]) == ["off", "on"]
    assert normalize_reasoning([{"type": "budget_tokens", "min": 1024}]) == [
        "off",
        "low",
        "medium",
        "high",
    ]
    assert normalize_reasoning([]) == []


def test_budget_mapping() -> None:
    """Budget levels span the declared range."""
    option = {"type": "budget_tokens", "min": 1024, "max": 8192}
    assert budget_for("low", option) == 1024
    assert budget_for("medium", option) == 4608
    assert budget_for("high", option) == 8192
    assert budget_for("high", {"min": 1024}) == 4096


def test_provider_kwargs() -> None:
    """Each integration receives its own reasoning shape."""
    effort = [{"type": "effort", "values": ["low", "medium", "high"]}]
    budget = [{"type": "budget_tokens", "min": 1024, "max": 8192}]

    assert reasoning_kwargs("openai", "medium", effort) == {
        "reasoning_effort": "medium"
    }
    assert reasoning_kwargs("openai", "off", effort) == {}
    assert reasoning_kwargs("anthropic", "high", effort) == {"reasoning_effort": "high"}
    assert reasoning_kwargs("anthropic", "high", budget) == {
        "thinking": {"type": "enabled", "budget_tokens": 8192}
    }
    assert reasoning_kwargs("google", "medium", effort) == {
        "reasoning_effort": "medium"
    }
    assert reasoning_kwargs("google", "max", effort) == {"reasoning_effort": "high"}
    assert reasoning_kwargs("anthropic", "minimal", effort) == {
        "reasoning_effort": "low"
    }
    assert reasoning_kwargs("deepseek", "off", [{"type": "toggle"}]) == {
        "thinking": {"type": "disabled"}
    }
    assert reasoning_kwargs("deepseek", "on", [{"type": "toggle"}]) == {
        "thinking": {"type": "enabled"}
    }
    assert reasoning_kwargs("openai", "", effort) == {}
