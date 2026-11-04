"""SQLite storage for threads, the user profile, and the decision journal.

One connection is opened per operation. SQLite is local and the workload is a
single user, so connection setup cost is irrelevant and per-call connections
avoid sharing one connection across FastAPI's worker threads.
"""

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from tradecopilot_agent.models import AppSettings
from tradecopilot_agent.secrets import SecretBox

_SCHEMA = """
CREATE TABLE IF NOT EXISTS threads (
  thread_id  TEXT PRIMARY KEY,
  title      TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS threads_updated ON threads (updated_at DESC);

CREATE TABLE IF NOT EXISTS profile (
  id         INTEGER PRIMARY KEY CHECK (id = 1),
  data       TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
  id                INTEGER PRIMARY KEY CHECK (id = 1),
  agent_model       TEXT NOT NULL DEFAULT '',
  model_api_key     TEXT NOT NULL DEFAULT '',
  alpaca_api_key    TEXT NOT NULL DEFAULT '',
  alpaca_api_secret TEXT NOT NULL DEFAULT '',
  alpaca_base_url   TEXT NOT NULL DEFAULT '',
  updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS journal (
  id               TEXT PRIMARY KEY,
  created_at       TEXT NOT NULL,
  tickers          TEXT NOT NULL,
  side             TEXT NOT NULL,
  qty              REAL NOT NULL,
  size_pct         REAL NOT NULL,
  thesis           TEXT NOT NULL,
  evidence_ids     TEXT NOT NULL,
  status           TEXT NOT NULL,
  user_action      TEXT,
  rejection_reason TEXT,
  fill_price       REAL,
  fill_at          TEXT,
  outcome_note     TEXT
);
CREATE INDEX IF NOT EXISTS journal_created ON journal (created_at DESC);
"""

_SECRET_FIELDS = frozenset({"model_api_key", "alpaca_api_key", "alpaca_api_secret"})
_SETTINGS_COLUMNS = (
    "agent_model",
    "model_api_key",
    "alpaca_api_key",
    "alpaca_api_secret",
    "alpaca_base_url",
)

DEFAULT_PROFILE: dict[str, Any] = {
    "risk_band": "moderate",
    "position_cap_pct": 10.0,
    "sector_exclusions": [],
    "horizon": "weeks",
    "watchlist": [],
    "source_preferences": [],
    "execution": {"autonomous": False, "max_order_notional": 1000.0},
}


