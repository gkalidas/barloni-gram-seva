"""Configurable multi-level approval engine (deferred execution).

A superadmin sets, per action, how much approval it needs:
  'none'       -> any admin does it immediately
  '2' / '3'    -> N distinct admins must approve (the initiator counts as one)
  'superadmin' -> a superadmin must approve

A gated action does NOT run when triggered: it creates a pending approval
request that stores the intended change (payload), and the change is executed
only once the requirement is met. A superadmin approval overrides any policy.
"""
import json
import os
from typing import Optional

from app.database import get_db

# Actions that can be put behind approval, in display order.
GATEABLE_ACTIONS = [
    ("user.delete", "Delete a user"),
    ("scheme.delete", "Delete a scheme"),
    ("user.role", "Change a user's role"),
    ("user.active", "Activate / deactivate a user"),
    ("user.reset_password", "Reset a user's password"),
    # Phase 2 — content edits.
    ("scheme.create", "Add a scheme"),
    ("scheme.update", "Edit a scheme"),
    ("official.create", "Add an official"),
    ("official.update", "Edit an official"),
    ("official.delete", "Remove an official"),
]
ACTION_LABELS = dict(GATEABLE_ACTIONS)

LEVELS = [
    ("none", "No approval (any admin)"),
    ("2", "Two admins"),
    ("3", "Three admins"),
    ("superadmin", "Superadmin"),
]
LEVEL_KEYS = {k for k, _ in LEVELS}


# --- policy ----------------------------------------------------------------

async def get_level(action_key: str) -> str:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT level FROM approval_policy WHERE action_key = ?", (action_key,))
        row = await cursor.fetchone()
    finally:
        await db.close()
    return row["level"] if row else "none"


