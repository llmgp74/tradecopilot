from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from tradecopilot_agent.config import Settings, get_settings


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Prepare storage before serving requests.

    Args:
        app: Application whose state holds the settings.

    Yields:
        Control back to the server for the lifetime of the process.
    """
    settings: Settings = app.state.settings
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the server application.

    Args:
        settings: Configuration override. Environment settings when omitted.

    Returns:
        The configured application.
    """
    app = FastAPI(title="TradeCopilot", lifespan=_lifespan)
    app.state.settings = settings or get_settings()

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        """Report that the server is running.

        Returns:
            A fixed status payload.
        """
        return {"status": "ok"}

    _mount_ui(app)
    return app


def _mount_ui(app: FastAPI) -> None:
    """Serve the built frontend when it is present.

    Args:
        app: Application to mount the frontend on.
    """
    ui_dist: Path = app.state.settings.ui_dist
    if ui_dist.is_dir():
        app.mount("/", StaticFiles(directory=ui_dist, html=True), name="ui")
        return

    @app.get("/", response_class=HTMLResponse)
    async def missing_ui() -> str:
        """Explain how to produce the missing frontend build.

        Returns:
            A short HTML hint.
        """
        return (
            "<p>UI build not found. Build the frontend under "
            "<code>ui/</code> first.</p>"
        )
