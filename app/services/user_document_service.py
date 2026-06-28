"""A user's personal document locker: uploaded documents (number + scan/photo)
that an admin reviews and approves. Files are stored on disk, never public."""
import os
import uuid
from typing import Optional

from app.database import get_db
from app.config import settings

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB

_DATA_DIR = os.path.dirname(settings.DATABASE_PATH) or "."
UPLOAD_ROOT = os.path.join(_DATA_DIR, "uploads")


# --- file helpers ----------------------------------------------------------

def file_extension(filename: str) -> str:
    return os.path.splitext(filename or "")[1].lower()


def is_allowed_file(filename: str) -> bool:
    return file_extension(filename) in ALLOWED_EXTENSIONS


def save_file(user_id: int, original_name: str, content: bytes) -> str:
    """Save an upload under data/uploads/<user_id>/ with a random name."""
    ext = file_extension(original_name)
    user_dir = os.path.join(UPLOAD_ROOT, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    path = os.path.join(user_dir, f"{uuid.uuid4().hex}{ext}")
    with open(path, "wb") as fh:
        fh.write(content)
    return path


def delete_file(path: Optional[str]) -> None:
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


# --- queries ---------------------------------------------------------------

async def list_user_documents(user_id: int) -> list:
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT * FROM user_documents WHERE user_id = ?
               ORDER BY document_name COLLATE NOCASE ASC""",
            (user_id,),
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()
    return [dict(r) for r in rows]


async def approved_document_names(user_id: int) -> set:
    """Names of the user's approved documents (for per-scheme matching)."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT document_name FROM user_documents WHERE user_id = ? AND status = 'approved'",
            (user_id,),
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()
    return {r["document_name"] for r in rows}


async def get_user_document(doc_id: int) -> Optional[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM user_documents WHERE id = ?", (doc_id,)
        )
        row = await cursor.fetchone()
    finally:
        await db.close()
    return dict(row) if row else None


async def _get_by_user_and_name(user_id: int, name: str) -> Optional[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM user_documents WHERE user_id = ? AND document_name = ?",
            (user_id, name),
        )
        row = await cursor.fetchone()
    finally:
        await db.close()
    return dict(row) if row else None


# --- mutations -------------------------------------------------------------

async def upsert_pending(user_id: int, document_name: str,
                         doc_number: str, file_path: str) -> tuple:
    """Create or replace a user's document, marking it pending review.

    Returns (doc_id, old_file_path) so the caller can clean up a replaced file.
    """
    existing = await _get_by_user_and_name(user_id, document_name)
    db = await get_db()
    try:
        if existing:
            await db.execute(
                """UPDATE user_documents
                   SET doc_number = ?, file_path = ?, status = 'pending',
                       rejection_reason = NULL, reviewed_by = NULL,
                       updated_at = datetime('now')
                   WHERE id = ?""",
                (doc_number, file_path, existing["id"]),
            )
            doc_id = existing["id"]
        else:
            cursor = await db.execute(
                """INSERT INTO user_documents
                   (user_id, document_name, doc_number, file_path, status)
                   VALUES (?, ?, ?, ?, 'pending')""",
                (user_id, document_name, doc_number, file_path),
            )
            doc_id = cursor.lastrowid
        await db.commit()
    finally:
        await db.close()
    return doc_id, (existing["file_path"] if existing else None)


async def delete_user_document(doc_id: int, user_id: int) -> Optional[str]:
    """Delete a document owned by the user. Returns its file path if removed."""
    doc = await get_user_document(doc_id)
    if not doc or doc["user_id"] != user_id:
        return None
    db = await get_db()
    try:
        await db.execute("DELETE FROM user_documents WHERE id = ?", (doc_id,))
        await db.commit()
    finally:
        await db.close()
    return doc.get("file_path")


# --- admin review ----------------------------------------------------------

async def list_document_requests(status: Optional[str] = "pending") -> list:
    query = """SELECT ud.*, u.username AS username, u.mobile AS mobile
               FROM user_documents ud JOIN users u ON u.id = ud.user_id"""
    params = []
    if status:
        query += " WHERE ud.status = ?"
        params.append(status)
    query += " ORDER BY ud.updated_at DESC"
    db = await get_db()
    try:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
    finally:
        await db.close()
    return [dict(r) for r in rows]


async def count_pending_document_requests() -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT COUNT(*) AS c FROM user_documents WHERE status = 'pending'"
        )
        row = await cursor.fetchone()
    finally:
        await db.close()
    return row["c"] if row else 0


async def approve_document(doc_id: int, admin_id: int) -> bool:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id FROM user_documents WHERE id = ? AND status = 'pending'",
            (doc_id,),
        )
        if await cursor.fetchone() is None:
            return False
        await db.execute(
            """UPDATE user_documents SET status = 'approved', rejection_reason = NULL,
               reviewed_by = ?, updated_at = datetime('now') WHERE id = ?""",
            (admin_id, doc_id),
        )
        await db.commit()
        return True
    finally:
        await db.close()


async def reject_document(doc_id: int, admin_id: int, reason: str) -> bool:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id FROM user_documents WHERE id = ? AND status = 'pending'",
            (doc_id,),
        )
        if await cursor.fetchone() is None:
            return False
        await db.execute(
            """UPDATE user_documents SET status = 'rejected', rejection_reason = ?,
               reviewed_by = ?, updated_at = datetime('now') WHERE id = ?""",
            (reason, admin_id, doc_id),
        )
        await db.commit()
        return True
    finally:
        await db.close()
