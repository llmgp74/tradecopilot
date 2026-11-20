"""Settings storage and provider credentials."""

import sqlite3
from pathlib import Path

import pytest
from tradecopilot_agent.models import ProviderCredential, ProviderModel
from tradecopilot_agent.store import Store


def test_exa_key_round_trips_through_storage(tmp_path: Path) -> None:
    """The Exa key is encrypted, stored, and returned like other secrets."""
    store = Store(tmp_path / "data.db")

    updated = store.patch_settings({"exa_api_key": "exa-secret"})

    assert updated.exa_api_key == "exa-secret"
    assert store.get_settings().exa_api_key == "exa-secret"


def test_provider_round_trips_and_encrypts_key(tmp_path: Path) -> None:
    """A provider row returns the key and stores it encrypted."""
    store = Store(tmp_path / "data.db")
    updated = store.upsert_provider(
        ProviderCredential(
            provider_id="openai",
            api_key="sk-secret",
            base_url="",
            npm="@ai-sdk/openai",
            models=[ProviderModel(id="gpt-5", name="GPT-5")],
        )
    )

    assert updated.api_key == "sk-secret"
    stored = store.get_provider("openai")
    assert stored is not None
    assert stored.models[0].id == "gpt-5"

    connection = sqlite3.connect(tmp_path / "data.db")
    raw = connection.execute(
        "SELECT api_key FROM provider_credentials WHERE provider_id = 'openai'"
    ).fetchone()[0]
    connection.close()
    assert raw != "sk-secret"


def test_old_schema_fails_with_a_clear_error(tmp_path: Path) -> None:
    """A database from the previous schema is reported, not migrated."""
    path = tmp_path / "data.db"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE settings "
        "(id INTEGER PRIMARY KEY, agent_model TEXT, updated_at TEXT)"
    )
    connection.commit()
    connection.close()

    with pytest.raises(RuntimeError, match="delete"):
        Store(path)


def test_upsert_provider_moves_selection_when_model_removed(tmp_path: Path) -> None:
    """Removing the selected model falls back to the first remaining one."""
    store = Store(tmp_path / "data.db")
    store.upsert_provider(
        ProviderCredential(
            provider_id="openai",
            api_key="k",
            npm="@ai-sdk/openai",
            models=[ProviderModel(id="gpt-5", name="GPT-5")],
        )
    )
    store.patch_settings({"model_provider": "openai", "model_id": "gpt-5"})

    store.upsert_provider(
        ProviderCredential(
            provider_id="openai",
            api_key="k",
            npm="@ai-sdk/openai",
            models=[ProviderModel(id="gpt-4", name="GPT-4")],
        )
    )

    settings = store.get_settings()
    assert settings.model_provider == "openai"
    assert settings.model_id == "gpt-4"


def test_get_settings_defaults_to_the_first_configured_model(tmp_path: Path) -> None:
    """Without a selection, the first usable model is reported."""
    store = Store(tmp_path / "data.db")
    store.upsert_provider(
        ProviderCredential(
            provider_id="openai",
            api_key="k",
            npm="@ai-sdk/openai",
            models=[ProviderModel(id="gpt-5", name="GPT-5")],
        )
    )

    settings = store.get_settings()

    assert settings.model_provider == "openai"
    assert settings.model_id == "gpt-5"


def test_get_settings_skips_providers_without_a_key(tmp_path: Path) -> None:
    """A provider with no key cannot supply the default model."""
    store = Store(tmp_path / "data.db")
    store.upsert_provider(
        ProviderCredential(
            provider_id="anthropic",
            api_key="",
            npm="@ai-sdk/anthropic",
            models=[ProviderModel(id="claude-sonnet-5", name="Claude Sonnet 5")],
        )
    )
    store.upsert_provider(
        ProviderCredential(
            provider_id="openai",
            api_key="k",
            npm="@ai-sdk/openai",
            models=[ProviderModel(id="gpt-5", name="GPT-5")],
        )
    )

    settings = store.get_settings()

    assert settings.model_provider == "openai"
    assert settings.model_id == "gpt-5"


