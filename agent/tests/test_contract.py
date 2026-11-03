"""Contract checks for the library boundary and the server."""

import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from tradecopilot_agent import Settings
from tradecopilot_agent.server import create_app


def test_health(tmp_path: Path) -> None:
    """The server exposes a health endpoint."""
    settings = Settings(db_path=tmp_path / "data.db")
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_library_root_does_not_import_fastapi() -> None:
    """Importing the library must not pull in the web stack."""
    check = (
        "import sys, tradecopilot_agent; "
        "assert 'fastapi' not in sys.modules, 'library root imports fastapi'"
    )
    subprocess.run([sys.executable, "-c", check], check=True)
