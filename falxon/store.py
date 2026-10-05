"""SQLite archive of completed checks (also used as a 24-hour result cache)."""
from __future__ import annotations

import json
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

from .config import settings

_lock = threading.Lock()


def _conn():
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS checks (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            label TEXT,
            confidence REAL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS checks_created ON checks(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS checks_title ON checks(kind, title)")
    return conn


def save(kind: str, title: str, payload: dict, label: str | None = None, confidence: float | None = None) -> str:
    check_id = secrets.token_urlsafe(6)
    with _lock, _conn() as conn:
        conn.execute(
            "INSERT INTO checks VALUES (?, ?, ?, ?, ?, ?, ?)",
            (check_id, kind, title[:500], label, confidence, json.dumps(payload),
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
    return check_id


def get(check_id: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM checks WHERE id=?", (check_id,)).fetchone()
    if not row:
        return None
    return {**dict(row), "payload": json.loads(row["payload"])}


def recent_claim(title: str, hours: int = 24) -> str | None:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
    with _conn() as conn:
        row = conn.execute(
            "SELECT id FROM checks WHERE kind='claim' AND title=? AND created_at>=? "
            "AND payload NOT LIKE '%could not%' ORDER BY created_at DESC LIMIT 1",
            (title, cutoff),
        ).fetchone()
    return row["id"] if row else None


def latest(limit: int = 12, kind: str | None = None) -> list[dict]:
    query = "SELECT id, kind, title, label, confidence, created_at FROM checks"
    params: tuple = ()
    if kind:
        query += " WHERE kind=?"
        params = (kind,)
    query += " ORDER BY created_at DESC LIMIT ?"
    with _conn() as conn:
        return [dict(r) for r in conn.execute(query, (*params, limit)).fetchall()]


def stats() -> dict:
    with _conn() as conn:
        rows = conn.execute("SELECT label, COUNT(*) n FROM checks WHERE kind='claim' GROUP BY label").fetchall()
    return {r["label"]: r["n"] for r in rows}
