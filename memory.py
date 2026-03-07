"""
memory.py — SQLite persistence: user profiles, conversation history, menu state.
"""
import json
import sqlite3
from contextlib import contextmanager
from typing import Optional

DB_PATH = "marcus.db"

DEFAULT_PROFILE = {
    "name": None,
    "timezone": "UTC",
    "occupation": None,
    "goals": {
        "short_term": [],
        "long_term": [],
        "dreams": [],
    },
    "preferences": {
        "interests": [],
        "communication_style": "direct",
    },
    "schedule": {
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
    },
    "context_notes": "",
}


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS users (
                phone            TEXT PRIMARY KEY,
                profile          TEXT NOT NULL DEFAULT '{}',
                menu_state       TEXT,
                menu_state_data  TEXT,
                msg_count        INTEGER DEFAULT 0,
                created_at       TEXT DEFAULT (datetime('now')),
                last_seen        TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                phone      TEXT NOT NULL,
                role       TEXT NOT NULL,
                content    TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(phone) REFERENCES users(phone)
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


def _row_to_user(row) -> dict:
    d = dict(row)
    d["profile"] = json.loads(d["profile"])
    if d.get("menu_state_data"):
        d["menu_state_data"] = json.loads(d["menu_state_data"])
    return d


def get_user(phone: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
        return _row_to_user(row) if row else None


def create_user(phone: str) -> dict:
    import copy
    profile = copy.deepcopy(DEFAULT_PROFILE)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (phone, profile) VALUES (?, ?)",
            (phone, json.dumps(profile)),
        )
    return get_user(phone)


def update_profile(phone: str, profile: dict):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET profile = ?, last_seen = datetime('now') WHERE phone = ?",
            (json.dumps(profile), phone),
        )


def set_menu_state(phone: str, state: Optional[str], data: Optional[dict] = None):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET menu_state = ?, menu_state_data = ? WHERE phone = ?",
            (state, json.dumps(data) if data else None, phone),
        )


def add_message(phone: str, role: str, content: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO messages (phone, role, content) VALUES (?, ?, ?)",
            (phone, role, content),
        )
        conn.execute(
            "UPDATE users SET msg_count = msg_count + 1, last_seen = datetime('now') WHERE phone = ?",
            (phone,),
        )


def get_history(phone: str, limit: int = 15) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT role, content FROM messages
               WHERE phone = ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (phone, limit),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def get_all_users() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM users").fetchall()
    return [_row_to_user(r) for r in rows]
