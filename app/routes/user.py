"""User routes: dashboard, profile view/edit, eligible schemes, document locker."""
import os
import re
from datetime import date, datetime

from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response

from app.auth import require_user, verify_password, is_admin, password_problems
from app.config import settings
from app.services import (
    user_service, scheme_service, eligibility_service,
    document_service, user_document_service, complaint_service,
)
from app.constants import GENDERS, CASTE_CATEGORIES, OCCUPATIONS, LAND_OWNERSHIP
from app.rate_limit import complaint_submissions

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
    ward_no = (form.get("ward_no") or "").strip()

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
    if ward_no and ward_no not in settings.COMPLAINT_WARDS:
        errors.append("Please select a valid ward.")

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
        "ward_no": ward_no,
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
    complaint_updates = await complaint_service.count_unseen_for_user(user["id"])
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
            "complaint_updates": complaint_updates,
        },
    )


def _friendly_doc_filename(doc: dict, full_name: str = None) -> str:
    """A human-readable file name for a document, e.g. 'Aadhaar-card_Ramesh-Kumar.jpg'.

    Used only for presentation (download / share) — the file is stored on disk
    under a random UUID, so no name or number ever touches the filesystem path.
    Filesystem-unsafe characters and whitespace are replaced with hyphens.
    """
    parts = [doc.get("document_name") or "document"]
    if full_name:
        parts.append(full_name)
    base = re.sub(r'[\\/:*?"<>|\s]+', "-", "_".join(parts)).strip("-_") or "document"
    ext = os.path.splitext(doc.get("file_path") or "")[1] or ".dat"
    return f"{base}{ext}"


def _build_share(profile: dict, approved_docs: list) -> dict:
    """Build the text + file list shared to WhatsApp from the user's profile."""
    income = profile.get("annual_family_income") or 0
    lines = [
        f"*{profile.get('full_name', '')}* — {settings.VILLAGE_NAME} {settings.APP_NAME}",
        f"Age: {profile.get('age', '')}",
        f"Gender: {(profile.get('gender') or '').title()}",
        f"Village: {profile.get('village', '')}, "
        f"{profile.get('district', '')}, {profile.get('state', '')}",
        f"Caste: {(profile.get('caste_category') or '').upper()}",
        f"Occupation: {(profile.get('occupation') or '').replace('_', ' ').title()}",
        f"Annual family income: ₹{income:,.0f}",
        f"BPL card: {'Yes' if profile.get('bpl_card') else 'No'}",
    ]
    if approved_docs:
        lines.append("")
        lines.append("Approved documents:")
        for d in approved_docs:
            num = f" — {d['doc_number']}" if d.get("doc_number") else ""
            lines.append(f"• {d['document_name']}{num}")
    files = [
        {"url": f"/documents/file/{d['id']}",
         "name": _friendly_doc_filename(d, profile.get("full_name"))}
        for d in approved_docs if d.get("file_path")
    ]
    return {"text": "\n".join(lines), "files": files}


