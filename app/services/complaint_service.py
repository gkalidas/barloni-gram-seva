"""Complaints: villagers report civic issues; admins track them to resolution.

The community board is public but anonymous — the filer's identity is stored
(user_id) and visible only to admins / in the audit trail, never on the board.
"""
import os
import uuid
from typing import Optional

from app.database import get_db
from app.config import settings
from app.constants import COMPLAINT_OPEN_STATUSES
from app.services.user_document_service import (
    ALLOWED_EXTENSIONS, MAX_FILE_BYTES, file_extension, is_allowed_file,
)

_DATA_DIR = os.path.dirname(settings.DATABASE_PATH) or "."
PHOTO_ROOT = os.path.join(_DATA_DIR, "uploads", "complaints")


# --- photo storage ---------------------------------------------------------

def save_photo(original_name: str, content: bytes) -> str:
    """Store a complaint photo under a random name. Returns the path."""
    os.makedirs(PHOTO_ROOT, exist_ok=True)
    ext = file_extension(original_name)
    path = os.path.join(PHOTO_ROOT, f"{uuid.uuid4().hex}{ext}")
    with open(path, "wb") as fh:
        fh.write(content)
    return path


def delete_photo(path: Optional[str]) -> None:
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


# --- create ----------------------------------------------------------------

async def create_complaint(user_id: int, category: str, ward: str,
                           description: str, photo_path: Optional[str]) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO complaints (user_id, category, ward, description, photo_path)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, category, ward or None, description, photo_path),
        )
        complaint_id = cursor.lastrowid
        await db.execute(
            """INSERT INTO complaint_status_history
               (complaint_id, old_status, new_status, note, changed_by)
               VALUES (?, NULL, 'submitted', NULL, ?)""",
            (complaint_id, user_id),
        )
        await db.commit()
        return complaint_id
    finally:
        await db.close()


# --- queries ---------------------------------------------------------------

def _build_filters(category, ward, status):
    clauses, params = [], []
    if category:
        clauses.append("category = ?"); params.append(category)
    if ward:
        clauses.append("ward = ?"); params.append(ward)
    if status:
        clauses.append("status = ?"); params.append(status)
    return clauses, params


