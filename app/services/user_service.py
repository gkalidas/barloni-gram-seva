"""User account, profile management, and change-request operations."""
import json
from typing import Optional

from app.database import get_db
from app.auth import hash_password


# Account ------------------------------------------------------------------

async def get_user_by_id(user_id: int) -> Optional[dict]:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
    finally:
        await db.close()
    return dict(row) if row else None


async def get_user_by_username(username: str) -> Optional[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        )
        row = await cursor.fetchone()
    finally:
        await db.close()
    return dict(row) if row else None


async def get_user_by_mobile(mobile: str) -> Optional[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM users WHERE mobile = ?", (mobile,)
        )
        row = await cursor.fetchone()
    finally:
        await db.close()
    return dict(row) if row else None


async def create_user(username: str, mobile: str, password: str,
                      role: str = "user") -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO users (username, mobile, password_hash, role)
               VALUES (?, ?, ?, ?)""",
            (username, mobile, hash_password(password), role),
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def list_users() -> list:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM users ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()
    return [dict(r) for r in rows]


async def count_users() -> int:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT COUNT(*) AS c FROM users")
        row = await cursor.fetchone()
    finally:
        await db.close()
    return row["c"] if row else 0


# Profile helpers ----------------------------------------------------------

def get_profile(user: dict) -> Optional[dict]:
    """Decode the user's stored profile_data JSON."""
    raw = user.get("profile_data")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def get_pending_profile(user: dict) -> Optional[dict]:
    raw = user.get("pending_profile_data")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


async def submit_first_profile(user_id: int, profile: dict) -> None:
    """First-time submission saves directly to profile_data."""
    db = await get_db()
    try:
        await db.execute(
            """UPDATE users SET profile_data = ?, profile_submitted = 1,
               updated_at = datetime('now') WHERE id = ?""",
            (json.dumps(profile), user_id),
        )
        await db.commit()
    finally:
        await db.close()


async def request_profile_change(user_id: int, old_profile: dict,
                                 new_profile: dict) -> int:
    """Subsequent edits store pending data and create a change request."""
    db = await get_db()
    try:
        await db.execute(
            """UPDATE users SET pending_profile_data = ?,
               updated_at = datetime('now') WHERE id = ?""",
            (json.dumps(new_profile), user_id),
        )
        cursor = await db.execute(
            """INSERT INTO profile_change_requests
               (user_id, old_values, new_values, status)
               VALUES (?, ?, ?, 'pending')""",
            (user_id, json.dumps(old_profile or {}), json.dumps(new_profile)),
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def has_pending_request(user_id: int) -> bool:
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT COUNT(*) AS c FROM profile_change_requests
               WHERE user_id = ? AND status = 'pending'""",
            (user_id,),
        )
        row = await cursor.fetchone()
    finally:
        await db.close()
    return (row["c"] if row else 0) > 0


# Change requests ----------------------------------------------------------

def _parse_request(row) -> dict:
    req = dict(row)
    for field in ("old_values", "new_values"):
        raw = req.get(field)
        try:
            req[field] = json.loads(raw) if raw else {}
        except (json.JSONDecodeError, TypeError):
            req[field] = {}
    return req


async def list_change_requests(status: Optional[str] = "pending") -> list:
    query = """SELECT cr.*, u.username AS username, u.mobile AS mobile
               FROM profile_change_requests cr
               JOIN users u ON u.id = cr.user_id"""
    params = []
    if status:
        query += " WHERE cr.status = ?"
        params.append(status)
    query += " ORDER BY cr.requested_at DESC"
    db = await get_db()
    try:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
    finally:
        await db.close()
    return [_parse_request(r) for r in rows]


async def get_change_request(request_id: int) -> Optional[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT cr.*, u.username AS username, u.mobile AS mobile
               FROM profile_change_requests cr
               JOIN users u ON u.id = cr.user_id
               WHERE cr.id = ?""",
            (request_id,),
        )
        row = await cursor.fetchone()
    finally:
        await db.close()
    return _parse_request(row) if row else None


async def list_user_change_requests(user_id: int) -> list:
    """All change requests for one user, newest first (for the user's own view)."""
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT * FROM profile_change_requests
               WHERE user_id = ? ORDER BY requested_at DESC, id DESC""",
            (user_id,),
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()
    return [_parse_request(r) for r in rows]


async def latest_change_request(user_id: int) -> Optional[dict]:
    requests = await list_user_change_requests(user_id)
    return requests[0] if requests else None


async def count_pending_requests() -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT COUNT(*) AS c FROM profile_change_requests WHERE status = 'pending'"
        )
        row = await cursor.fetchone()
    finally:
        await db.close()
    return row["c"] if row else 0


async def approve_change_request(request_id: int, admin_id: int) -> bool:
    """Copy new_values to user's profile_data, clear pending, mark approved."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM profile_change_requests WHERE id = ? AND status = 'pending'",
            (request_id,),
        )
        req = await cursor.fetchone()
        if req is None:
            return False
        await db.execute(
            """UPDATE users SET profile_data = ?, pending_profile_data = NULL,
               profile_submitted = 1, updated_at = datetime('now')
               WHERE id = ?""",
            (req["new_values"], req["user_id"]),
        )
        await db.execute(
            """UPDATE profile_change_requests
               SET status = 'approved', reviewed_by = ?,
                   reviewed_at = datetime('now')
               WHERE id = ?""",
            (admin_id, request_id),
        )
        await db.commit()
        return True
    finally:
        await db.close()


async def reject_change_request(request_id: int, admin_id: int,
                               reason: str) -> bool:
    """Mark rejected, clear pending data, record reason and reviewer."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM profile_change_requests WHERE id = ? AND status = 'pending'",
            (request_id,),
        )
        req = await cursor.fetchone()
        if req is None:
            return False
        await db.execute(
            """UPDATE users SET pending_profile_data = NULL,
               updated_at = datetime('now') WHERE id = ?""",
            (req["user_id"],),
        )
        await db.execute(
            """UPDATE profile_change_requests
               SET status = 'rejected', rejection_reason = ?, reviewed_by = ?,
                   reviewed_at = datetime('now')
               WHERE id = ?""",
            (reason, admin_id, request_id),
        )
        await db.commit()
        return True
    finally:
        await db.close()
