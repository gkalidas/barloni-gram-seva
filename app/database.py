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


CREATE_COMPLAINTS = """
CREATE TABLE IF NOT EXISTS complaints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,            -- the filer (internal; never shown publicly)
    category TEXT NOT NULL,
    ward TEXT,
    description TEXT NOT NULL,
    photo_path TEXT,                     -- optional stored photo (issue evidence)
    status TEXT NOT NULL DEFAULT 'submitted',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""

CREATE_COMPLAINT_HISTORY = """
CREATE TABLE IF NOT EXISTS complaint_status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id INTEGER NOT NULL,
    old_status TEXT,
    new_status TEXT NOT NULL,
    note TEXT,
    changed_by INTEGER,                  -- admin/user who made the change (audit trail)
    changed_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (complaint_id) REFERENCES complaints(id),
    FOREIGN KEY (changed_by) REFERENCES users(id)
);
"""


CREATE_RESPONSIBLE_PEOPLE = """
CREATE TABLE IF NOT EXISTS responsible_people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    designation TEXT,
    level INTEGER NOT NULL DEFAULT 2,    -- 1 = top of the hierarchy
    ward TEXT,                           -- optional: responsible for this ward
    department TEXT,                     -- optional: responsible for this category
    phone TEXT,
    email TEXT,
    photo_path TEXT,
    office_address TEXT,
    office_hours TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
"""


CREATE_ACTIVITY_LOG = """
CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER,                    -- admin who acted (no FK: log outlives the user)
    actor_username TEXT,                 -- snapshot, so it survives admin deletion
    action TEXT NOT NULL,                -- short code, e.g. 'scheme.delete'
    detail TEXT,                         -- human-readable description
    target_type TEXT,
    target_id INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);
"""


CREATE_APPROVAL_POLICY = """
CREATE TABLE IF NOT EXISTS approval_policy (
    action_key TEXT PRIMARY KEY,
    level TEXT NOT NULL DEFAULT 'none'   -- 'none' | '2' | '3' | 'superadmin'
);
"""

CREATE_APPROVAL_REQUESTS = """
CREATE TABLE IF NOT EXISTS approval_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_key TEXT NOT NULL,
    payload TEXT,                        -- JSON of the intended change
    detail TEXT,                         -- human-readable summary
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected
    required TEXT NOT NULL,              -- snapshot of the level at creation
    initiated_by INTEGER,
    initiated_by_username TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    resolved_at TEXT,
    resolved_note TEXT
);
"""

CREATE_APPROVAL_VOTES = """
CREATE TABLE IF NOT EXISTS approval_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL,
    voter_id INTEGER,
    voter_username TEXT,
    voter_role TEXT,
    vote TEXT NOT NULL DEFAULT 'approve',    -- approve | reject
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(request_id, voter_id),
    FOREIGN KEY (request_id) REFERENCES approval_requests(id)
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
        await db.execute(CREATE_COMPLAINTS)
        await db.execute(CREATE_COMPLAINT_HISTORY)
        await db.execute(CREATE_RESPONSIBLE_PEOPLE)
        await db.execute(CREATE_ACTIVITY_LOG)
        await db.execute(CREATE_APPROVAL_POLICY)
        await db.execute(CREATE_APPROVAL_REQUESTS)
        await db.execute(CREATE_APPROVAL_VOTES)
        # Migrations for databases created before a column existed.
        await _ensure_column(db, "profile_change_requests", "required_documents", "TEXT")
        await _ensure_column(db, "complaints", "filer_unseen", "INTEGER DEFAULT 0")
        await _ensure_column(db, "users", "active", "INTEGER DEFAULT 1")
        await db.commit()
    finally:
        await db.close()
