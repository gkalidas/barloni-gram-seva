"""Admin routes: dashboard, change request review, scheme & user management."""
import json

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from app.auth import require_admin
from app.services import user_service, scheme_service, document_service
from app.constants import (
    GENDERS, CASTE_CATEGORIES, OCCUPATIONS, LAND_OWNERSHIP,
)

router = APIRouter()


def _templates(request: Request):
    return request.app.state.templates


SCHEME_STATUSES = ["active", "closed", "upcoming"]


def _scheme_form_context(request, user, scheme, action, documents, flash=None):
    """Shared context for the add/edit scheme form template."""
    ctx = {
        "request": request,
        "user": user,
        "scheme": scheme,
        "categories": scheme_service.CATEGORIES,
        "statuses": SCHEME_STATUSES,
        "documents": documents,
        "genders": GENDERS,
        "caste_categories": CASTE_CATEGORIES,
        "occupations": OCCUPATIONS,
        "land_ownership_options": LAND_OWNERSHIP,
        "action": action,
    }
    if flash:
        ctx["flash"] = flash
    return ctx


def _validate_json(text: str, expect_type):
    """Return (parsed, error). Empty text -> (default, None)."""
    text = (text or "").strip()
    if not text:
        return (None, None)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return (None, f"Invalid JSON: {exc}")
    if expect_type and not isinstance(parsed, expect_type):
        return (None, f"Expected a JSON {expect_type.__name__}.")
    return (parsed, None)


@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    user = await require_admin(request)
    return _templates(request).TemplateResponse(request, 
        "admin/dashboard.html",
        {
            "request": request,
            "user": user,
            "pending_count": await user_service.count_pending_requests(),
            "user_count": await user_service.count_users(),
            "scheme_count": await scheme_service.count_schemes(),
        },
    )


@router.get("/admin/change-requests", response_class=HTMLResponse)
async def change_requests(request: Request, status: str = "pending"):
    user = await require_admin(request)
    requests = await user_service.list_change_requests(
        status=status if status != "all" else None
    )
    return _templates(request).TemplateResponse(request, 
        "admin/change_requests.html",
        {
            "request": request,
            "user": user,
            "requests": requests,
            "status": status,
        },
    )


@router.get("/admin/change-requests/{request_id}", response_class=HTMLResponse)
async def review_change(request: Request, request_id: int):
    user = await require_admin(request)
    change = await user_service.get_change_request(request_id)
    if change is None:
        return RedirectResponse("/admin/change-requests", status_code=303)
    # Build a set of field keys present in either old or new
    keys = sorted(
        set(change["old_values"].keys()) | set(change["new_values"].keys())
    )
    return _templates(request).TemplateResponse(request, 
        "admin/review_change.html",
        {
            "request": request,
            "user": user,
            "change": change,
            "keys": keys,
        },
    )


@router.post("/admin/change-requests/{request_id}/approve")
async def approve_change(request: Request, request_id: int):
    admin = await require_admin(request)
    ok = await user_service.approve_change_request(request_id, admin["id"])
    msg = "Change+request+approved" if ok else "Request+not+found+or+already+reviewed"
    return RedirectResponse(f"/admin/change-requests?msg={msg}", status_code=303)


@router.post("/admin/change-requests/{request_id}/reject")
async def reject_change(
    request: Request,
    request_id: int,
    rejection_reason: str = Form(...),
):
    admin = await require_admin(request)
    reason = rejection_reason.strip()
    if not reason:
        return RedirectResponse(
            f"/admin/change-requests/{request_id}?msg=Rejection+reason+is+required",
            status_code=303,
        )
    ok = await user_service.reject_change_request(request_id, admin["id"], reason)
    msg = "Change+request+rejected" if ok else "Request+not+found+or+already+reviewed"
    return RedirectResponse(f"/admin/change-requests?msg={msg}", status_code=303)


@router.get("/admin/users", response_class=HTMLResponse)
async def users(request: Request):
    user = await require_admin(request)
    all_users = await user_service.list_users()
    return _templates(request).TemplateResponse(request, 
        "admin/users.html",
        {"request": request, "user": user, "users": all_users},
    )


@router.get("/admin/schemes", response_class=HTMLResponse)
async def admin_schemes(request: Request):
    user = await require_admin(request)
    schemes = await scheme_service.list_schemes(only_active=False)
    return _templates(request).TemplateResponse(request, 
        "admin/schemes.html",
        {"request": request, "user": user, "schemes": schemes},
    )


@router.get("/admin/schemes/add", response_class=HTMLResponse)
async def add_scheme_form(request: Request):
    user = await require_admin(request)
    documents = await document_service.list_documents()
    return _templates(request).TemplateResponse(
        request,
        "admin/scheme_form.html",
        _scheme_form_context(request, user, None, "/admin/schemes/add", documents),
    )


def _assemble_eligibility(form) -> dict:
    """Build the eligibility_rules dict from structured form fields.

    Blank / unticked fields are omitted, which the matcher treats as
    "no restriction".
    """
    rules = {}

    def num(key):
        raw = (form.get(key) or "").strip()
        if not raw:
            return None
        try:
            return int(float(raw))
        except ValueError:
            return None

    min_age = num("min_age")
    max_age = num("max_age")
    max_income = num("max_income")
    if min_age is not None:
        rules["min_age"] = min_age
    if max_age is not None:
        rules["max_age"] = max_age
    if max_income is not None:
        rules["max_income"] = max_income

    gender = [g for g in form.getlist("rule_gender") if g in GENDERS]
    if gender:
        rules["gender"] = gender
    caste = [c for c in form.getlist("rule_caste") if c in CASTE_CATEGORIES]
    if caste:
        rules["caste_category"] = caste
    occupation = [o for o in form.getlist("rule_occupation") if o in OCCUPATIONS]
    if occupation:
        rules["occupation"] = occupation
    land = [l for l in form.getlist("rule_land") if l in LAND_OWNERSHIP]
    if land:
        rules["land_ownership"] = land

    if form.get("bpl_card_required") == "on":
        rules["bpl_card_required"] = True
    if form.get("has_disability") == "on":
        rules["has_disability"] = True
    if form.get("bank_account_required") == "on":
        rules["bank_account_required"] = True

    return rules


