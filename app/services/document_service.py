"""Master document list: the shared catalogue of documents a scheme can require
and a user can store. Admins extend it from the scheme form."""
from typing import Optional

from app.database import get_db
from app.constants import DEFAULT_DOCUMENTS


async def list_documents() -> list:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM documents ORDER BY name COLLATE NOCASE ASC"
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()
    return [dict(r) for r in rows]


async def count_documents() -> int:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT COUNT(*) AS c FROM documents")
        row = await cursor.fetchone()
    finally:
        await db.close()
    return row["c"] if row else 0


async def add_document(name: str) -> Optional[dict]:
    """Add a document to the master list (case-insensitive dedupe).

    Returns the existing or newly created row as a dict, or None if blank.
    """
    name = (name or "").strip()
    if not name:
        return None
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM documents WHERE name = ? COLLATE NOCASE", (name,)
        )
        existing = await cursor.fetchone()
        if existing:
            return dict(existing)
        cursor = await db.execute(
            "INSERT INTO documents (name) VALUES (?)", (name,)
        )
        await db.commit()
        return {"id": cursor.lastrowid, "name": name}
    finally:
        await db.close()


async def seed_documents() -> None:
    """Seed the default document catalogue on first run (skip if non-empty)."""
    if await count_documents() > 0:
        return
    db = await get_db()
    try:
        for name in DEFAULT_DOCUMENTS:
            await db.execute("INSERT INTO documents (name) VALUES (?)", (name,))
        await db.commit()
    finally:
        await db.close()