def test_get_settings_keeps_an_explicit_selection(tmp_path: Path) -> None:
    """A stored selection wins over the default."""
    store = Store(tmp_path / "data.db")
    store.upsert_provider(
        ProviderCredential(
            provider_id="openai",
            api_key="k",
            npm="@ai-sdk/openai",
            models=[
                ProviderModel(id="gpt-5", name="GPT-5"),
                ProviderModel(id="gpt-4", name="GPT-4"),
            ],
        )
    )
    store.patch_settings({"model_provider": "openai", "model_id": "gpt-4"})

    settings = store.get_settings()

    assert settings.model_id == "gpt-4"


def test_delete_provider_clears_selection(tmp_path: Path) -> None:
    """Deleting the provider clears the selection that pointed at it."""
    store = Store(tmp_path / "data.db")
    store.upsert_provider(
        ProviderCredential(
            provider_id="openai",
            api_key="k",
            npm="@ai-sdk/openai",
            models=[ProviderModel(id="gpt-5", name="GPT-5")],
        )
    )
    store.patch_settings({"model_provider": "openai", "model_id": "gpt-5"})

    store.delete_provider("openai")

    assert store.get_settings().model_provider == ""
    assert store.list_providers() == []


def test_upsert_provider_clears_selection_when_key_cleared(tmp_path: Path) -> None:
    """Clearing the key disables the provider and drops its selection."""
    store = Store(tmp_path / "data.db")
    credential = ProviderCredential(
        provider_id="openai",
        api_key="k",
        npm="@ai-sdk/openai",
        models=[ProviderModel(id="gpt-5", name="GPT-5")],
    )
    store.upsert_provider(credential)
    store.patch_settings({"model_provider": "openai", "model_id": "gpt-5"})

    store.upsert_provider(
        ProviderCredential(
            provider_id="openai",
            api_key="",
            npm="@ai-sdk/openai",
            models=[ProviderModel(id="gpt-5", name="GPT-5")],
        )
    )

    settings = store.get_settings()
    assert settings.model_provider == ""
    assert settings.model_id == ""


def test_tool_permissions_roundtrip(tmp_path: Path) -> None:
    """The permission map is stored as JSON and returned as a full map."""
    store = Store(tmp_path / "data.db")

    updated = store.patch_settings({"tool_permissions": {"execute": "auto"}})

    assert updated.tool_permissions["execute"] == "auto"
    assert updated.tool_permissions["write_file"] == "auto"
    assert store.get_settings().tool_permissions["execute"] == "auto"


def test_old_database_gains_tool_permissions(tmp_path: Path) -> None:
    """A database from before the column migrates on open."""
    path = tmp_path / "data.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE settings (id INTEGER PRIMARY KEY CHECK (id = 1), "
            "model_provider TEXT NOT NULL DEFAULT '', "
            "model_id TEXT NOT NULL DEFAULT '', "
            "reasoning_effort TEXT NOT NULL DEFAULT '', "
            "alpaca_api_key TEXT NOT NULL DEFAULT '', "
            "alpaca_api_secret TEXT NOT NULL DEFAULT '', "
            "alpaca_base_url TEXT NOT NULL DEFAULT '', "
            "fmp_api_key TEXT NOT NULL DEFAULT '', "
            "finnhub_api_key TEXT NOT NULL DEFAULT '', "
            "fred_api_key TEXT NOT NULL DEFAULT '', "
            "edgar_user_agent TEXT NOT NULL DEFAULT '', "
            "exa_api_key TEXT NOT NULL DEFAULT '', "
            "updated_at TEXT NOT NULL)"
        )
        connection.execute("INSERT INTO settings (id, updated_at) VALUES (1, 'now')")

    store = Store(path)

    assert store.get_settings().tool_permissions["execute"] == "ask"
