"""Database connection helpers and schema creation using aiosqlite."""
import os
import aiosqlite

from app.config import settings

# Table definitions ---------------------------------------------------------

CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    mobile TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    profile_data TEXT,
    pending_profile_data TEXT,
    profile_submitted INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
"""

CREATE_CHANGE_REQUESTS = """
CREATE TABLE IF NOT EXISTS profile_change_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    old_values TEXT NOT NULL,
    new_values TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    rejection_reason TEXT,
    reviewed_by INTEGER,
    requested_at TEXT DEFAULT (datetime('now')),
    reviewed_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (reviewed_by) REFERENCES users(id)
);
"""

CREATE_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
"""

CREATE_SCHEMES = """
CREATE TABLE IF NOT EXISTS schemes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    name_hi TEXT,
    ministry TEXT,
    category TEXT,
    objective TEXT,
    benefits TEXT,
    eligibility_rules TEXT,
    documents_required TEXT,
    how_to_apply TEXT,
    application_deadline TEXT,
    status TEXT DEFAULT 'active',
    scheme_data TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
"""


def _ensure_data_dir() -> None:
    """Make sure the directory that holds the SQLite file exists."""
    db_dir = os.path.dirname(settings.DATABASE_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)


async def get_db() -> aiosqlite.Connection:
    """Open a new connection with row factory set to sqlite3.Row."""
    db = await aiosqlite.connect(settings.DATABASE_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON;")
    return db


async def init_db() -> None:
    """Create all tables if they do not yet exist."""
    _ensure_data_dir()
    db = await get_db()
    try:
        await db.execute(CREATE_USERS)
        await db.execute(CREATE_CHANGE_REQUESTS)
        await db.execute(CREATE_DOCUMENTS)
        await db.execute(CREATE_SCHEMES)
        await db.commit()
    finally:
        await db.close()
