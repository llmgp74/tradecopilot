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
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

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
  fmp_api_key       TEXT NOT NULL DEFAULT '',
  finnhub_api_key   TEXT NOT NULL DEFAULT '',
  fred_api_key      TEXT NOT NULL DEFAULT '',
  edgar_user_agent  TEXT NOT NULL DEFAULT '',
  exa_api_key       TEXT NOT NULL DEFAULT '',
  updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS journal (
  event_id    TEXT PRIMARY KEY,
  decision_id TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  payload     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS journal_decision ON journal (decision_id, created_at DESC);
CREATE INDEX IF NOT EXISTS journal_created ON journal (created_at DESC);
"""

_SECRET_FIELDS = frozenset(
    {
        "model_api_key",
        "alpaca_api_key",
        "alpaca_api_secret",
        "fmp_api_key",
        "finnhub_api_key",
        "fred_api_key",
        "exa_api_key",
    }
)
_SETTINGS_COLUMNS = (
    "agent_model",
    "model_api_key",
    "alpaca_api_key",
    "alpaca_api_secret",
    "alpaca_base_url",
    "fmp_api_key",
    "finnhub_api_key",
    "fred_api_key",
    "edgar_user_agent",
    "exa_api_key",
)
_SETTINGS_SELECT = (
    "agent_model, model_api_key, alpaca_api_key, alpaca_api_secret, "
    "alpaca_base_url, fmp_api_key, finnhub_api_key, fred_api_key, "
    "edgar_user_agent, exa_api_key, updated_at"
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
        # The checkpointer shares this database. Wait for its short writes
        # instead of failing with "database is locked".
        connection.execute("PRAGMA busy_timeout=5000")
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
                f"SELECT {_SETTINGS_SELECT} FROM settings WHERE id = 1"
            ).fetchone()
        if row is None:
            return AppSettings(updated_at=now_iso())
        return AppSettings(
            agent_model=str(row[0]),
            model_api_key=self._secrets.decrypt(str(row[1])),
            alpaca_api_key=self._secrets.decrypt(str(row[2])),
            alpaca_api_secret=self._secrets.decrypt(str(row[3])),
            alpaca_base_url=str(row[4]),
            fmp_api_key=self._secrets.decrypt(str(row[5])),
            finnhub_api_key=self._secrets.decrypt(str(row[6])),
            fred_api_key=self._secrets.decrypt(str(row[7])),
            edgar_user_agent=str(row[8]),
            exa_api_key=self._secrets.decrypt(str(row[9])),
            updated_at=str(row[10]),
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

    def recent_journal(
        self,
        tickers: list[str],
        since: str,
        limit: int = 10,
        *,
        until: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return recent decisions overlapping any of the tickers.

        Args:
            tickers: Tickers to match against the legs.
            since: Inclusive lower creation date, or an aware timestamp when
                ``until`` is provided.
            limit: Maximum decisions to return.
            until: Inclusive aware timestamp for historical retrieval. Events
                after it are excluded before selecting a decision snapshot.

        Returns:
            Decisions, newest first.

        Raises:
            ValueError: Historical bounds are invalid or lack a timezone.
        """
        wanted = {ticker.upper() for ticker in tickers}
        if until is None:
            rows, _ = self.list_journal(page_no=1, page_size=1000)
            rows = [row for row in rows if row.get("created_at", "")[:10] >= since[:10]]
        else:
            rows = self._journal_in_window(since, until)
        return [
            row
            for row in rows
            if any(
                str(leg.get("ticker", "")).upper() in wanted
                for leg in row.get("legs", [])
            )
        ][:limit]

    def _journal_in_window(self, since: str, until: str) -> list[dict[str, Any]]:
        """Choose the last known snapshot without letting future updates hide it."""
        cutoff = _journal_timestamp(until)
        lower = _journal_timestamp(since)
        if len(since) == 10:
            try:
                lower = datetime.fromisoformat(since).replace(tzinfo=UTC)
            except ValueError:
                lower = None
        if cutoff is None or lower is None:
            raise ValueError(
                "Historical journal bounds need valid timezone-aware times."
            )
        with self._connection() as connection:
            rows = connection.execute("SELECT rowid, payload FROM journal").fetchall()
        latest: dict[str, tuple[datetime, int, dict[str, Any]]] = {}
        for row_id, raw in rows:
            payload: dict[str, Any] = json.loads(str(raw))
            timestamp = _journal_timestamp(payload.get("created_at"))
            if timestamp is None or not lower <= timestamp <= cutoff:
                continue
            decision_id = str(payload["decision_id"])
            previous = latest.get(decision_id)
            key = (timestamp, int(row_id))
            if previous is None or key > previous[:2]:
                latest[decision_id] = (timestamp, int(row_id), payload)
        ordered = sorted(latest.values(), key=lambda item: item[:2], reverse=True)
        return [_journal_row(item[2]) for item in ordered]

    def append_journal(self, event: dict[str, Any]) -> None:
        """Append one journal event as a full decision snapshot.

        Args:
            event: Decision snapshot with ``decision_id``, ``legs``, ``status``,
                and the remaining journal fields.
        """
        decision_id = str(event["decision_id"])
        created_at = str(event.get("created_at") or now_iso())
        payload = {**event, "decision_id": decision_id, "created_at": created_at}
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO journal (event_id, decision_id, created_at, payload) "
                "VALUES (?, ?, ?, ?)",
                (uuid4().hex, decision_id, created_at, json.dumps(payload)),
            )

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
        """Return one page of decisions, newest first.

        Args:
            page_no: One-based page number.
            page_size: Decisions per page.
            status: Exact decision status filter.
            ticker: Case-insensitive filter over the legs.
            from_date: Inclusive lower bound on the creation date.
            to_date: Inclusive upper bound on the creation date.

        Returns:
            The decisions on the page and the total matching count.
        """
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT payload FROM (
                  SELECT payload, ROW_NUMBER() OVER (
                    PARTITION BY decision_id
                    ORDER BY created_at DESC, rowid DESC
                  ) AS rank FROM journal
                ) WHERE rank = 1
                ORDER BY json_extract(payload, '$.created_at') DESC
                """
            ).fetchall()
        entries = [json.loads(str(row[0])) for row in rows]
        if status is not None:
            entries = [entry for entry in entries if entry.get("status") == status]
        if ticker is not None:
            wanted = ticker.upper()
            entries = [
                entry
                for entry in entries
                if any(
                    str(leg.get("ticker", "")).upper() == wanted
                    for leg in entry.get("legs", [])
                )
            ]
        if from_date is not None:
            entries = [
                entry
                for entry in entries
                if str(entry.get("created_at", ""))[:10] >= from_date.isoformat()
            ]
        if to_date is not None:
            entries = [
                entry
                for entry in entries
                if str(entry.get("created_at", ""))[:10] <= to_date.isoformat()
            ]
        total = len(entries)
        offset = (page_no - 1) * page_size
        page = entries[offset : offset + page_size]
        return [_journal_row(entry) for entry in page], total


def _journal_timestamp(value: Any) -> datetime | None:
    """Exclude unusable timestamps from historical journal retrieval."""
    if not isinstance(value, str):
        return None
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError:
        return None
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        return None
    return timestamp.astimezone(UTC)


def _journal_row(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(payload["decision_id"]),
        "created_at": str(payload["created_at"]),
        "legs": payload.get("legs", []),
        "thesis": str(payload.get("thesis", "")),
        "horizon": str(payload.get("horizon", "weeks")),
        "evidence_ids": payload.get("evidence_ids", []),
        "status": str(payload.get("status", "proposed")),
        "user_action": payload.get("user_action"),
        "rejection_reason": payload.get("rejection_reason"),
        "outcome": payload.get("outcome"),
    }
