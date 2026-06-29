"""Responsible people directory: public hierarchy page + admin CRUD."""
import os

from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response

from app.auth import require_admin, get_current_user
from app.config import settings
from app.constants import COMPLAINT_CATEGORIES
from app.services import officials_service, user_document_service, import_export_service

router = APIRouter()


def _templates(request: Request):
    return request.app.state.templates


# --- public ----------------------------------------------------------------

@router.get("/officials", response_class=HTMLResponse)
async def officials_page(request: Request):
    user = await get_current_user(request)
    officials = await officials_service.list_officials()
    return _templates(request).TemplateResponse(request,
        "officials/public.html",
        {"request": request, "user": user, "officials": officials})


@router.get("/officials/{official_id}/photo")
async def official_photo(request: Request, official_id: int):
    official = await officials_service.get_official(official_id)
    if not official or not official.get("photo_path"):
        return Response("Not found", status_code=404)
    if not os.path.isfile(official["photo_path"]):
        return Response("File missing", status_code=404)
    return FileResponse(official["photo_path"], content_disposition_type="inline")


# --- admin -----------------------------------------------------------------

def _admin_ctx(request, user, official=None, action="/admin/officials/add", flash=None):
    ctx = {
        "request": request, "user": user, "official": official, "action": action,
        "wards": settings.COMPLAINT_WARDS, "departments": COMPLAINT_CATEGORIES,
    }
    if flash:
        ctx["flash"] = flash
    return ctx


def _parse_form(form) -> tuple:
    """Return (data, errors). Does not handle the photo (caller does)."""
    errors = []
    name = (form.get("name") or "").strip()
    if not name:
        errors.append("Name is required.")
    try:
        level = int(form.get("level") or 2)
    except ValueError:
        level = 2
    level = max(1, level)
    ward = (form.get("ward") or "").strip()
    if ward and ward not in settings.COMPLAINT_WARDS:
        errors.append("Invalid ward.")
    department = (form.get("department") or "").strip()
    if department and department not in COMPLAINT_CATEGORIES:
        errors.append("Invalid department.")
    data = {
        "name": name,
        "designation": (form.get("designation") or "").strip() or None,
        "level": level,
        "ward": ward or None,
        "department": department or None,
        "phone": (form.get("phone") or "").strip() or None,
        "email": (form.get("email") or "").strip() or None,
        "office_address": (form.get("office_address") or "").strip() or None,
        "office_hours": (form.get("office_hours") or "").strip() or None,
    }
    return data, errors


async def _photo_from_form(form):
    """Return (photo_path_or_None, error_or_None) for an uploaded photo."""
    file = form.get("photo")
    if file is None or not getattr(file, "filename", ""):
        return None, None
    if not user_document_service.is_allowed_file(file.filename):
        return None, "Photo must be jpg, jpeg, png or pdf."
    content = await file.read()
    if len(content) > user_document_service.MAX_FILE_BYTES:
        mb = user_document_service.MAX_FILE_BYTES // (1024 * 1024)
        return None, f"Photo is too large (max {mb} MB)."
    if not content:
        return None, None
    return officials_service.save_photo(file.filename, content), None


async def _render_officials(request, user, import_result=None):
    officials = await officials_service.list_officials()
    return _templates(request).TemplateResponse(request,
        "admin/officials.html",
        {"request": request, "user": user, "officials": officials,
         "import_result": import_result})


@router.get("/admin/officials", response_class=HTMLResponse)
async def admin_officials(request: Request):
    user = await require_admin(request)
    return await _render_officials(request, user)


def _csv_response(content: str, filename: str) -> Response:
    return Response(content=content, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/admin/officials/export.csv")
async def export_officials_route(request: Request):
    await require_admin(request)
    return _csv_response(await import_export_service.export_officials_csv(), "officials.csv")


@router.get("/admin/officials/template.csv")
async def template_officials_route(request: Request):
    await require_admin(request)
    return _csv_response(import_export_service.officials_template_csv(), "officials-template.csv")


@router.post("/admin/officials/import", response_class=HTMLResponse)
async def import_officials_route(request: Request, file: UploadFile = File(...)):
    user = await require_admin(request)
    raw = await file.read()
    if not raw:
        return await _render_officials(request, user, {"error": "No file uploaded."})
    summary = await import_export_service.import_officials(raw)
    return await _render_officials(request, user, summary)


@router.get("/admin/officials/add", response_class=HTMLResponse)
async def add_official_form(request: Request):
    user = await require_admin(request)
    return _templates(request).TemplateResponse(request,
        "admin/official_form.html", _admin_ctx(request, user))


@router.post("/admin/officials/add", response_class=HTMLResponse)
async def add_official_submit(request: Request):
    user = await require_admin(request)
    form = await request.form()
    data, errors = _parse_form(form)
    photo_path, perr = await _photo_from_form(form)
    if perr:
        errors.append(perr)
    if errors:
        return _templates(request).TemplateResponse(request,
            "admin/official_form.html",
            _admin_ctx(request, user, data, flash=("error", " ".join(errors))),
            status_code=400)
    data["photo_path"] = photo_path
    await officials_service.create_official(data)
    return RedirectResponse("/admin/officials?msg=Official+added", status_code=303)


@router.get("/admin/officials/{official_id}/edit", response_class=HTMLResponse)
async def edit_official_form(request: Request, official_id: int):
    user = await require_admin(request)
    official = await officials_service.get_official(official_id)
    if official is None:
        return RedirectResponse("/admin/officials", status_code=303)
    return _templates(request).TemplateResponse(request,
        "admin/official_form.html",
        _admin_ctx(request, user, official, f"/admin/officials/{official_id}/edit"))


@router.post("/admin/officials/{official_id}/edit", response_class=HTMLResponse)
async def edit_official_submit(request: Request, official_id: int):
    user = await require_admin(request)
    existing = await officials_service.get_official(official_id)
    if existing is None:
        return RedirectResponse("/admin/officials", status_code=303)
    form = await request.form()
    data, errors = _parse_form(form)
    new_photo, perr = await _photo_from_form(form)
    if perr:
        errors.append(perr)
    if errors:
        merged = {**existing, **data}
        return _templates(request).TemplateResponse(request,
            "admin/official_form.html",
            _admin_ctx(request, user, merged, f"/admin/officials/{official_id}/edit",
                       flash=("error", " ".join(errors))),
            status_code=400)
    if new_photo:
        data["photo_path"] = new_photo
        if existing.get("photo_path") and existing["photo_path"] != new_photo:
            officials_service.delete_photo(existing["photo_path"])
    else:
        data["photo_path"] = existing.get("photo_path")
    await officials_service.update_official(official_id, data)
    return RedirectResponse("/admin/officials?msg=Official+updated", status_code=303)


@router.post("/admin/officials/{official_id}/delete")
async def delete_official_route(request: Request, official_id: int):
    await require_admin(request)
    photo = await officials_service.delete_official(official_id)
    if photo:
        officials_service.delete_photo(photo)
    return RedirectResponse("/admin/officials?msg=Official+removed", status_code=303)
