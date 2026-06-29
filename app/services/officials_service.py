"""Responsible people ('officials'): an admin-managed, publicly-viewable
directory of who is responsible for what — by ward and/or department — shown as
a level-based hierarchy on a public page."""
import os
import uuid
from typing import Optional

from app.database import get_db
from app.config import settings
from app.services.user_document_service import file_extension, is_allowed_file  # noqa: F401

_DATA_DIR = os.path.dirname(settings.DATABASE_PATH) or "."
PHOTO_ROOT = os.path.join(_DATA_DIR, "uploads", "officials")

_FIELDS = ("name", "designation", "level", "ward", "department",
           "phone", "email", "photo_path", "office_address", "office_hours")


# --- photo storage ---------------------------------------------------------

def save_photo(original_name: str, content: bytes) -> str:
    os.makedirs(PHOTO_ROOT, exist_ok=True)
    path = os.path.join(PHOTO_ROOT, f"{uuid.uuid4().hex}{file_extension(original_name)}")
    with open(path, "wb") as fh:
        fh.write(content)
    return path


def delete_photo(path: Optional[str]) -> None:
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


# --- queries ---------------------------------------------------------------

async def list_officials() -> list:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM responsible_people ORDER BY level ASC, name COLLATE NOCASE ASC"
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()
    return [dict(r) for r in rows]


async def get_official(official_id: int) -> Optional[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM responsible_people WHERE id = ?", (official_id,)
        )
        row = await cursor.fetchone()
    finally:
        await db.close()
    return dict(row) if row else None


async def list_for(ward: Optional[str], department: Optional[str]) -> list:
    """Officials responsible for a given ward and/or department (for a complaint)."""
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT * FROM responsible_people
               WHERE (ward IS NOT NULL AND ward != '' AND ward = ?)
                  OR (department IS NOT NULL AND department != '' AND department = ?)
               ORDER BY level ASC, name COLLATE NOCASE ASC""",
            (ward or "", department or ""),
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()
    return [dict(r) for r in rows]


async def find_official(name: str, designation: str, ward: str) -> Optional[dict]:
    """Find an official by name + designation + ward (for CSV import dedupe)."""
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT * FROM responsible_people
               WHERE lower(name) = lower(?)
                 AND lower(COALESCE(designation, '')) = lower(?)
                 AND COALESCE(ward, '') = ?""",
            (name, designation or "", ward or ""),
        )
        row = await cursor.fetchone()
    finally:
        await db.close()
    return dict(row) if row else None


async def count_officials() -> int:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT COUNT(*) AS c FROM responsible_people")
        row = await cursor.fetchone()
    finally:
        await db.close()
    return row["c"] if row else 0


# --- mutations -------------------------------------------------------------

async def create_official(data: dict) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            f"""INSERT INTO responsible_people ({', '.join(_FIELDS)})
                VALUES ({', '.join('?' * len(_FIELDS))})""",
            tuple(data.get(f) for f in _FIELDS),
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def update_official(official_id: int, data: dict) -> None:
    assignments = ", ".join(f"{f} = ?" for f in _FIELDS)
    db = await get_db()
    try:
        await db.execute(
            f"""UPDATE responsible_people SET {assignments}, updated_at = datetime('now')
                WHERE id = ?""",
            tuple(data.get(f) for f in _FIELDS) + (official_id,),
        )
        await db.commit()
    finally:
        await db.close()


async def delete_official(official_id: int) -> Optional[str]:
    """Delete an official, returning its photo path (if any) for cleanup."""
    official = await get_official(official_id)
    if not official:
        return None
    db = await get_db()
    try:
        await db.execute("DELETE FROM responsible_people WHERE id = ?", (official_id,))
        await db.commit()
    finally:
        await db.close()
    return official.get("photo_path")
