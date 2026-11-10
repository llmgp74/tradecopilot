"""Settings storage and provider key routing."""

import os
from pathlib import Path

from tradecopilot_agent.models import AppSettings
from tradecopilot_agent.server.app import _apply_model_key
from tradecopilot_agent.store import Store


def test_exa_key_round_trips_through_storage(tmp_path: Path) -> None:
    """The Exa key is encrypted, stored, and returned like other secrets."""
    store = Store(tmp_path / "data.db")

    updated = store.patch_settings({"exa_api_key": "exa-secret"})

    assert updated.exa_api_key == "exa-secret"
    assert store.get_settings().exa_api_key == "exa-secret"


def test_deepseek_model_key_sets_the_deepseek_env(monkeypatch) -> None:
    """The stored key is exposed where build_chat_model reads it."""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    settings = AppSettings(
        agent_model="anthropic:deepseek-flash",
        model_api_key="stored-key",
        updated_at="2026-11-10T00:00:00Z",
    )

    _apply_model_key(settings)

    assert os.environ["DEEPSEEK_API_KEY"] == "stored-key"
