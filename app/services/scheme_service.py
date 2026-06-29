"""Scheme CRUD and search operations."""
import json
import os
import uuid
from typing import Optional

from app.config import settings
from app.database import get_db

# --- scheme source references (GR file + official links) -------------------

# GRs come in many formats; allow the common document/scan/sheet types, but not
# anything executable or web-renderable (no .svg/.html) since these are served
# to the public. Files are always served as a download (attachment).
SOURCE_ALLOWED_EXTENSIONS = {
    ".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx",
    ".xls", ".xlsx", ".txt", ".csv", ".odt", ".ods",
}
SOURCE_MAX_BYTES = 10 * 1024 * 1024  # 10 MB — GRs can be multi-page scans

_DATA_DIR = os.path.dirname(settings.DATABASE_PATH) or "."
SOURCE_ROOT = os.path.join(_DATA_DIR, "uploads", "scheme_sources")


def source_extension(filename: str) -> str:
    return os.path.splitext(filename or "")[1].lower()


def is_allowed_source_file(filename: str) -> bool:
    return source_extension(filename) in SOURCE_ALLOWED_EXTENSIONS

# Allowed categories for validation / display
CATEGORIES = [
    "agriculture",
    "housing",
    "health",
    "education",
    "pension",
    "employment",
    "women_child",
    "sc_st_welfare",
    "other",
]


def _parse_scheme(row) -> dict:
    """Convert a DB row into a dict with JSON fields decoded."""
    scheme = dict(row)
    for field in ("eligibility_rules", "documents_required", "scheme_data"):
        raw = scheme.get(field)
        if raw:
            try:
                scheme[field] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                scheme[field] = None
        else:
            scheme[field] = None
    return scheme


async def list_schemes(
    search: Optional[str] = None,
    category: Optional[str] = None,
    only_active: bool = True,
) -> list:
    """Return schemes, optionally filtered by search text / category."""
    query = "SELECT * FROM schemes WHERE 1=1"
    params = []
    if only_active:
        query += " AND status = 'active'"
    if category:
        query += " AND category = ?"
        params.append(category)
    if search:
        query += " AND (name LIKE ? OR objective LIKE ? OR ministry LIKE ?)"
        like = f"%{search}%"
        params.extend([like, like, like])
    query += " ORDER BY name COLLATE NOCASE ASC"

    db = await get_db()
    try:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
    finally:
        await db.close()
    return [_parse_scheme(r) for r in rows]


async def get_scheme(scheme_id: int) -> Optional[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM schemes WHERE id = ?", (scheme_id,)
        )
        row = await cursor.fetchone()
    finally:
        await db.close()
    return _parse_scheme(row) if row else None


async def get_scheme_by_name(name: str) -> Optional[dict]:
    """Look up a scheme by exact name (case-insensitive), for import dedupe."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM schemes WHERE name = ? COLLATE NOCASE", (name,)
        )
        row = await cursor.fetchone()
    finally:
        await db.close()
    return _parse_scheme(row) if row else None


async def count_schemes() -> int:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT COUNT(*) AS c FROM schemes")
        row = await cursor.fetchone()
    finally:
        await db.close()
    return row["c"] if row else 0


async def create_scheme(data: dict) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO schemes
               (name, name_hi, ministry, category, objective, benefits,
                eligibility_rules, documents_required, how_to_apply,
                application_deadline, status, scheme_data)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data.get("name"),
                data.get("name_hi"),
                data.get("ministry"),
                data.get("category"),
                data.get("objective"),
                data.get("benefits"),
                data.get("eligibility_rules"),
                data.get("documents_required"),
                data.get("how_to_apply"),
                data.get("application_deadline"),
                data.get("status", "active"),
                data.get("scheme_data"),
            ),
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def delete_scheme(scheme_id: int) -> list:
    """Delete a scheme and its source references. Returns source file paths to
    remove from disk (caller deletes the files)."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT file_path FROM scheme_sources WHERE scheme_id = ? AND file_path IS NOT NULL",
            (scheme_id,),
        )
        paths = [r["file_path"] for r in await cursor.fetchall()]
        await db.execute("DELETE FROM scheme_sources WHERE scheme_id = ?", (scheme_id,))
        await db.execute("DELETE FROM schemes WHERE id = ?", (scheme_id,))
        await db.commit()
    finally:
        await db.close()
    return paths


# --- scheme sources --------------------------------------------------------

def _save_source_file(original_name: str, content: bytes) -> str:
    """Store a GR/source upload under a random name. Returns the path."""
    os.makedirs(SOURCE_ROOT, exist_ok=True)
    ext = source_extension(original_name)
    path = os.path.join(SOURCE_ROOT, f"{uuid.uuid4().hex}{ext}")
    with open(path, "wb") as fh:
        fh.write(content)
    return path


async def list_sources(scheme_id: int) -> list:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM scheme_sources WHERE scheme_id = ? "
            "ORDER BY kind ASC, id ASC",
            (scheme_id,),
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()
    return [dict(r) for r in rows]


async def get_source(source_id: int) -> Optional[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM scheme_sources WHERE id = ?", (source_id,)
        )
        row = await cursor.fetchone()
    finally:
        await db.close()
    return dict(row) if row else None


async def add_link_source(scheme_id: int, label: str, url: str) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO scheme_sources (scheme_id, kind, label, url)
               VALUES (?, 'link', ?, ?)""",
            (scheme_id, label or None, url),
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def add_file_source(scheme_id: int, label: str, original_name: str,
                          content: bytes) -> int:
    path = _save_source_file(original_name, content)
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO scheme_sources
               (scheme_id, kind, label, file_path, original_name)
               VALUES (?, 'file', ?, ?, ?)""",
            (scheme_id, label or None, path, original_name),
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def delete_source(source_id: int) -> Optional[str]:
    """Delete a source row. Returns its file path (if any) for the caller to
    remove from disk."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT file_path FROM scheme_sources WHERE id = ?", (source_id,)
        )
        row = await cursor.fetchone()
        file_path = row["file_path"] if row else None
        await db.execute("DELETE FROM scheme_sources WHERE id = ?", (source_id,))
        await db.commit()
    finally:
        await db.close()
    return file_path


async def update_scheme(scheme_id: int, data: dict) -> None:
    db = await get_db()
    try:
        await db.execute(
            """UPDATE schemes SET
               name = ?, name_hi = ?, ministry = ?, category = ?,
               objective = ?, benefits = ?, eligibility_rules = ?,
               documents_required = ?, how_to_apply = ?,
               application_deadline = ?, status = ?, scheme_data = ?,
               updated_at = datetime('now')
               WHERE id = ?""",
            (
                data.get("name"),
                data.get("name_hi"),
                data.get("ministry"),
                data.get("category"),
                data.get("objective"),
                data.get("benefits"),
                data.get("eligibility_rules"),
                data.get("documents_required"),
                data.get("how_to_apply"),
                data.get("application_deadline"),
                data.get("status", "active"),
                data.get("scheme_data"),
                scheme_id,
            ),
        )
        await db.commit()
    finally:
        await db.close()
