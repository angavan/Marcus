"""
memory.py — SQLite for session state only.

Identity, memory, and conversation history now live in workspace files (workspace.py).
This module tracks: menu navigation state, schedule config, message count, last seen.
"""
import json
import sqlite3
from contextlib import contextmanager
from typing import Optional

DB_PATH = "marcus.db"

DEFAULT_SCHEDULE = {
    "morning_time": "07:00",
    "midday_time": "12:00",
    "evening_time": "21:00",
    "weekly_day": "sunday",
    "weekly_time": "19:00",
    "monday_time": "08:00",
    "morning_enabled": True,
    "midday_enabled": True,
    "evening_enabled": True,
    "weekly_enabled": True,
    "monday_enabled": True,
}


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS sessions (
                phone           TEXT PRIMARY KEY,
                menu_state      TEXT,
                menu_state_data TEXT,
                schedule        TEXT NOT NULL DEFAULT '{}',
                msg_count       INTEGER DEFAULT 0,
                last_seen       TEXT DEFAULT (datetime('now'))
            );
        """)


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _row_to_session(row) -> dict:
    d = dict(row)
    schedule_raw = json.loads(d.get("schedule") or "{}")
    d["schedule"] = {**DEFAULT_SCHEDULE, **schedule_raw}
    if d.get("menu_state_data"):
        d["menu_state_data"] = json.loads(d["menu_state_data"])
    return d


def get_session(phone: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE phone = ?", (phone,)).fetchone()
        return _row_to_session(row) if row else None


def create_session(phone: str) -> dict:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO sessions (phone, schedule) VALUES (?, ?)",
            (phone, json.dumps(DEFAULT_SCHEDULE)),
        )
    return get_session(phone)


def set_menu_state(phone: str, state: Optional[str], data: Optional[dict] = None):
    with get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET menu_state = ?, menu_state_data = ? WHERE phone = ?",
            (state, json.dumps(data) if data else None, phone),
        )


def update_schedule(phone: str, schedule: dict):
    with get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET schedule = ?, last_seen = datetime('now') WHERE phone = ?",
            (json.dumps(schedule), phone),
        )


def increment_msg(phone: str) -> int:
    with get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET msg_count = msg_count + 1, last_seen = datetime('now') WHERE phone = ?",
            (phone,),
        )
        row = conn.execute("SELECT msg_count FROM sessions WHERE phone = ?", (phone,)).fetchone()
        return row["msg_count"] if row else 0


def get_all_sessions() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM sessions").fetchall()
    return [_row_to_session(r) for r in rows]
