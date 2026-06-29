"""Scheme CRUD and search operations."""
import json
from typing import Optional

from app.database import get_db

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


async def delete_scheme(scheme_id: int) -> None:
    db = await get_db()
    try:
        await db.execute("DELETE FROM schemes WHERE id = ?", (scheme_id,))
        await db.commit()
    finally:
        await db.close()


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
