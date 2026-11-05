"""Decision journal storage and settings round-trip."""

import json
import sqlite3
from pathlib import Path

from tradecopilot_agent.store import Store


def _event(
    decision_id: str,
    *,
    created_at: str,
    status: str = "proposed",
    legs: list[dict] | None = None,
) -> dict:
    return {
        "decision_id": decision_id,
        "created_at": created_at,
        "legs": legs
        or [
            {
                "ticker": "NVDA",
                "side": "buy",
                "qty": 10.0,
                "notional": 1000.0,
                "fill_price": None,
                "fill_at": None,
                "status": status,
            }
        ],
        "thesis": "test thesis",
        "horizon": "weeks",
        "evidence_ids": ["ev_1"],
        "status": status,
        "user_action": None,
        "rejection_reason": None,
    }


def _store(tmp_path: Path) -> Store:
    return Store(tmp_path / "data.db")


def test_journal_returns_the_newest_event_per_decision(tmp_path: Path) -> None:
    """A decision is appended many times and read once, with its last state."""
    store = _store(tmp_path)
    store.append_journal(_event("d1", created_at="2026-11-01T10:00:00Z"))
    store.append_journal(
        _event("d1", created_at="2026-11-01T10:05:00Z", status="approved")
    )
    store.append_journal(_event("d2", created_at="2026-11-02T10:00:00Z"))

    rows, total = store.list_journal(page_no=1, page_size=10)

    assert total == 2
    by_id = {row["id"]: row for row in rows}
    assert by_id["d1"]["status"] == "approved"
    assert by_id["d1"]["legs"][0]["ticker"] == "NVDA"
    assert by_id["d2"]["status"] == "proposed"


def test_journal_filters_match_any_leg(tmp_path: Path) -> None:
    """The ticker filter matches when any leg carries the ticker."""
    store = _store(tmp_path)
    store.append_journal(
        _event(
            "d1",
            created_at="2026-11-01T10:00:00Z",
            legs=[
                {
                    "ticker": "NVDA",
                    "side": "sell",
                    "qty": 10.0,
                    "notional": 1000.0,
                    "fill_price": None,
                    "fill_at": None,
                    "status": "proposed",
                },
                {
                    "ticker": "AAPL",
                    "side": "buy",
                    "qty": 5.0,
                    "notional": 500.0,
                    "fill_price": None,
                    "fill_at": None,
                    "status": "proposed",
                },
            ],
        )
    )

    assert store.list_journal(page_no=1, page_size=10, ticker="aapl")[1] == 1
    assert store.list_journal(page_no=1, page_size=10, ticker="msft")[1] == 0
    assert store.list_journal(page_no=1, page_size=10, status="proposed")[1] == 1


def test_new_settings_round_trip_and_encrypt(tmp_path: Path) -> None:
    """Provider keys are encrypted; the EDGAR agent is plain text."""
    store = _store(tmp_path)
    store.patch_settings(
        {
            "fmp_api_key": "fmp-secret",
            "finnhub_api_key": "finnhub-secret",
            "fred_api_key": "fred-secret",
            "edgar_user_agent": "TradeCopilot you@example.com",
        }
    )

    settings = store.get_settings()
    assert settings.fmp_api_key == "fmp-secret"
    assert settings.finnhub_api_key == "finnhub-secret"
    assert settings.fred_api_key == "fred-secret"
    assert settings.edgar_user_agent == "TradeCopilot you@example.com"

    with sqlite3.connect(tmp_path / "data.db") as connection:
        row = connection.execute(
            "SELECT fmp_api_key, finnhub_api_key, fred_api_key, edgar_user_agent "
            "FROM settings WHERE id = 1"
        ).fetchone()

    assert row is not None
    for encrypted in row[:3]:
        assert "secret" not in encrypted
        assert encrypted.startswith("gAAAA")
    assert row[3] == "TradeCopilot you@example.com"


def test_journal_persists_payload_json(tmp_path: Path) -> None:
    """The stored event is a self-contained snapshot."""
    store = _store(tmp_path)
    store.append_journal(_event("d1", created_at="2026-11-01T10:00:00Z"))

    with sqlite3.connect(tmp_path / "data.db") as connection:
        payload = connection.execute("SELECT payload FROM journal").fetchone()[0]

    decoded = json.loads(payload)
    assert decoded["decision_id"] == "d1"
    assert decoded["legs"][0]["qty"] == 10.0
