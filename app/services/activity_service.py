"""Admin activity log — an audit trail of who did what, when.

Logging never raises: an audit-log failure must not break the action it records.
"""
from typing import Optional

from app.database import get_db


async def log(actor: Optional[dict], action: str, detail: str = "",
              target_type: Optional[str] = None, target_id: Optional[int] = None) -> None:
    actor_id = actor.get("id") if actor else None
    actor_username = actor.get("username") if actor else "system"
    try:
        db = await get_db()
        try:
            await db.execute(
                """INSERT INTO activity_log
                   (actor_id, actor_username, action, detail, target_type, target_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (actor_id, actor_username, action, detail or None, target_type, target_id),
            )
            await db.commit()
        finally:
            await db.close()
    except Exception:  # never let auditing break the real operation
        pass


async def list_activity(limit: int = 200) -> list:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM activity_log ORDER BY id DESC LIMIT ?", (int(limit),)
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()
    return [dict(r) for r in rows]


async def count_activity() -> int:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT COUNT(*) AS c FROM activity_log")
        row = await cursor.fetchone()
    finally:
        await db.close()
    return row["c"] if row else 0