async def set_level(action_key: str, level: str) -> None:
    if action_key not in ACTION_LABELS or level not in LEVEL_KEYS:
        return
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO approval_policy (action_key, level) VALUES (?, ?)
               ON CONFLICT(action_key) DO UPDATE SET level = excluded.level""",
            (action_key, level))
        await db.commit()
    finally:
        await db.close()


async def list_policy() -> list:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT action_key, level FROM approval_policy")
        existing = {r["action_key"]: r["level"] for r in await cursor.fetchall()}
    finally:
        await db.close()
    return [
        {"action_key": k, "label": label, "level": existing.get(k, "none")}
        for k, label in GATEABLE_ACTIONS
    ]


# --- the executor: performs an approved action -----------------------------

def _remove_files(paths) -> None:
    for p in paths or []:
        if not p:
            continue
        try:
            os.remove(p)
        except OSError:
            pass


async def _execute(action_key: str, payload: dict) -> None:
    from app.services import user_service, scheme_service, officials_service
    if action_key == "user.delete":
        _remove_files(await user_service.delete_user(payload["user_id"]))
    elif action_key == "scheme.delete":
        _remove_files(await scheme_service.delete_scheme(payload["scheme_id"]))
    elif action_key == "user.role":
        await user_service.update_role(payload["user_id"], payload["role"])
    elif action_key == "user.active":
        await user_service.set_active(payload["user_id"], bool(payload["active"]))
    elif action_key == "user.reset_password":
        await user_service.set_password_hash(payload["user_id"], payload["password_hash"])
    # --- Phase 2: content edits ---
    elif action_key == "scheme.create":
        await scheme_service.create_scheme(payload["data"])
    elif action_key == "scheme.update":
        await scheme_service.update_scheme(payload["scheme_id"], payload["data"])
    elif action_key == "official.create":
        await officials_service.create_official(payload["data"])
    elif action_key == "official.update":
        await officials_service.update_official(payload["official_id"], payload["data"])
    elif action_key == "official.delete":
        photo = await officials_service.delete_official(payload["official_id"])
        if photo:
            officials_service.delete_photo(photo)


# --- requests & votes ------------------------------------------------------

async def guard(actor: dict, action_key: str, payload: dict, detail: str) -> dict:
    """Either execute immediately (policy 'none') or open an approval request.

    Returns {"executed": bool, "request_id": int|None}.
    """
    level = await get_level(action_key)
    if level == "none":
        await _execute(action_key, payload)
        await _log(actor, action_key, detail, None)
        return {"executed": True, "request_id": None}

    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO approval_requests
               (action_key, payload, detail, required, initiated_by, initiated_by_username)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (action_key, json.dumps(payload), detail, level,
             actor.get("id"), actor.get("username")))
        request_id = cursor.lastrowid
        await db.commit()
    finally:
        await db.close()

    # The initiator's action counts as their approval.
    await _add_vote(request_id, actor, "approve")
    executed = await _resolve(request_id)
    # If it ran straight away (e.g. a superadmin's own action satisfied the
    # policy), the initiator already saw the outcome — don't also queue them a
    # "your action was approved" notice.
    if executed:
        await _mark_seen_one(request_id)
    await _log(actor, "approval.request",
               f"Requested approval: {detail}", request_id)
    return {"executed": executed, "request_id": request_id}


async def _add_vote(request_id: int, voter: dict, vote: str) -> None:
    db = await get_db()
    try:
        await db.execute(
            """INSERT OR IGNORE INTO approval_votes
               (request_id, voter_id, voter_username, voter_role, vote)
               VALUES (?, ?, ?, ?, ?)""",
            (request_id, voter.get("id"), voter.get("username"),
             voter.get("role"), vote))
        await db.commit()
    finally:
        await db.close()


async def _resolve(request_id: int) -> bool:
    """Apply the request if its requirement is now satisfied. Returns executed."""
    req = await get_request(request_id)
    if req is None or req["status"] != "pending":
        return False
    votes = req["votes"]
    if any(v["vote"] == "reject" for v in votes):
        await _set_status(request_id, "rejected")
        return False

    approvers = [v for v in votes if v["vote"] == "approve"]
    required = req["required"]
    superadmin_approved = any(v["voter_role"] == "superadmin" for v in approvers)
    satisfied = False
    if superadmin_approved:               # superadmin overrides any policy
        satisfied = True
    elif required == "superadmin":
        satisfied = False                 # needs a superadmin (handled above)
    elif required in ("2", "3"):
        satisfied = len({v["voter_id"] for v in approvers}) >= int(required)

    if satisfied:
        try:
            await _execute(req["action_key"], json.loads(req["payload"] or "{}"))
        except Exception as exc:  # don't lose the request on an executor error
            await _set_status(request_id, "rejected", f"Execution failed: {exc}")
            return False
        await _set_status(request_id, "approved")
        return True
    return False


async def vote(request_id: int, voter: dict, approve: bool, note: str = "") -> dict:
    req = await get_request(request_id)
    if req is None or req["status"] != "pending":
        return {"ok": False, "executed": False}
    await _add_vote(request_id, voter, "approve" if approve else "reject")
    if not approve and note:
        await _set_note(request_id, note)
    executed = await _resolve(request_id)
    final = await get_request(request_id)
    await _log(voter, "approval.vote",
               f"{'Approved' if approve else 'Rejected'}: {req['detail']}", request_id)
    return {"ok": True, "executed": executed, "status": final["status"]}


async def _set_status(request_id: int, status: str, note: str = "") -> None:
    db = await get_db()
    try:
        await db.execute(
            """UPDATE approval_requests
               SET status = ?, resolved_at = datetime('now'),
                   resolved_note = COALESCE(NULLIF(?, ''), resolved_note)
               WHERE id = ?""",
            (status, note, request_id))
        await db.commit()
    finally:
        await db.close()


async def _set_note(request_id: int, note: str) -> None:
    db = await get_db()
    try:
        await db.execute(
            "UPDATE approval_requests SET resolved_note = ? WHERE id = ?",
            (note, request_id))
        await db.commit()
    finally:
        await db.close()


async def get_request(request_id: int) -> Optional[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM approval_requests WHERE id = ?", (request_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        req = dict(row)
        cursor = await db.execute(
            "SELECT * FROM approval_votes WHERE request_id = ? ORDER BY id ASC",
            (request_id,))
        req["votes"] = [dict(v) for v in await cursor.fetchall()]
    finally:
        await db.close()
    req["label"] = ACTION_LABELS.get(req["action_key"], req["action_key"])
    req["approvals"] = len({v["voter_id"] for v in req["votes"] if v["vote"] == "approve"})
    return req


async def list_requests(status: Optional[str] = "pending") -> list:
    query = "SELECT * FROM approval_requests"
    params = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY id DESC"
    db = await get_db()
    try:
        cursor = await db.execute(query, params)
        rows = [dict(r) for r in await cursor.fetchall()]
    finally:
        await db.close()
    out = []
    for r in rows:
        full = await get_request(r["id"])
        out.append(full)
    return out


async def count_pending() -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT COUNT(*) AS c FROM approval_requests WHERE status = 'pending'")
        row = await cursor.fetchone()
    finally:
        await db.close()
    return row["c"] if row else 0


# --- initiator notices (in-app "your action was approved/rejected") --------

async def _mark_seen_one(request_id: int) -> None:
    db = await get_db()
    try:
        await db.execute(
            "UPDATE approval_requests SET initiator_seen = 1 WHERE id = ?",
            (request_id,))
        await db.commit()
    finally:
        await db.close()


async def notices_for(user_id: int) -> list:
    """Resolved requests this user initiated that they haven't been shown yet."""
    if not user_id:
        return []
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT * FROM approval_requests
               WHERE initiated_by = ? AND status IN ('approved', 'rejected')
                 AND COALESCE(initiator_seen, 0) = 0
               ORDER BY resolved_at DESC, id DESC""",
            (user_id,))
        rows = [dict(r) for r in await cursor.fetchall()]
    finally:
        await db.close()
    for r in rows:
        r["label"] = ACTION_LABELS.get(r["action_key"], r["action_key"])
    return rows


async def mark_notices_seen(user_id: int) -> None:
    """Mark all of a user's resolved-request notices as seen."""
    if not user_id:
        return
    db = await get_db()
    try:
        await db.execute(
            """UPDATE approval_requests SET initiator_seen = 1
               WHERE initiated_by = ? AND status IN ('approved', 'rejected')""",
            (user_id,))
        await db.commit()
    finally:
        await db.close()


async def _log(actor, action, detail, request_id) -> None:
    try:
        from app.services import activity_service
        await activity_service.log(actor, action, detail, "approval_request", request_id)
    except Exception:
        pass
