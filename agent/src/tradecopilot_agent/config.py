"""Process configuration read from the environment."""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Configuration read from environment variables.

    Credentials do not come from the environment. They are entered in the app
    and stored in SQLite.

    Attributes:
        db_path: SQLite file for settings, threads, and checkpoints. Its
            parent directory is created on server startup.
        ui_dist: Directory containing the built frontend.
        host: Interface the server binds to. Loopback only by default.
        port: Port the server listens on.
    """

    model_config = SettingsConfigDict(
        frozen=True,
        # Process environment wins over this file; pydantic-settings orders
        # env_settings above dotenv_settings.
        env_file=_REPOSITORY_ROOT / ".env",
    )

    db_path: Path = Path.home() / ".tradecopilot" / "data.db"
    ui_dist: Path = _REPOSITORY_ROOT / "ui" / "dist"
    host: str = "127.0.0.1"
    port: int = 8000

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
