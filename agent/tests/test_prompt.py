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
