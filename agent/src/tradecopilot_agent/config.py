"""Process configuration read from the environment."""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Configuration read from environment variables.

    Attributes:
        agent_model: ``provider:model`` string for the agent graph. Required
            before a graph can be built. A stored setting overrides it.
        model_api_key: Provider key used when no stored setting holds one.
        judge_model: ``provider:model`` string used by the evaluation judge.
            Must reference a different model family from ``agent_model``.
        db_path: SQLite file for the profile, journal, and checkpoints. Its
            parent directory is created on server startup.
        ui_dist: Directory containing the built frontend.
        host: Interface the server binds to. Loopback only by default.
        port: Port the server listens on.
        alpaca_api_key: Alpaca key id. Portfolio reads are unavailable when
            either credential is missing.
        alpaca_api_secret: Alpaca secret key.
        alpaca_base_url: Trading API base URL. The paper host selects paper
            trading in API responses.
    """

    model_config = SettingsConfigDict(
        frozen=True,
        # Process environment wins over this file; pydantic-settings orders
        # env_settings above dotenv_settings.
        env_file=_REPOSITORY_ROOT / ".env",
    )

    agent_model: str | None = None
    model_api_key: str | None = None
    judge_model: str | None = None
    db_path: Path = Path.home() / ".tradecopilot" / "data.db"
    ui_dist: Path = _REPOSITORY_ROOT / "ui" / "dist"
    host: str = "127.0.0.1"
    port: int = 8000
    alpaca_api_key: str | None = None
    alpaca_api_secret: str | None = None
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    fmp_api_key: str | None = None
    finnhub_api_key: str | None = None
    fred_api_key: str | None = None
    edgar_user_agent: str = ""

    @field_validator("db_path", "ui_dist")
    @classmethod
    def _expand_home(cls, value: Path) -> Path:
        """Expand a leading ``~`` supplied through the environment."""
        return value.expanduser()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance.

    Returns:
        Settings loaded from the current environment.
    """
    return Settings()
