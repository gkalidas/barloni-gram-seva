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
    required_documents TEXT,            -- JSON array of supporting docs the user must supply
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

CREATE_USER_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS user_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    document_name TEXT NOT NULL,         -- matches a name in the documents master list
    doc_number TEXT,                     -- e.g. the Aadhaar / account number
    file_path TEXT,                      -- stored scan/photocopy (not public)
    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'approved', 'rejected'
    rejection_reason TEXT,
    reviewed_by INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(user_id, document_name),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (reviewed_by) REFERENCES users(id)
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


async def _ensure_column(db, table: str, column: str, coldef: str) -> None:
    """Add a column to an existing table if it is missing (lightweight migration)."""
    cursor = await db.execute(f"PRAGMA table_info({table})")
    existing = [row["name"] for row in await cursor.fetchall()]
    if column not in existing:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coldef}")


async def init_db() -> None:
    """Create all tables if they do not yet exist, and run small migrations."""
    _ensure_data_dir()
    db = await get_db()
    try:
        await db.execute(CREATE_USERS)
        await db.execute(CREATE_CHANGE_REQUESTS)
        await db.execute(CREATE_DOCUMENTS)
        await db.execute(CREATE_USER_DOCUMENTS)
        await db.execute(CREATE_SCHEMES)
        # Migrations for databases created before a column existed.
        await _ensure_column(db, "profile_change_requests", "required_documents", "TEXT")
        await db.commit()
    finally:
        await db.close()
