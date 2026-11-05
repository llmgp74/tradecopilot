"""Contract checks for the library boundary and the server."""

import sqlite3
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from tradecopilot_agent import Settings, build_agent
from tradecopilot_agent.memory import MemoryConfig
from tradecopilot_agent.server import create_app
from tradecopilot_agent.state import ToolOutput
from tradecopilot_agent.store import Store


class EmptySource:
    """A source with no providers configured."""

    def capabilities(self) -> set[str]:
        """Return no capabilities."""
        return set()

    async def quote(self, ticker: str) -> ToolOutput:
        """Not configured."""
        raise NotImplementedError


def test_build_agent_composes_the_loop(tmp_path: Path, monkeypatch) -> None:
    """The eval contract signature builds the model and tools."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    store = Store(tmp_path / "data.db")

    graph = build_agent(
        MemoryConfig(condition="full", store=store),
        EmptySource(),
        model="deepseek:deepseek-chat",
    )

    nodes = set(graph.get_graph().nodes)
    assert {"model", "tools"} <= nodes


def test_health(tmp_path: Path) -> None:
    """The server exposes a health endpoint with the configured model."""
    settings = Settings(db_path=tmp_path / "data.db", agent_model=None)
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "agent_model": ""}


def test_checkpointer_reuses_data_database(tmp_path: Path) -> None:
    """The checkpointer creates its tables in the application database."""
    settings = Settings(db_path=tmp_path / "data.db")

    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").status_code == 200

    with sqlite3.connect(settings.db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"checkpoints", "writes"} <= tables


def test_library_root_does_not_import_fastapi() -> None:
    """Importing the library must not pull in the web stack."""
    check = (
        "import sys, tradecopilot_agent; "
        "assert 'fastapi' not in sys.modules, 'library root imports fastapi'"
    )
    subprocess.run([sys.executable, "-c", check], check=True)
