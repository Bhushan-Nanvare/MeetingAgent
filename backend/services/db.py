"""SQLite storage so meetings survive a restart."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from config import settings

ROOT = Path(__file__).resolve().parent.parent.parent

SCHEMA = """
CREATE TABLE IF NOT EXISTS meetings (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    meeting_date TEXT,
    summary TEXT NOT NULL DEFAULT '',
    attendees TEXT NOT NULL DEFAULT '',
    transcript_length INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS action_items (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    task TEXT NOT NULL,
    owner TEXT NOT NULL DEFAULT 'Unassigned',
    due_date TEXT,
    priority TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'new',
    source_segment TEXT,
    ticket_id TEXT,
    ticket_url TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_items_meeting ON action_items(meeting_id);
CREATE INDEX IF NOT EXISTS idx_items_status ON action_items(status);
CREATE INDEX IF NOT EXISTS idx_decisions_meeting ON decisions(meeting_id);
"""


def db_path() -> Path:
    configured = Path(settings.DATABASE_PATH)
    return configured if configured.is_absolute() else ROOT / configured


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with session() as conn:
        conn.executescript(SCHEMA)
