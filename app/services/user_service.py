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


async def update_password(user_id: int, new_password: str) -> None:
    db = await get_db()
    try:
        await db.execute(
            "UPDATE users SET password_hash = ?, updated_at = datetime('now') WHERE id = ?",
            (hash_password(new_password), user_id),
        )
        await db.commit()
    finally:
        await db.close()


async def update_role(user_id: int, role: str) -> None:
    db = await get_db()
    try:
        await db.execute(
            "UPDATE users SET role = ?, updated_at = datetime('now') WHERE id = ?",
            (role, user_id),
        )
        await db.commit()
    finally:
        await db.close()


async def set_active(user_id: int, active: bool) -> None:
    db = await get_db()
    try:
        await db.execute(
            "UPDATE users SET active = ?, updated_at = datetime('now') WHERE id = ?",
            (1 if active else 0, user_id),
        )
        await db.commit()
    finally:
        await db.close()


async def set_password_hash(user_id: int, password_hash: str) -> None:
    """Set an already-hashed password (used by the deferred approval engine)."""
    db = await get_db()
    try:
        await db.execute(
            "UPDATE users SET password_hash = ?, updated_at = datetime('now') WHERE id = ?",
            (password_hash, user_id),
        )
        await db.commit()
    finally:
        await db.close()


async def count_admins() -> int:
    """Number of active admins/superadmins (for last-admin protection)."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT COUNT(*) AS c FROM users WHERE role IN ('admin','superadmin') AND active = 1"
        )
        row = await cursor.fetchone()
    finally:
        await db.close()
    return row["c"] if row else 0


async def delete_user(user_id: int) -> list:
    """Hard-delete a user and all their data. Returns file paths to remove from disk.

    Audit references made by this user elsewhere (who reviewed/changed something)
    are set to NULL so other users' records stay intact.
    """
    db = await get_db()
    paths = []
    try:
        cur = await db.execute(
            "SELECT file_path FROM user_documents WHERE user_id = ? AND file_path IS NOT NULL",
            (user_id,))
        paths += [r["file_path"] for r in await cur.fetchall()]
        cur = await db.execute(
            "SELECT photo_path FROM complaints WHERE user_id = ? AND photo_path IS NOT NULL",
            (user_id,))
        paths += [r["photo_path"] for r in await cur.fetchall()]

        # Detach audit references this user made on other people's records.
        await db.execute("UPDATE complaint_status_history SET changed_by = NULL WHERE changed_by = ?", (user_id,))
        await db.execute("UPDATE profile_change_requests SET reviewed_by = NULL WHERE reviewed_by = ?", (user_id,))
        await db.execute("UPDATE user_documents SET reviewed_by = NULL WHERE reviewed_by = ?", (user_id,))

        # Remove this user's own data (children before parents for FK safety).
        await db.execute(
            "DELETE FROM complaint_status_history WHERE complaint_id IN "
            "(SELECT id FROM complaints WHERE user_id = ?)", (user_id,))
        await db.execute("DELETE FROM complaints WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM user_documents WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM profile_change_requests WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        await db.commit()
    finally:
        await db.close()
    return paths


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


async def sync_seen_schemes(user_id: int, current_ids: list) -> list:
    """Diff the user's currently-eligible scheme ids against what they've been
    shown, persist the new set, and return the *newly* matching ids.

    The first time this runs for a user (column is NULL) we initialise silently
    — no "new match" banner for schemes they already qualified for at sign-up.
    """
    current = sorted({int(i) for i in current_ids})
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT seen_scheme_ids FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        raw = row["seen_scheme_ids"] if row else None
        first_time = raw is None
        try:
            seen = set(json.loads(raw)) if raw else set()
        except (json.JSONDecodeError, TypeError):
            seen = set()
        new_ids = [] if first_time else [i for i in current if i not in seen]
        await db.execute(
            "UPDATE users SET seen_scheme_ids = ? WHERE id = ?",
            (json.dumps(current), user_id))
        await db.commit()
    finally:
        await db.close()
    return new_ids


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
    raw_docs = req.get("required_documents")
    try:
        req["required_documents"] = json.loads(raw_docs) if raw_docs else []
    except (json.JSONDecodeError, TypeError):
        req["required_documents"] = []
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
                               reason: str,
                               required_documents: Optional[list] = None) -> bool:
    """Mark rejected, clear pending data, record reason, requested docs, reviewer."""
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
        docs_json = json.dumps(required_documents) if required_documents else None
        await db.execute(
            """UPDATE profile_change_requests
               SET status = 'rejected', rejection_reason = ?,
                   required_documents = ?, reviewed_by = ?,
                   reviewed_at = datetime('now')
               WHERE id = ?""",
            (reason, docs_json, admin_id, request_id),
        )
        await db.commit()
        return True
    finally:
        await db.close()
