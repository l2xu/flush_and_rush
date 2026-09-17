import sqlite3
import statistics
from contextlib import contextmanager
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from app.settings import LOCAL_TIMEZONE, load_settings

_LOCAL_TZ = ZoneInfo(LOCAL_TIMEZONE)

_SESSION_COLUMNS = "id, started_at, ended_at, duration_sec, session_date, status"

# Obergrenzen (Sekunden) der Histogramm-Klassen; None = offenes Ende.
_DURATION_BUCKETS: Sequence[Tuple[Optional[int], str]] = (
    (30, "< 30s"),
    (60, "30–60s"),
    (120, "1–2m"),
    (180, "2–3m"),
    (300, "3–5m"),
    (600, "5–10m"),
    (None, "> 10m"),
)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _to_local(iso_utc_value: str) -> datetime:
    return _parse_iso(iso_utc_value).astimezone(_LOCAL_TZ)


def _local_date(iso_utc_value: str) -> str:
    # Tagesgrenze wird anhand der lokalen Zeitzone des Start-Zeitpunkts bestimmt.
    return _to_local(iso_utc_value).date().isoformat()


def today_local_date() -> str:
    return datetime.now(timezone.utc).astimezone(_LOCAL_TZ).date().isoformat()


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(load_settings().db_path)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:  # commit bzw. rollback
            yield conn
    finally:
        # sqlite3 schliesst die Verbindung beim Verlassen des with-Blocks nicht selbst.
        conn.close()


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

        duration_sec = max(0, int((_parse_iso(end_value) - _parse_iso(row["started_at"])).total_seconds()))
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
        elapsed = (datetime.now(timezone.utc) - _parse_iso(data["started_at"])).total_seconds()
        data["elapsed_sec"] = max(0, int(elapsed))
    else:
        data["elapsed_sec"] = int(data["duration_sec"] or 0)
    return data


def get_latest_open_session_id() -> Optional[int]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM sessions WHERE status = 'open' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return int(row["id"]) if row else None


def get_open_session() -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            f"SELECT {_SESSION_COLUMNS} FROM sessions WHERE status = 'open' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return _enrich_session_row(row) if row else None


def _stats_of(durations: Sequence[int]) -> Dict[str, Any]:
    """Fastest/Median/Longest einer Dauer-Liste; leere Liste -> None-Werte."""
    if not durations:
        return {"fastest_sec": None, "median_sec": None, "longest_sec": None, "count": 0, "total_sec": 0}
    return {
        "fastest_sec": min(durations),
        "median_sec": int(round(statistics.median(durations))),
        "longest_sec": max(durations),
        "count": len(durations),
        "total_sec": sum(durations),
    }


def _closed_rows(
    conn: sqlite3.Connection,
    columns: str,
    where: str = "",
    params: Iterable[Any] = (),
    order_by: str = "",
) -> List[sqlite3.Row]:
    clause = f" AND {where}" if where else ""
    ordering = f" ORDER BY {order_by}" if order_by else ""
    return conn.execute(
        f"SELECT {columns} FROM sessions WHERE status = 'closed'{clause}{ordering}", tuple(params)
    ).fetchall()


def get_day_stats(session_date: str, exclude_session_id: Optional[int] = None) -> Dict[str, Any]:
    with _connect() as conn:
        rows = _closed_rows(conn, "id, duration_sec", "session_date = ?", (session_date,))
    durations = [int(r["duration_sec"]) for r in rows if r["id"] != exclude_session_id]
    return {**_stats_of(durations), "date": session_date}


def list_days() -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = _closed_rows(conn, "session_date, duration_sec", "session_date IS NOT NULL")

    by_date: Dict[str, List[int]] = {}
    for row in rows:
        by_date.setdefault(row["session_date"], []).append(int(row["duration_sec"]))

    days = [{**_stats_of(durations), "date": date_value} for date_value, durations in by_date.items()]
    days.sort(key=lambda day: day["date"], reverse=True)
    return days


def list_sessions_for_day(session_date: str) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = _closed_rows(
            conn, _SESSION_COLUMNS, "session_date = ?", (session_date,), order_by="started_at ASC"
        )
    return [dict(row) for row in rows]


def _bucket_label(duration_sec: int) -> str:
    for upper, label in _DURATION_BUCKETS:
        if upper is None or duration_sec < upper:
            return label
    return _DURATION_BUCKETS[-1][1]


def get_statistics(day_limit: int = 30) -> Dict[str, Any]:
    """Aggregate fuer die Admin-Auswertung: Gesamtwerte, Tagesverlauf, Uhrzeit-,
    Wochentag- und Dauerverteilung."""
    with _connect() as conn:
        rows = _closed_rows(conn, "started_at, session_date, duration_sec", "duration_sec IS NOT NULL")

    all_durations: List[int] = []
    by_date: Dict[str, List[int]] = {}
    by_hour: Dict[int, List[int]] = {}
    by_weekday: Dict[int, List[int]] = {}
    histogram: Dict[str, int] = {label: 0 for _, label in _DURATION_BUCKETS}

    for row in rows:
        duration = int(row["duration_sec"])
        started_local = _to_local(row["started_at"])

        all_durations.append(duration)
        by_date.setdefault(row["session_date"] or started_local.date().isoformat(), []).append(duration)
        by_hour.setdefault(started_local.hour, []).append(duration)
        by_weekday.setdefault(started_local.weekday(), []).append(duration)
        histogram[_bucket_label(duration)] += 1

    daily = [{**_stats_of(durations), "date": date_value} for date_value, durations in by_date.items()]
    daily.sort(key=lambda day: day["date"])
    busiest = max(daily, key=lambda day: day["count"], default=None)

    totals = _stats_of(all_durations)
    totals["days"] = len(daily)
    totals["avg_per_day"] = round(len(all_durations) / len(daily), 1) if daily else 0
    totals["busiest_date"] = busiest["date"] if busiest else None
    totals["busiest_count"] = busiest["count"] if busiest else 0

    return {
        "totals": totals,
        "today": get_day_stats(today_local_date()),
        "daily": daily[-day_limit:] if day_limit > 0 else daily,
        "by_hour": [
            {"hour": hour, **_stats_of(by_hour.get(hour, []))} for hour in range(24)
        ],
        "by_weekday": [
            {"weekday": weekday, **_stats_of(by_weekday.get(weekday, []))} for weekday in range(7)
        ],
        "histogram": [{"label": label, "count": histogram[label]} for _, label in _DURATION_BUCKETS],
    }


def delete_session(session_id: int) -> bool:
    with _connect() as conn:
        return conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,)).rowcount > 0


def log_event(event_type: str, sensor_state: Optional[str] = None) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO events (event_type, sensor_state, created_at) VALUES (?, ?, ?)",
            (event_type, sensor_state, _now_utc_iso()),
        )