async def list_complaints(category=None, ward=None, status=None,
                          user_id=None) -> list:
    """Board / 'my complaints' view. No filer identity is selected here."""
    clauses, params = _build_filters(category, ward, status)
    if user_id is not None:
        clauses.append("user_id = ?"); params.append(user_id)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    db = await get_db()
    try:
        cursor = await db.execute(
            f"""SELECT id, category, ward, description, photo_path, status,
                       filer_unseen, created_at, updated_at
                FROM complaints{where} ORDER BY created_at DESC, id DESC""",
            params,
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()
    return [dict(r) for r in rows]


async def list_complaints_admin(category=None, ward=None, status=None) -> list:
    """Admin list — includes the filer's identity."""
    clauses, params = _build_filters(category, ward, status)
    where = (" WHERE " + " AND ".join("c." + c for c in clauses)) if clauses else ""
    db = await get_db()
    try:
        cursor = await db.execute(
            f"""SELECT c.*, u.username AS filer_username, u.mobile AS filer_mobile
                FROM complaints c JOIN users u ON u.id = c.user_id
                {where} ORDER BY c.created_at DESC, c.id DESC""",
            params,
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()
    return [dict(r) for r in rows]


async def get_complaint(complaint_id: int) -> Optional[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM complaints WHERE id = ?", (complaint_id,)
        )
        row = await cursor.fetchone()
    finally:
        await db.close()
    return dict(row) if row else None


async def get_complaint_with_filer(complaint_id: int) -> Optional[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT c.*, u.username AS filer_username, u.mobile AS filer_mobile
               FROM complaints c JOIN users u ON u.id = c.user_id
               WHERE c.id = ?""",
            (complaint_id,),
        )
        row = await cursor.fetchone()
    finally:
        await db.close()
    return dict(row) if row else None


async def list_status_history(complaint_id: int) -> list:
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT h.*, u.username AS by_username
               FROM complaint_status_history h
               LEFT JOIN users u ON u.id = h.changed_by
               WHERE h.complaint_id = ? ORDER BY h.changed_at ASC, h.id ASC""",
            (complaint_id,),
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()
    return [dict(r) for r in rows]


async def count_open_complaints() -> int:
    placeholders = ",".join("?" * len(COMPLAINT_OPEN_STATUSES))
    db = await get_db()
    try:
        cursor = await db.execute(
            f"SELECT COUNT(*) AS c FROM complaints WHERE status IN ({placeholders})",
            COMPLAINT_OPEN_STATUSES,
        )
        row = await cursor.fetchone()
    finally:
        await db.close()
    return row["c"] if row else 0


# --- mutations -------------------------------------------------------------

async def update_status(complaint_id: int, admin_id: int, new_status: str,
                        note: str = "") -> bool:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT status FROM complaints WHERE id = ?", (complaint_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return False
        old_status = row["status"]
        await db.execute(
            """UPDATE complaints SET status = ?, filer_unseen = 1,
               updated_at = datetime('now') WHERE id = ?""",
            (new_status, complaint_id),
        )
        await db.execute(
            """INSERT INTO complaint_status_history
               (complaint_id, old_status, new_status, note, changed_by)
               VALUES (?, ?, ?, ?, ?)""",
            (complaint_id, old_status, new_status, note or None, admin_id),
        )
        await db.commit()
        return True
    finally:
        await db.close()


async def mark_seen(complaint_id: int, user_id: int) -> None:
    """Clear the 'unseen update' flag once the filer views their complaint."""
    db = await get_db()
    try:
        await db.execute(
            "UPDATE complaints SET filer_unseen = 0 WHERE id = ? AND user_id = ?",
            (complaint_id, user_id),
        )
        await db.commit()
    finally:
        await db.close()


async def count_unseen_for_user(user_id: int) -> int:
    """How many of the user's complaints have an unseen status update."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT COUNT(*) AS c FROM complaints WHERE user_id = ? AND filer_unseen = 1",
            (user_id,),
        )
        row = await cursor.fetchone()
    finally:
        await db.close()
    return row["c"] if row else 0


async def complaint_stats() -> dict:
    """Aggregate counts for the admin analytics view."""
    open_ph = ",".join("?" * len(COMPLAINT_OPEN_STATUSES))
    db = await get_db()
    try:
        async def scalar(query, params=()):
            cur = await db.execute(query, params)
            row = await cur.fetchone()
            return row["c"] if row else 0

        async def grouped(query, params=()):
            cur = await db.execute(query, params)
            return [dict(r) for r in await cur.fetchall()]

        total = await scalar("SELECT COUNT(*) AS c FROM complaints")
        open_count = await scalar(
            f"SELECT COUNT(*) AS c FROM complaints WHERE status IN ({open_ph})",
            COMPLAINT_OPEN_STATUSES)
        resolved = await scalar(
            "SELECT COUNT(*) AS c FROM complaints WHERE status = 'resolved'")
        this_month = await scalar(
            "SELECT COUNT(*) AS c FROM complaints "
            "WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')")
        by_category = await grouped(
            "SELECT category, COUNT(*) AS c FROM complaints "
            "GROUP BY category ORDER BY c DESC")
        by_ward = await grouped(
            "SELECT COALESCE(ward, '—') AS ward, COUNT(*) AS c FROM complaints "
            "GROUP BY ward ORDER BY c DESC")
        by_status = await grouped(
            "SELECT status, COUNT(*) AS c FROM complaints GROUP BY status")
        matrix_rows = await grouped(
            "SELECT COALESCE(ward, '—') AS ward, category, COUNT(*) AS c "
            "FROM complaints GROUP BY ward, category")
    finally:
        await db.close()
    return {
        "total": total, "open": open_count, "resolved": resolved,
        "this_month": this_month, "by_category": by_category,
        "by_ward": by_ward, "by_status": by_status, "matrix_rows": matrix_rows,
    }


async def withdraw_complaint(complaint_id: int, user_id: int) -> bool:
    """A filer may withdraw their own complaint while it is still 'submitted'."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT user_id, status FROM complaints WHERE id = ?", (complaint_id,)
        )
        row = await cursor.fetchone()
        if row is None or row["user_id"] != user_id or row["status"] != "submitted":
            return False
        await db.execute(
            """UPDATE complaints SET status = 'withdrawn', updated_at = datetime('now')
               WHERE id = ?""",
            (complaint_id,),
        )
        await db.execute(
            """INSERT INTO complaint_status_history
               (complaint_id, old_status, new_status, note, changed_by)
               VALUES (?, 'submitted', 'withdrawn', 'Withdrawn by filer', ?)""",
            (complaint_id, user_id),
        )
        await db.commit()
        return True
    finally:
        await db.close()
