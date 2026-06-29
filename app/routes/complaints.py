"""Complaints: public anonymous board + login-gated filing + admin tracking."""
import os

from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response

from app.auth import require_user, require_admin, get_current_user
from app.config import settings
from app.constants import (
    COMPLAINT_CATEGORIES, COMPLAINT_ADMIN_STATUSES,
)
from app.rate_limit import complaint_submissions
from app.services import complaint_service, user_document_service

router = APIRouter()


def _templates(request: Request):
    return request.app.state.templates


# --- public community board (anonymous) ------------------------------------

@router.get("/complaints", response_class=HTMLResponse)
async def board(request: Request, category: str = "", ward: str = "", status: str = ""):
    user = await get_current_user(request)
    complaints = await complaint_service.list_complaints(
        category=category or None, ward=ward or None, status=status or None,
    )
    return _templates(request).TemplateResponse(request,
        "complaints/board.html",
        {
            "request": request, "user": user, "complaints": complaints,
            "categories": COMPLAINT_CATEGORIES, "wards": settings.COMPLAINT_WARDS,
            "category": category, "ward": ward, "status": status,
        },
    )


@router.get("/complaints/new", response_class=HTMLResponse)
async def new_complaint_form(request: Request):
    user = await require_user(request)
    return _templates(request).TemplateResponse(request,
        "complaints/new.html", _new_ctx(request, user))


def _new_ctx(request, user, values=None, flash=None):
    ctx = {
        "request": request, "user": user,
        "categories": COMPLAINT_CATEGORIES, "wards": settings.COMPLAINT_WARDS,
        "values": values or {},
    }
    if flash:
        ctx["flash"] = flash
    return ctx


@router.post("/complaints", response_class=HTMLResponse)
async def create_complaint_submit(
    request: Request,
    category: str = Form(...),
    ward: str = Form(""),
    description: str = Form(...),
    file: UploadFile = File(None),
):
    user = await require_user(request)
    category = (category or "").strip()
    ward = (ward or "").strip()
    description = (description or "").strip()
    values = {"category": category, "ward": ward, "description": description}

    def fail(msg, code=400):
        return _templates(request).TemplateResponse(request,
            "complaints/new.html",
            _new_ctx(request, user, values, flash=("error", msg)), status_code=code)

    if complaint_submissions.is_blocked(str(user["id"])):
        return fail("You have filed several complaints recently. "
                    "Please try again a little later.", code=429)
    if category not in COMPLAINT_CATEGORIES:
        return fail("Please choose a valid category.")
    if ward and ward not in settings.COMPLAINT_WARDS:
        return fail("Please choose a valid ward/area.")
    if not description:
        return fail("Please describe the issue.")

    photo_path = None
    if file is not None and file.filename:
        content = await file.read()
        if not user_document_service.is_allowed_file(file.filename):
            return fail("Photo must be one of: "
                        f"{', '.join(sorted(user_document_service.ALLOWED_EXTENSIONS))}.")
        if len(content) > user_document_service.MAX_FILE_BYTES:
            mb = user_document_service.MAX_FILE_BYTES // (1024 * 1024)
            return fail(f"Photo is too large (max {mb} MB).")
        if content:
            photo_path = complaint_service.save_photo(file.filename, content)

    complaint_id = await complaint_service.create_complaint(
        user["id"], category, ward, description, photo_path)
    complaint_submissions.record(str(user["id"]))
    return RedirectResponse(
        f"/complaints/{complaint_id}?msg=Complaint+filed+%E2%80%94+thank+you",
        status_code=303)


@router.get("/my/complaints", response_class=HTMLResponse)
async def my_complaints(request: Request):
    user = await require_user(request)
    complaints = await complaint_service.list_complaints(user_id=user["id"])
    return _templates(request).TemplateResponse(request,
        "complaints/my.html",
        {"request": request, "user": user, "complaints": complaints})


