"""Tool approval policies stored in settings.

Each known tool has one policy: ``ask`` pauses the turn for a human decision
through deepagents' interrupt middleware, and ``auto`` runs without asking.
The map is keyed by the concrete tool name so a new tool starts at ``ask``
until the user opts it into auto.
"""

KNOWN_TOOLS: tuple[str, ...] = ("execute", "write_file", "edit_file", "delete")

DEFAULT_TOOL_PERMISSIONS: dict[str, str] = {
    "execute": "ask",
    "write_file": "auto",
    "edit_file": "auto",
    "delete": "auto",
}

POLICIES: frozenset[str] = frozenset({"ask", "auto"})


def normalize_tool_permissions(raw: dict[str, str] | None) -> dict[str, str]:
    """Validate a permission map and fill the tools it omits.

    Args:
        raw: Partial policy map from storage or a settings patch. ``None``
            means no overrides.

    Returns:
        A complete map covering every known tool.

    Raises:
        ValueError: When a key is not a known tool name or a value is not a
            known policy.
    """
    permissions = dict(DEFAULT_TOOL_PERMISSIONS)
    for tool, policy in (raw or {}).items():
        if tool not in KNOWN_TOOLS:
            raise ValueError(f"Unknown tool {tool!r}.")
        if policy not in POLICIES:
            raise ValueError(f"Unknown permission {policy!r}.")
        permissions[tool] = policy
    return permissions


def interrupt_on_for(permissions: dict[str, str]) -> dict[str, bool] | None:
    """Project the policy map onto deepagents ``interrupt_on``.

    Args:
        permissions: Complete policy map.

    Returns:
        Tool names set to ask, or ``None`` when every tool runs automatically.
    """
    interrupts = {tool: True for tool, policy in permissions.items() if policy == "ask"}
    return interrupts or None
