"""User routes: dashboard, profile view/edit, eligible schemes, document locker."""
import os
from datetime import date, datetime

from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response

from app.auth import require_user
from app.services import (
    user_service, scheme_service, eligibility_service,
    document_service, user_document_service,
)
from app.constants import GENDERS, CASTE_CATEGORIES, OCCUPATIONS, LAND_OWNERSHIP

router = APIRouter()


def _templates(request: Request):
    return request.app.state.templates


def _calc_age(dob_str: str):
    try:
        dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    today = date.today()
    return today.year - dob.year - (
        (today.month, today.day) < (dob.month, dob.day)
    )


def _to_float(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _to_int(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _parse_profile_form(form) -> tuple:
    """Build a profile dict from raw form data. Returns (profile, errors)."""
    errors = []

    full_name = (form.get("full_name") or "").strip()
    date_of_birth = (form.get("date_of_birth") or "").strip()
    gender = (form.get("gender") or "").strip()
    state = (form.get("state") or "").strip()
    district = (form.get("district") or "").strip()
    village = (form.get("village") or "").strip()
    caste_category = (form.get("caste_category") or "").strip()
    occupation = (form.get("occupation") or "").strip()
    land_ownership = (form.get("land_ownership") or "").strip()

    if not full_name:
        errors.append("Full name is required.")
    age = _calc_age(date_of_birth)
    if age is None:
        errors.append("A valid date of birth is required.")
    if gender not in GENDERS:
        errors.append("Please select a valid gender.")
    if not state:
        errors.append("State is required.")
    if not district:
        errors.append("District is required.")
    if not village:
        errors.append("Village is required.")
    if caste_category not in CASTE_CATEGORIES:
        errors.append("Please select a valid caste category.")
    if occupation not in OCCUPATIONS:
        errors.append("Please select a valid occupation.")
    if land_ownership not in LAND_OWNERSHIP:
        errors.append("Please select a valid land ownership type.")

    income = _to_float(form.get("annual_family_income"))
    if income is None or income < 0:
        errors.append("A valid annual family income is required.")

    family_size = _to_int(form.get("family_size"))
    if family_size is None or family_size < 1:
        errors.append("Family size must be at least 1.")

    land_area = _to_float(form.get("land_area_acres"))
    if land_ownership == "landless":
        land_area = 0.0

    profile = {
        "full_name": full_name,
        "date_of_birth": date_of_birth,
        "age": age,
        "gender": gender,
        "state": state,
        "district": district,
        "village": village,
        "caste_category": caste_category.upper() if caste_category else "",
        "bpl_card": form.get("bpl_card") == "on",
        "annual_family_income": income,
        "occupation": occupation,
        "land_ownership": land_ownership,
        "land_area_acres": land_area,
        "family_size": family_size,
        "has_disability": form.get("has_disability") == "on",
        "bank_account_aadhaar_linked": form.get("bank_account_aadhaar_linked") == "on",
    }
    return profile, errors


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = await require_user(request)
    profile = user_service.get_profile(user)
    eligible_count = 0
    if profile:
        schemes = await scheme_service.list_schemes(only_active=True)
        eligible_count = len(
            eligibility_service.matching_schemes(profile, schemes)
        )
    pending = await user_service.has_pending_request(user["id"])
    latest_request = await user_service.latest_change_request(user["id"])
    return _templates(request).TemplateResponse(request,
        "user/dashboard.html",
        {
            "request": request,
            "user": user,
            "profile": profile,
            "profile_submitted": bool(user.get("profile_submitted")),
            "eligible_count": eligible_count,
            "has_pending": pending,
            "latest_request": latest_request,
        },
    )


@router.get("/profile", response_class=HTMLResponse)
async def view_profile(request: Request):
    user = await require_user(request)
    profile = user_service.get_profile(user)
    pending_profile = user_service.get_pending_profile(user)
    return _templates(request).TemplateResponse(request,
        "user/profile.html",
        {
            "request": request,
            "user": user,
            "profile": profile,
            "pending_profile": pending_profile,
            "has_pending": await user_service.has_pending_request(user["id"]),
            "change_requests": await user_service.list_user_change_requests(user["id"]),
        },
    )


@router.get("/profile/edit", response_class=HTMLResponse)
async def edit_profile_form(request: Request):
    user = await require_user(request)
    profile = user_service.get_profile(user)
    first_time = not bool(user.get("profile_submitted"))
    has_pending = await user_service.has_pending_request(user["id"])
    return _templates(request).TemplateResponse(request, 
        "user/profile_edit.html",
        {
            "request": request,
            "user": user,
            "profile": profile or {},
            "first_time": first_time,
            "has_pending": has_pending,
            "genders": GENDERS,
            "caste_categories": CASTE_CATEGORIES,
            "occupations": OCCUPATIONS,
            "land_ownership_options": LAND_OWNERSHIP,
        },
    )


@router.post("/profile/edit", response_class=HTMLResponse)
async def edit_profile_submit(request: Request):
    user = await require_user(request)
    form = await request.form()
    profile, errors = _parse_profile_form(form)
    first_time = not bool(user.get("profile_submitted"))

    if errors:
        return _templates(request).TemplateResponse(request, 
            "user/profile_edit.html",
            {
                "request": request,
                "user": user,
                "profile": profile,
                "first_time": first_time,
                "has_pending": await user_service.has_pending_request(user["id"]),
                "genders": GENDERS,
                "caste_categories": CASTE_CATEGORIES,
                "occupations": OCCUPATIONS,
                "land_ownership_options": LAND_OWNERSHIP,
                "flash": ("error", " ".join(errors)),
            },
            status_code=400,
        )

    if first_time:
        await user_service.submit_first_profile(user["id"], profile)
        return RedirectResponse(
            "/dashboard?msg=Profile+saved+successfully", status_code=303
        )

    # Subsequent edit -> change request
    if await user_service.has_pending_request(user["id"]):
        return RedirectResponse(
            "/profile?msg=You+already+have+a+pending+change+request",
            status_code=303,
        )
    old_profile = user_service.get_profile(user)
    await user_service.request_profile_change(user["id"], old_profile, profile)
    return RedirectResponse(
        "/profile?msg=Change+request+submitted+for+admin+approval",
        status_code=303,
    )


@router.get("/my-schemes", response_class=HTMLResponse)
async def my_schemes(request: Request):
    user = await require_user(request)
    profile = user_service.get_profile(user)
    eligible = []
    if profile:
        schemes = await scheme_service.list_schemes(only_active=True)
        eligible = eligibility_service.matching_schemes(profile, schemes)
    return _templates(request).TemplateResponse(request,
        "user/eligibility.html",
        {
            "request": request,
            "user": user,
            "profile": profile,
            "schemes": eligible,
        },
    )


# --- Document locker -------------------------------------------------------

async def _documents_context(request, user, flash=None):
    docs = await user_document_service.list_user_documents(user["id"])
    have = {d["document_name"] for d in docs}
    master = await document_service.list_documents()
    # Documents the admin asked for in the most recent rejected change request.
    latest = await user_service.latest_change_request(user["id"])
    requested = (
        latest["required_documents"]
        if latest and latest.get("status") == "rejected" else []
    )
    ctx = {
        "request": request,
        "user": user,
        "documents": docs,
        "have": have,
        "master": master,
        "requested": requested,
        "allowed_ext": ", ".join(sorted(user_document_service.ALLOWED_EXTENSIONS)),
        "max_mb": user_document_service.MAX_FILE_BYTES // (1024 * 1024),
    }
    if flash:
        ctx["flash"] = flash
    return ctx


@router.get("/documents", response_class=HTMLResponse)
async def documents_page(request: Request):
    user = await require_user(request)
    ctx = await _documents_context(request, user)
    return _templates(request).TemplateResponse(request, "user/documents.html", ctx)


@router.post("/documents", response_class=HTMLResponse)
async def upload_document(
    request: Request,
    document_name: str = Form(...),
    doc_number: str = Form(""),
    file: UploadFile = File(...),
):
    user = await require_user(request)
    document_name = document_name.strip()
    doc_number = doc_number.strip()

    master_names = {d["name"] for d in await document_service.list_documents()}
    content = await file.read()

    error = None
    if document_name not in master_names:
        error = "Please choose a document from the list."
    elif not file.filename or not user_document_service.is_allowed_file(file.filename):
        error = f"File must be one of: {', '.join(sorted(user_document_service.ALLOWED_EXTENSIONS))}."
    elif not content:
        error = "The uploaded file is empty."
    elif len(content) > user_document_service.MAX_FILE_BYTES:
        mb = user_document_service.MAX_FILE_BYTES // (1024 * 1024)
        error = f"File is too large (max {mb} MB)."

    if error:
        ctx = await _documents_context(request, user, flash=("error", error))
        return _templates(request).TemplateResponse(
            request, "user/documents.html", ctx, status_code=400,
        )

    path = user_document_service.save_file(user["id"], file.filename, content)
    _, old_path = await user_document_service.upsert_pending(
        user["id"], document_name, doc_number, path,
    )
    if old_path and old_path != path:
        user_document_service.delete_file(old_path)
    return RedirectResponse(
        "/documents?msg=Document+uploaded+and+sent+for+approval", status_code=303,
    )


@router.post("/documents/{doc_id}/delete")
async def delete_document(request: Request, doc_id: int):
    user = await require_user(request)
    old_path = await user_document_service.delete_user_document(doc_id, user["id"])
    if old_path:
        user_document_service.delete_file(old_path)
    return RedirectResponse("/documents?msg=Document+removed", status_code=303)


@router.get("/documents/file/{doc_id}")
async def serve_document_file(request: Request, doc_id: int):
    user = await require_user(request)
    doc = await user_document_service.get_user_document(doc_id)
    if not doc or not doc.get("file_path"):
        return Response("Not found", status_code=404)
    # Only the owner or an admin may view the file.
    if doc["user_id"] != user["id"] and user.get("role") != "admin":
        return Response("Forbidden", status_code=403)
    if not os.path.isfile(doc["file_path"]):
        return Response("File missing", status_code=404)
    return FileResponse(doc["file_path"])