@router.get("/profile", response_class=HTMLResponse)
async def view_profile(request: Request):
    user = await require_user(request)
    profile = user_service.get_profile(user)
    pending_profile = user_service.get_pending_profile(user)
    all_docs = await user_document_service.list_user_documents(user["id"])
    approved_docs = [d for d in all_docs if d["status"] == "approved"]
    share_data = _build_share(profile, approved_docs) if profile else None
    return _templates(request).TemplateResponse(request,
        "user/profile.html",
        {
            "request": request,
            "user": user,
            "profile": profile,
            "pending_profile": pending_profile,
            "has_pending": await user_service.has_pending_request(user["id"]),
            "change_requests": await user_service.list_user_change_requests(user["id"]),
            "approved_docs": approved_docs,
            "share_data": share_data,
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
            "wards": settings.COMPLAINT_WARDS,
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
                "wards": settings.COMPLAINT_WARDS,
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
    near_miss = []
    recommendations = []
    if profile:
        schemes = await scheme_service.list_schemes(only_active=True)
        eligible = eligibility_service.matching_schemes(profile, schemes)
        approved = await user_document_service.approved_document_names(user["id"])
        for scheme in eligible:
            required = scheme.get("documents_required") or []
            scheme["docs_total"] = len(required)
            scheme["docs_have"] = sum(1 for d in required if d in approved)
            scheme["docs_missing"] = [d for d in required if d not in approved]
        # Schemes the resident is *close* to qualifying for (partial eligibility),
        # plus the single actions that would unlock the most additional schemes.
        near_miss = eligibility_service.near_miss_schemes(profile, schemes)
        recommendations = eligibility_service.recommend_actions(profile, schemes)
    return _templates(request).TemplateResponse(request,
        "user/eligibility.html",
        {
            "request": request,
            "user": user,
            "profile": profile,
            "schemes": eligible,
            "near_miss": near_miss,
            "recommendations": recommendations,
        },
    )


@router.post("/schemes/{scheme_id}/dispute")
async def dispute_eligibility(request: Request, scheme_id: int,
                              description: str = Form("")):
    """A resident disputes the system's 'not eligible' verdict for a scheme.
    Allowed only when the system actually says they don't qualify."""
    user = await require_user(request)
    scheme = await scheme_service.get_scheme(scheme_id)
    if scheme is None:
        return RedirectResponse("/schemes", status_code=303)

    def back(msg):
        return RedirectResponse(f"/schemes/{scheme_id}?msg={msg}", status_code=303)

    profile = user_service.get_profile(user)
    if not profile:
        return back("Fill+your+profile+before+raising+an+eligibility+dispute")
    # Only allow a dispute when the system's verdict is "not eligible".
    if eligibility_service.evaluate_scheme(profile, scheme.get("eligibility_rules")):
        return back("You+already+qualify+for+this+scheme")
    # One open dispute per scheme is enough.
    existing = await complaint_service.get_user_dispute_for_scheme(user["id"], scheme_id)
    if existing and existing["status"] in ("submitted", "acknowledged", "in_progress"):
        return RedirectResponse(
            f"/complaints/{existing['id']}?msg=You+already+raised+this+dispute",
            status_code=303)
    description = (description or "").strip()
    if not description:
        return back("Please+explain+why+you+believe+you+qualify")
    if complaint_submissions.is_blocked(str(user["id"])):
        return back("You+have+filed+several+requests+recently.+Try+again+later")

    dispute_id = await complaint_service.create_eligibility_dispute(
        user["id"], scheme_id, description)
    complaint_submissions.record(str(user["id"]))
    return RedirectResponse(
        f"/complaints/{dispute_id}?msg=Eligibility+dispute+raised+%E2%80%94+an+admin+will+review+it",
        status_code=303)


# --- Account / password ----------------------------------------------------

@router.get("/account", response_class=HTMLResponse)
async def account_page(request: Request):
    user = await require_user(request)
    return _templates(request).TemplateResponse(request,
        "user/account.html", {"request": request, "user": user})


@router.post("/account/password", response_class=HTMLResponse)
async def change_password(
    request: Request,
    current_password: str = Form(""),
    new_password: str = Form(""),
    confirm_password: str = Form(""),
):
    user = await require_user(request)
    errors = []
    if not verify_password(current_password, user["password_hash"]):
        errors.append("Your current password is incorrect.")
    errors.extend(password_problems(new_password))
    if new_password != confirm_password:
        errors.append("New passwords do not match.")
    if errors:
        return _templates(request).TemplateResponse(request,
            "user/account.html",
            {"request": request, "user": user, "flash": ("error", " ".join(errors))},
            status_code=400)
    await user_service.update_password(user["id"], new_password)
    return RedirectResponse("/account?msg=Password+updated", status_code=303)


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
async def upload_document(request: Request):
    """Upload one or many documents at once.

    Each selected file is paired (by position) with a document type and an
    optional number, so a single submit can send several documents.
    """
    user = await require_user(request)
    form = await request.form()
    # Each upload row submits one document_name, one doc_number and one file,
    # so the three lists line up by position (row index).
    names = form.getlist("document_name")
    numbers = form.getlist("doc_number")
    files = form.getlist("file")

    master_names = {d["name"] for d in await document_service.list_documents()}
    max_bytes = user_document_service.MAX_FILE_BYTES
    mb = max_bytes // (1024 * 1024)

    if not any(getattr(f, "filename", "") for f in files):
        ctx = await _documents_context(
            request, user, flash=("error", "Please choose at least one file to upload."))
        return _templates(request).TemplateResponse(
            request, "user/documents.html", ctx, status_code=400)

    added = 0
    errors = []
    for i, file in enumerate(files):
        # Skip empty file slots (e.g. an extra row left blank) without losing
        # alignment with the name/number lists.
        if not getattr(file, "filename", ""):
            continue
        document_name = (names[i].strip() if i < len(names) else "")
        doc_number = (numbers[i].strip() if i < len(numbers) else "")
        content = await file.read()
        label = document_name or file.filename

        if document_name not in master_names:
            errors.append(f"{label}: please choose a document type from the list.")
        elif not user_document_service.is_allowed_file(file.filename):
            errors.append(f"{label}: file must be one of "
                          f"{', '.join(sorted(user_document_service.ALLOWED_EXTENSIONS))}.")
        elif not content:
            errors.append(f"{label}: the file is empty.")
        elif len(content) > max_bytes:
            errors.append(f"{label}: file is too large (max {mb} MB).")
        else:
            path = user_document_service.save_file(user["id"], file.filename, content)
            _, old_path = await user_document_service.upsert_pending(
                user["id"], document_name, doc_number, path)
            if old_path and old_path != path:
                user_document_service.delete_file(old_path)
            added += 1

    # All failed -> re-render with the errors. Some succeeded -> redirect with a note.
    if added == 0:
        ctx = await _documents_context(request, user, flash=("error", " ".join(errors)))
        return _templates(request).TemplateResponse(
            request, "user/documents.html", ctx, status_code=400)

    msg = f"{added}+document(s)+uploaded+and+sent+for+approval"
    if errors:
        msg += f"+%E2%80%94+{len(errors)}+could+not+be+uploaded"
    return RedirectResponse(f"/documents?msg={msg}", status_code=303)


@router.post("/documents/{doc_id}/delete")
async def delete_document(request: Request, doc_id: int):
    user = await require_user(request)
    old_path = await user_document_service.delete_user_document(doc_id, user["id"])
    if old_path:
        user_document_service.delete_file(old_path)
    return RedirectResponse("/documents?msg=Document+removed", status_code=303)


@router.get("/documents/file/{doc_id}")
async def serve_document_file(request: Request, doc_id: int, download: bool = False):
    user = await require_user(request)
    doc = await user_document_service.get_user_document(doc_id)
    if not doc or not doc.get("file_path"):
        return Response("Not found", status_code=404)
    # Only the owner or an admin may view the file.
    if doc["user_id"] != user["id"] and not is_admin(user):
        return Response("Forbidden", status_code=403)
    if not os.path.isfile(doc["file_path"]):
        return Response("File missing", status_code=404)
    # Serve with a human-readable name (storage stays a random UUID on disk).
    # ?download=1 forces a download; otherwise it opens inline in the browser.
    owner = await user_service.get_user_by_id(doc["user_id"])
    owner_profile = user_service.get_profile(owner) if owner else None
    full_name = owner_profile.get("full_name") if owner_profile else None
    filename = _friendly_doc_filename(doc, full_name)
    return FileResponse(
        doc["file_path"], filename=filename,
        content_disposition_type="attachment" if download else "inline",
    )