def now_iso() -> str:
    """Return the current UTC time as an RFC 3339 string.

    Returns:
        The timestamp, for example ``2026-11-05T03:00:12Z``.
    """
    return datetime.now(tz=UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class ThreadRecord:
    """One row of the thread index."""

    thread_id: str
    title: str
    created_at: str
    updated_at: str


class Store:
    """Thread, profile, and journal storage backed by the application database."""

    def __init__(self, path: Path) -> None:
        """Open the database schema and seed the default profile.

        Args:
            path: SQLite database file. Its parent must exist.
        """
        self.path = path
        with self._connection() as connection:
            connection.executescript(_SCHEMA)
        os.chmod(path, 0o600)
        self._secrets = SecretBox(path.parent / "settings.key")
        self._seed_profile()
        self._seed_settings()

    def _seed_settings(self) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO settings (id, updated_at) VALUES (1, ?)",
                (now_iso(),),
            )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _seed_profile(self) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO profile (id, data, updated_at) VALUES (1, ?, ?)",
                (json.dumps(DEFAULT_PROFILE), now_iso()),
            )

    def upsert_thread(self, thread_id: str, title: str) -> None:
        """Insert a thread or refresh its update time.

        Args:
            thread_id: Conversation thread id.
            title: Title used only when the thread is created.
        """
        timestamp = now_iso()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO threads (thread_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (thread_id) DO UPDATE SET updated_at = excluded.updated_at
                """,
                (thread_id, title, timestamp, timestamp),
            )

    def get_settings(self) -> AppSettings:
        """Return the stored settings with secrets decrypted.

        Returns:
            The stored settings. Fields without a stored value are empty.
        """
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT agent_model, model_api_key, alpaca_api_key,
                       alpaca_api_secret, alpaca_base_url, updated_at
                FROM settings WHERE id = 1
                """
            ).fetchone()
        if row is None:
            return AppSettings(updated_at=now_iso())
        return AppSettings(
            agent_model=str(row[0]),
            model_api_key=self._secrets.decrypt(str(row[1])),
            alpaca_api_key=self._secrets.decrypt(str(row[2])),
            alpaca_api_secret=self._secrets.decrypt(str(row[3])),
            alpaca_base_url=str(row[4]),
            updated_at=str(row[5]),
        )

    def patch_settings(self, changes: dict[str, Any]) -> AppSettings:
        """Apply validated changes to the stored settings.

        Args:
            changes: Field values to store. An empty string clears a field.
                Secret fields are encrypted before writing.

        Returns:
            The stored settings after the update.
        """
        updates = [
            (name, value)
            for name, value in changes.items()
            if name in _SETTINGS_COLUMNS
        ]
        assignments = ", ".join(f"{name} = ?" for name, _ in updates)
        params = [
            self._secrets.encrypt(str(value)) if name in _SECRET_FIELDS else str(value)
            for name, value in updates
        ]
        with self._connection() as connection:
            connection.execute(
                f"UPDATE settings SET {assignments}, updated_at = ? WHERE id = 1",
                (*params, now_iso()),
            )
        return self.get_settings()

    def list_threads(
        self, page_no: int, page_size: int
    ) -> tuple[list[ThreadRecord], int]:
        """Return one page of threads, newest first.

        Args:
            page_no: One-based page number.
            page_size: Rows per page.

        Returns:
            The rows on the page and the total row count.
        """
        offset = (page_no - 1) * page_size
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT thread_id, title, created_at, updated_at
                FROM threads ORDER BY updated_at DESC LIMIT ? OFFSET ?
                """,
                (page_size, offset),
            ).fetchall()
            total = connection.execute("SELECT COUNT(*) FROM threads").fetchone()
        records = [
            ThreadRecord(
                thread_id=str(row[0]),
                title=str(row[1]),
                created_at=str(row[2]),
                updated_at=str(row[3]),
            )
            for row in rows
        ]
        return records, int(total[0]) if total is not None else 0

    def get_thread(self, thread_id: str) -> ThreadRecord | None:
        """Return a thread row by id.

        Args:
            thread_id: Conversation thread id.

        Returns:
            The row, or ``None`` when it does not exist.
        """
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT thread_id, title, created_at, updated_at
                FROM threads WHERE thread_id = ?
                """,
                (thread_id,),
            ).fetchone()
        if row is None:
            return None
        return ThreadRecord(
            thread_id=str(row[0]),
            title=str(row[1]),
            created_at=str(row[2]),
            updated_at=str(row[3]),
        )

    def get_profile(self) -> dict[str, Any]:
        """Return the full profile including its update time.

        Returns:
            The stored profile.
        """
        with self._connection() as connection:
            row = connection.execute(
                "SELECT data, updated_at FROM profile WHERE id = 1"
            ).fetchone()
        if row is None:
            return {**deepcopy(DEFAULT_PROFILE), "updated_at": now_iso()}
        data: dict[str, Any] = json.loads(str(row[0]))
        data["updated_at"] = str(row[1])
        return data

    def patch_profile(self, changes: dict[str, Any]) -> dict[str, Any]:
        """Apply validated changes to the stored profile.

        Args:
            changes: Fields to merge. ``execution`` replaces the whole object.

        Returns:
            The full profile after the update.
        """
        profile = self.get_profile()
        profile.pop("updated_at", None)
        profile.update(changes)
        timestamp = now_iso()
        with self._connection() as connection:
            connection.execute(
                "UPDATE profile SET data = ?, updated_at = ? WHERE id = 1",
                (json.dumps(profile), timestamp),
            )
        profile["updated_at"] = timestamp
        return profile

    def list_journal(
        self,
        *,
        page_no: int,
        page_size: int,
        status: str | None = None,
        ticker: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return one page of journal rows, newest first.

        Args:
            page_no: One-based page number.
            page_size: Rows per page.
            status: Exact status filter.
            ticker: Case-insensitive ticker filter.
            from_date: Inclusive lower bound on the creation date.
            to_date: Inclusive upper bound on the creation date.

        Returns:
            The rows on the page and the total matching row count.
        """
        clauses: list[str] = []
        params: list[Any] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if ticker is not None:
            clauses.append(
                "EXISTS (SELECT 1 FROM json_each(tickers) "
                "WHERE UPPER(json_each.value) = UPPER(?))"
            )
            params.append(ticker)
        if from_date is not None:
            clauses.append("created_at >= ?")
            params.append(from_date.isoformat())
        if to_date is not None:
            clauses.append("created_at < ?")
            params.append((to_date + timedelta(days=1)).isoformat())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        offset = (page_no - 1) * page_size
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT id, created_at, tickers, side, qty, size_pct, thesis,
                       evidence_ids, status, user_action, rejection_reason,
                       fill_price, fill_at
                FROM journal {where} ORDER BY created_at DESC LIMIT ? OFFSET ?
                """,
                (*params, page_size, offset),
            ).fetchall()
            total = connection.execute(
                f"SELECT COUNT(*) FROM journal {where}", params
            ).fetchone()
        entries = [_journal_row(row) for row in rows]
        return entries, int(total[0]) if total is not None else 0


def _journal_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": str(row[0]),
        "created_at": str(row[1]),
        "tickers": json.loads(str(row[2])),
        "side": str(row[3]),
        "qty": float(row[4]),
        "size_pct": float(row[5]),
        "thesis": str(row[6]),
        "evidence_ids": json.loads(str(row[7])),
        "status": str(row[8]),
        "user_action": row[9],
        "rejection_reason": row[10],
        "fill_price": row[11],
        "fill_at": row[12],
        "outcome": None,
    }
