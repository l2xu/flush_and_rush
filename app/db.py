import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.settings import load_settings


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()



def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)



def _connect() -> sqlite3.Connection:
    settings = load_settings()
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn



def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                duration_sec INTEGER,
                status TEXT NOT NULL CHECK(status IN ('open', 'closed')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                sensor_state TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
            """
        )



def create_session(started_at: Optional[str] = None) -> int:
    start_value = started_at or _now_utc_iso()
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO sessions (started_at, status) VALUES (?, 'open')",
            (start_value,),
        )
        return int(cursor.lastrowid)



def close_session(session_id: int, ended_at: Optional[str] = None) -> bool:
    end_value = ended_at or _now_utc_iso()
    with _connect() as conn:
        row = conn.execute(
            "SELECT started_at, status FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if not row or row["status"] != "open":
            return False

        started_at = _parse_iso(row["started_at"])
        ended_dt = _parse_iso(end_value)
        duration_sec = max(0, int((ended_dt - started_at).total_seconds()))

        conn.execute(
            """
            UPDATE sessions
            SET ended_at = ?, duration_sec = ?, status = 'closed'
            WHERE id = ?
            """,
            (end_value, duration_sec, session_id),
        )
        return True



def _enrich_session_row(row: sqlite3.Row) -> Dict[str, Any]:
    data = dict(row)
    if data["status"] == "open":
        started_at = _parse_iso(data["started_at"])
        elapsed_sec = max(0, int((datetime.now(timezone.utc) - started_at).total_seconds()))
        data["elapsed_sec"] = elapsed_sec
    else:
        data["elapsed_sec"] = int(data["duration_sec"] or 0)
    return data



def get_latest_session() -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, started_at, ended_at, duration_sec, status
            FROM sessions
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
    if not row:
        return None
    return _enrich_session_row(row)



def get_latest_open_session_id() -> Optional[int]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM sessions WHERE status = 'open' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return int(row["id"])


def log_event(event_type: str, sensor_state: Optional[str] = None) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO events (event_type, sensor_state, created_at) VALUES (?, ?, ?)",
            (event_type, sensor_state, _now_utc_iso()),
        )




