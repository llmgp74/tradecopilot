"""Tool approval policies."""

import pytest
from tradecopilot_agent.permissions import (
    DEFAULT_TOOL_PERMISSIONS,
    interrupt_on_for,
    normalize_tool_permissions,
)


def test_missing_tools_take_defaults() -> None:
    """A partial map keeps the default policy for the tools it omits."""
    assert normalize_tool_permissions({"execute": "auto"}) == {
        **DEFAULT_TOOL_PERMISSIONS,
        "execute": "auto",
    }


def test_unknown_tool_is_rejected() -> None:
    """A name that is not a known tool is refused."""
    with pytest.raises(ValueError, match="Unknown tool"):
        normalize_tool_permissions({"rm": "ask"})


def test_unknown_value_is_rejected() -> None:
    """A policy other than ask or auto is refused."""
    with pytest.raises(ValueError, match="Unknown permission"):
        normalize_tool_permissions({"execute": "never"})


def test_ask_tools_become_interrupts() -> None:
    """Only the tools set to ask need a human decision."""
    assert interrupt_on_for(DEFAULT_TOOL_PERMISSIONS) == {"execute": True}


def test_all_auto_disables_the_middleware() -> None:
    """With every tool auto, there is nothing to interrupt on."""
    permissions = {name: "auto" for name in DEFAULT_TOOL_PERMISSIONS}
    assert interrupt_on_for(permissions) is None
