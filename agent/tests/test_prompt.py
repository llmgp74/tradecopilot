"""The system prompt states the current clock instead of guessing."""

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from tradecopilot_agent import agent as agent_module
from tradecopilot_agent.memory import MemoryConfig
from tradecopilot_agent.prompt import build_system_prompt
from tradecopilot_agent.store import Store


def test_prompt_states_the_clock_and_the_market_zone() -> None:
    """Both the reader's clock and the exchange clock are explicit."""
    now = datetime(2026, 11, 20, 14, 30, tzinfo=timezone(timedelta(hours=8)))

    prompt = build_system_prompt(now)

    assert "Friday, November 20, 2026" in prompt
    assert "14:30" in prompt
    assert "New York" in prompt
    assert "01:30" in prompt


def test_build_agent_uses_the_decision_clock(tmp_path: Path) -> None:
    """An evaluation run shows the scenario time, never the wall clock."""
    now = datetime(2026, 11, 20, 14, 0, tzinfo=UTC)
    captured: dict[str, object] = {}

    def fake_create(**kwargs: object) -> MagicMock:
        captured.update(kwargs)
        return MagicMock()

    with (
        patch.object(agent_module, "create_deep_agent", side_effect=fake_create),
        patch.object(agent_module, "build_chat_model", return_value=MagicMock()),
    ):
        agent_module.build_agent(
            MemoryConfig(condition="full", store=Store(tmp_path / "data.db")),
            MagicMock(capabilities=lambda: set()),
            decision_time=now,
            model="deepseek:deepseek-chat",
        )

    prompt = str(captured["system_prompt"])
    assert "Friday, November 20, 2026" in prompt
    assert f"{now.astimezone():%H:%M}" in prompt
    assert "09:00 -0500" in prompt


def test_workspace_section_names_both_path_forms() -> None:
    """File tools use a virtual root; the shell uses relative paths."""
    prompt = build_system_prompt(
        datetime(2026, 11, 20, tzinfo=UTC),
        workspace="/home/u/.tradecopilot/workspace",
    )

    assert "uploads/" in prompt
    assert "working directory" in prompt
    assert "python" in prompt
    assert "/home/u/.tradecopilot/workspace" not in prompt


def test_no_workspace_section_without_a_root() -> None:
    """Evaluation runs keep the prompt they had before."""
    prompt = build_system_prompt(datetime(2026, 11, 20, tzinfo=UTC))

    assert "Attachments are stored" not in prompt


def test_build_agent_maps_permissions_to_interrupts(tmp_path: Path) -> None:
    """Ask tools become interrupts; auto tools stay silent."""
    captured: dict[str, object] = {}

    def fake_create(**kwargs: object) -> MagicMock:
        captured.update(kwargs)
        return MagicMock()

    with (
        patch.object(agent_module, "create_deep_agent", side_effect=fake_create),
        patch.object(agent_module, "build_chat_model", return_value=MagicMock()),
    ):
        agent_module.build_agent(
            MemoryConfig(condition="full", store=Store(tmp_path / "data.db")),
            MagicMock(capabilities=lambda: set()),
            model="deepseek:deepseek-chat",
            tool_permissions={
                "execute": "ask",
                "write_file": "auto",
                "edit_file": "auto",
                "delete": "auto",
            },
            backend=MagicMock(),
            workspace="/w",
        )

    assert captured["backend"] is not None
    assert captured["interrupt_on"] == {"execute": True}


def test_build_agent_defaults_keep_the_state_backend(tmp_path: Path) -> None:
    """Callers that pass nothing, such as the evaluation harness, are unchanged."""
    captured: dict[str, object] = {}

    def fake_create(**kwargs: object) -> MagicMock:
        captured.update(kwargs)
        return MagicMock()

    with (
        patch.object(agent_module, "create_deep_agent", side_effect=fake_create),
        patch.object(agent_module, "build_chat_model", return_value=MagicMock()),
    ):
        agent_module.build_agent(
            MemoryConfig(condition="full", store=Store(tmp_path / "data.db")),
            MagicMock(capabilities=lambda: set()),
            model="deepseek:deepseek-chat",
        )

    assert captured["backend"] is None
    assert captured["interrupt_on"] is None


def test_build_agent_with_every_tool_auto_adds_no_interrupts(tmp_path: Path) -> None:
    """Auto for every tool means no human-in-the-loop middleware."""
    captured: dict[str, object] = {}

    def fake_create(**kwargs: object) -> MagicMock:
        captured.update(kwargs)
        return MagicMock()

    with (
        patch.object(agent_module, "create_deep_agent", side_effect=fake_create),
        patch.object(agent_module, "build_chat_model", return_value=MagicMock()),
    ):
        agent_module.build_agent(
            MemoryConfig(condition="full", store=Store(tmp_path / "data.db")),
            MagicMock(capabilities=lambda: set()),
            model="deepseek:deepseek-chat",
            tool_permissions={
                "execute": "auto",
                "write_file": "auto",
                "edit_file": "auto",
                "delete": "auto",
            },
            backend=MagicMock(),
            workspace="/w",
        )

    assert captured["interrupt_on"] is None
