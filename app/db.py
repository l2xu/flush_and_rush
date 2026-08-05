import sqlite3
import statistics
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional

from app.settings import LOCAL_TIMEZONE, load_settings

_LOCAL_TZ = ZoneInfo(LOCAL_TIMEZONE)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()



def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)



def _local_date(iso_utc_value: str) -> str:
    # Tagesgrenze wird anhand der lokalen Zeitzone des Start-Zeitpunkts bestimmt.
    dt_utc = _parse_iso(iso_utc_value)
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(_LOCAL_TZ).date().isoformat()



def today_local_date() -> str:
    return datetime.now(timezone.utc).astimezone(_LOCAL_TZ).date().isoformat()



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
                session_date TEXT,
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
            CREATE INDEX IF NOT EXISTS idx_sessions_session_date ON sessions(session_date);
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



def close_session(session_id: int, ended_at: Optional[str] = None) -> Optional[Dict[str, Any]]:
    end_value = ended_at or _now_utc_iso()
    with _connect() as conn:
        row = conn.execute(
            "SELECT started_at, status FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if not row or row["status"] != "open":
            return None

        started_at = _parse_iso(row["started_at"])
        ended_dt = _parse_iso(end_value)
        duration_sec = max(0, int((ended_dt - started_at).total_seconds()))
        session_date = _local_date(row["started_at"])

        conn.execute(
            """
            UPDATE sessions
            SET ended_at = ?, duration_sec = ?, session_date = ?, status = 'closed'
            WHERE id = ?
            """,
            (end_value, duration_sec, session_date, session_id),
        )
        return {
            "id": session_id,
            "started_at": row["started_at"],
            "ended_at": end_value,
            "duration_sec": duration_sec,
            "session_date": session_date,
        }



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
            SELECT id, started_at, ended_at, duration_sec, session_date, status
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



def get_open_session() -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, started_at, ended_at, duration_sec, session_date, status
            FROM sessions
            WHERE status = 'open'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
    if not row:
        return None
    return _enrich_session_row(row)



def _compute_day_stats(durations: List[int]) -> Dict[str, Any]:
    if not durations:
        return {"fastest_sec": None, "median_sec": None, "longest_sec": None, "count": 0}
    return {
        "fastest_sec": min(durations),
        "median_sec": int(round(statistics.median(durations))),
        "longest_sec": max(durations),
        "count": len(durations),
    }



def get_day_stats(session_date: str, exclude_session_id: Optional[int] = None) -> Dict[str, Any]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, duration_sec FROM sessions WHERE session_date = ? AND status = 'closed'",
            (session_date,),
        ).fetchall()
    durations = [int(r["duration_sec"]) for r in rows if exclude_session_id is None or r["id"] != exclude_session_id]
    stats = _compute_day_stats(durations)
    stats["date"] = session_date
    return stats



def list_days() -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT session_date, duration_sec FROM sessions WHERE status = 'closed' AND session_date IS NOT NULL"
        ).fetchall()

    by_date: Dict[str, List[int]] = {}
    for row in rows:
        by_date.setdefault(row["session_date"], []).append(int(row["duration_sec"]))

    days = []
    for date_value, durations in by_date.items():
        stats = _compute_day_stats(durations)
        stats["date"] = date_value
        days.append(stats)

    days.sort(key=lambda d: d["date"], reverse=True)
    return days



def list_sessions_for_day(session_date: str) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, started_at, ended_at, duration_sec, session_date, status
            FROM sessions
            WHERE session_date = ? AND status = 'closed'
            ORDER BY started_at ASC
            """,
            (session_date,),
        ).fetchall()
    return [dict(row) for row in rows]



def delete_session(session_id: int) -> bool:
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        return cursor.rowcount > 0



def log_event(event_type: str, sensor_state: Optional[str] = None) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO events (event_type, sensor_state, created_at) VALUES (?, ?, ?)",
            (event_type, sensor_state, _now_utc_iso()),
        )