@router.post("/complaints/{complaint_id}/withdraw")
async def withdraw(request: Request, complaint_id: int):
    user = await require_user(request)
    ok = await complaint_service.withdraw_complaint(complaint_id, user["id"])
    msg = "Complaint+withdrawn" if ok else "Could+not+withdraw+this+complaint"
    return RedirectResponse(f"/my/complaints?msg={msg}", status_code=303)


@router.get("/complaints/{complaint_id}/photo")
async def complaint_photo(request: Request, complaint_id: int):
    # Public: the board is public, and a complaint photo is issue evidence.
    complaint = await complaint_service.get_complaint(complaint_id)
    if not complaint or not complaint.get("photo_path"):
        return Response("Not found", status_code=404)
    if not os.path.isfile(complaint["photo_path"]):
        return Response("File missing", status_code=404)
    return FileResponse(complaint["photo_path"], content_disposition_type="inline")


@router.get("/complaints/{complaint_id}", response_class=HTMLResponse)
async def complaint_detail(request: Request, complaint_id: int):
    user = await get_current_user(request)
    complaint = await complaint_service.get_complaint(complaint_id)
    if complaint is None:
        return RedirectResponse("/complaints", status_code=303)
    history = await complaint_service.list_status_history(complaint_id)
    is_owner = bool(user and user["id"] == complaint["user_id"])
    if is_owner and complaint.get("filer_unseen"):
        await complaint_service.mark_seen(complaint_id, user["id"])
    return _templates(request).TemplateResponse(request,
        "complaints/detail.html",
        {
            "request": request, "user": user, "complaint": complaint,
            "history": history, "is_owner": is_owner,
        },
    )


# --- admin -----------------------------------------------------------------

@router.get("/admin/complaints", response_class=HTMLResponse)
async def admin_complaints(request: Request, category: str = "",
                           ward: str = "", status: str = ""):
    admin = await require_admin(request)
    complaints = await complaint_service.list_complaints_admin(
        category=category or None, ward=ward or None, status=status or None)
    return _templates(request).TemplateResponse(request,
        "admin/complaints.html",
        {
            "request": request, "user": admin, "complaints": complaints,
            "categories": COMPLAINT_CATEGORIES, "wards": settings.COMPLAINT_WARDS,
            "category": category, "ward": ward, "status": status,
        },
    )


@router.get("/admin/complaints/analytics", response_class=HTMLResponse)
async def admin_complaint_analytics(request: Request):
    admin = await require_admin(request)
    stats = await complaint_service.complaint_stats()
    matrix = {}
    for r in stats["matrix_rows"]:
        matrix.setdefault(r["ward"], {})[r["category"]] = r["c"]
    return _templates(request).TemplateResponse(request,
        "admin/complaint_analytics.html",
        {
            "request": request, "user": admin, "stats": stats,
            "matrix": matrix, "wards": sorted(matrix.keys()),
            "categories": COMPLAINT_CATEGORIES,
        },
    )


@router.get("/admin/complaints/{complaint_id}", response_class=HTMLResponse)
async def admin_complaint_detail(request: Request, complaint_id: int):
    admin = await require_admin(request)
    complaint = await complaint_service.get_complaint_with_filer(complaint_id)
    if complaint is None:
        return RedirectResponse("/admin/complaints", status_code=303)
    history = await complaint_service.list_status_history(complaint_id)
    return _templates(request).TemplateResponse(request,
        "admin/complaint_detail.html",
        {
            "request": request, "user": admin, "complaint": complaint,
            "history": history, "statuses": COMPLAINT_ADMIN_STATUSES,
        },
    )


@router.post("/admin/complaints/{complaint_id}/status")
async def admin_update_status(request: Request, complaint_id: int):
    admin = await require_admin(request)
    form = await request.form()
    new_status = (form.get("status") or "").strip()
    note = (form.get("note") or "").strip()
    if new_status not in COMPLAINT_ADMIN_STATUSES:
        return RedirectResponse(
            f"/admin/complaints/{complaint_id}?msg=Choose+a+valid+status",
            status_code=303)
    await complaint_service.update_status(complaint_id, admin["id"], new_status, note)
    return RedirectResponse(
        f"/admin/complaints/{complaint_id}?msg=Status+updated", status_code=303)