def _extract_scheme_form(form) -> tuple:
    """Return (data, errors) for scheme create/update."""
    errors = []
    name = (form.get("name") or "").strip()
    if not name:
        errors.append("Scheme name is required.")

    rules = _assemble_eligibility(form)
    if (
        rules.get("min_age") is not None
        and rules.get("max_age") is not None
        and rules["min_age"] > rules["max_age"]
    ):
        errors.append("Minimum age cannot be greater than maximum age.")

    documents = [d.strip() for d in form.getlist("documents") if d.strip()]

    extra, extra_err = _validate_json(form.get("scheme_data"), dict)
    if extra_err:
        errors.append("Additional data — " + extra_err)

    data = {
        "name": name,
        "name_hi": (form.get("name_hi") or "").strip() or None,
        "ministry": (form.get("ministry") or "").strip() or None,
        "category": (form.get("category") or "").strip() or None,
        "objective": (form.get("objective") or "").strip() or None,
        "benefits": (form.get("benefits") or "").strip() or None,
        "eligibility_rules": json.dumps(rules) if rules else None,
        "documents_required": json.dumps(documents) if documents else None,
        "how_to_apply": (form.get("how_to_apply") or "").strip() or None,
        "application_deadline": (form.get("application_deadline") or "").strip() or None,
        "status": (form.get("status") or "active").strip(),
        "scheme_data": json.dumps(extra) if extra is not None else None,
    }
    return data, errors


def _form_to_scheme_view(form, scheme_id=None) -> dict:
    """Re-present submitted values (with structured rules/docs) on validation error."""
    return {
        "id": scheme_id,
        "name": form.get("name"),
        "name_hi": form.get("name_hi"),
        "ministry": form.get("ministry"),
        "category": form.get("category"),
        "objective": form.get("objective"),
        "benefits": form.get("benefits"),
        "how_to_apply": form.get("how_to_apply"),
        "application_deadline": form.get("application_deadline"),
        "status": form.get("status") or "active",
        "scheme_data": form.get("scheme_data") or "",
        "eligibility_rules": _assemble_eligibility(form),
        "documents_required": [d for d in form.getlist("documents") if d.strip()],
    }


@router.post("/admin/schemes/add", response_class=HTMLResponse)
async def add_scheme_submit(request: Request):
    user = await require_admin(request)
    form = await request.form()
    data, errors = _extract_scheme_form(form)
    if errors:
        documents = await document_service.list_documents()
        return _templates(request).TemplateResponse(
            request,
            "admin/scheme_form.html",
            _scheme_form_context(
                request, user, _form_to_scheme_view(form),
                "/admin/schemes/add", documents,
                flash=("error", " ".join(errors)),
            ),
            status_code=400,
        )
    await scheme_service.create_scheme(data)
    return RedirectResponse("/admin/schemes?msg=Scheme+added", status_code=303)


@router.get("/admin/schemes/{scheme_id}/edit", response_class=HTMLResponse)
async def edit_scheme_form(request: Request, scheme_id: int):
    user = await require_admin(request)
    scheme = await scheme_service.get_scheme(scheme_id)
    if scheme is None:
        return RedirectResponse("/admin/schemes", status_code=303)
    # eligibility_rules (dict) and documents_required (list) are used directly
    # by the structured form. Only scheme_data uses a raw-JSON textarea.
    scheme["scheme_data"] = (
        json.dumps(scheme["scheme_data"], indent=2)
        if scheme.get("scheme_data") else ""
    )
    documents = await document_service.list_documents()
    return _templates(request).TemplateResponse(
        request,
        "admin/scheme_form.html",
        _scheme_form_context(
            request, user, scheme,
            f"/admin/schemes/{scheme_id}/edit", documents,
        ),
    )


@router.post("/admin/schemes/{scheme_id}/edit", response_class=HTMLResponse)
async def edit_scheme_submit(request: Request, scheme_id: int):
    user = await require_admin(request)
    form = await request.form()
    data, errors = _extract_scheme_form(form)
    if errors:
        documents = await document_service.list_documents()
        return _templates(request).TemplateResponse(
            request,
            "admin/scheme_form.html",
            _scheme_form_context(
                request, user, _form_to_scheme_view(form, scheme_id),
                f"/admin/schemes/{scheme_id}/edit", documents,
                flash=("error", " ".join(errors)),
            ),
            status_code=400,
        )
    await scheme_service.update_scheme(scheme_id, data)
    return RedirectResponse("/admin/schemes?msg=Scheme+updated", status_code=303)


@router.post("/admin/documents/add")
async def add_document_route(request: Request, name: str = Form(...)):
    """Add a document to the master list. Used by the inline 'add' button."""
    await require_admin(request)
    doc = await document_service.add_document(name)
    if doc is None:
        return JSONResponse({"ok": False, "error": "Document name is required."},
                            status_code=400)
    return JSONResponse({"ok": True, "id": doc["id"], "name": doc["name"]})
