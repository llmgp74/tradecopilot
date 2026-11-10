"""Tests for the desktop entrypoint."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from tradecopilot_agent import Settings, desktop
from tradecopilot_agent.server import create_app


def test_listening_line_is_compact_json() -> None:
    assert desktop.listening_line(51234) == '{"event": "listening", "port": 51234}'


def test_server_binds_an_ephemeral_loopback_port() -> None:
    server = desktop.create_server()
    assert server.config.host == "127.0.0.1"
    assert server.config.port == 0


TAURI_ORIGINS = ["tauri://localhost", "http://tauri.localhost"]


def _app(tmp_path: Path) -> FastAPI:
    return create_app(Settings(db_path=tmp_path / "data.db"))


def test_health_allows_each_desktop_origin(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        for origin in TAURI_ORIGINS:
            response = client.get("/api/health", headers={"Origin": origin})
            assert response.status_code == 200
            assert response.headers["access-control-allow-origin"] == origin


def test_chat_preflight_is_allowed(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        for origin in TAURI_ORIGINS:
            response = client.options(
                "/api/chat",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
            assert response.status_code == 200
            assert response.headers["access-control-allow-origin"] == origin
