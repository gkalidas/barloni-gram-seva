"""Approval policy (superadmin) and the approvals queue (admins vote)."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import require_admin, require_superadmin
from app.services import approval_service

router = APIRouter()


def _templates(request: Request):
    return request.app.state.templates


# --- superadmin: configure the policy --------------------------------------

@router.get("/admin/approval-policy", response_class=HTMLResponse)
async def approval_policy(request: Request):
    user = await require_superadmin(request)
    return _templates(request).TemplateResponse(request,
        "admin/approval_policy.html",
        {"request": request, "user": user,
         "policy": await approval_service.list_policy(),
         "levels": approval_service.LEVELS})


@router.post("/admin/approval-policy")
async def save_approval_policy(request: Request):
    await require_superadmin(request)
    form = await request.form()
    for action_key, _ in approval_service.GATEABLE_ACTIONS:
        level = (form.get(f"level__{action_key}") or "none").strip()
        await approval_service.set_level(action_key, level)
    return RedirectResponse("/admin/approval-policy?msg=Policy+saved", status_code=303)


# --- admins: the approvals queue -------------------------------------------

@router.get("/admin/approvals", response_class=HTMLResponse)
async def approvals_queue(request: Request, status: str = "pending"):
    user = await require_admin(request)
    requests = await approval_service.list_requests(
        status=status if status != "all" else None)
    return _templates(request).TemplateResponse(request,
        "admin/approvals.html",
        {"request": request, "user": user, "requests": requests, "status": status})


@router.post("/admin/approvals/{request_id}/vote")
async def vote_on_request(request: Request, request_id: int):
    user = await require_admin(request)
    form = await request.form()
    approve = (form.get("decision") or "") == "approve"
    note = (form.get("note") or "").strip()
    result = await approval_service.vote(request_id, user, approve, note)
    if not result["ok"]:
        msg = "Request+not+found+or+already+resolved"
    elif result["executed"]:
        msg = "Approved+and+applied"
    elif result["status"] == "rejected":
        msg = "Request+rejected"
    else:
        msg = "Your+approval+is+recorded+%E2%80%94+more+approvals+needed"
    return RedirectResponse(f"/admin/approvals?msg={msg}", status_code=303)
