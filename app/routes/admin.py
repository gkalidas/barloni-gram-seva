"""Admin routes: dashboard, change request review, scheme & user management."""
import json

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import require_admin
from app.services import user_service, scheme_service

router = APIRouter()


def _templates(request: Request):
    return request.app.state.templates


SCHEME_STATUSES = ["active", "closed", "upcoming"]


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
    return _templates(request).TemplateResponse(request, 
        "admin/scheme_form.html",
        {
            "request": request,
            "user": user,
            "scheme": None,
            "categories": scheme_service.CATEGORIES,
            "statuses": SCHEME_STATUSES,
            "action": "/admin/schemes/add",
        },
    )


def _extract_scheme_form(form) -> tuple:
    """Return (data, errors) for scheme create/update."""
    errors = []
    name = (form.get("name") or "").strip()
    if not name:
        errors.append("Scheme name is required.")

    rules, rules_err = _validate_json(form.get("eligibility_rules"), dict)
    if rules_err:
        errors.append("Eligibility rules — " + rules_err)
    docs, docs_err = _validate_json(form.get("documents_required"), list)
    if docs_err:
        errors.append("Documents required — " + docs_err)
    extra, extra_err = _validate_json(form.get("scheme_data"), dict)
    if extra_err:
        errors.append("Scheme data — " + extra_err)

    data = {
        "name": name,
        "name_hi": (form.get("name_hi") or "").strip() or None,
        "ministry": (form.get("ministry") or "").strip() or None,
        "category": (form.get("category") or "").strip() or None,
        "objective": (form.get("objective") or "").strip() or None,
        "benefits": (form.get("benefits") or "").strip() or None,
        "eligibility_rules": json.dumps(rules) if rules is not None else None,
        "documents_required": json.dumps(docs) if docs is not None else None,
        "how_to_apply": (form.get("how_to_apply") or "").strip() or None,
        "application_deadline": (form.get("application_deadline") or "").strip() or None,
        "status": (form.get("status") or "active").strip(),
        "scheme_data": json.dumps(extra) if extra is not None else None,
    }
    return data, errors


@router.post("/admin/schemes/add", response_class=HTMLResponse)
async def add_scheme_submit(request: Request):
    user = await require_admin(request)
    form = await request.form()
    data, errors = _extract_scheme_form(form)
    if errors:
        return _templates(request).TemplateResponse(request, 
            "admin/scheme_form.html",
            {
                "request": request,
                "user": user,
                "scheme": _form_to_scheme_view(form),
                "categories": scheme_service.CATEGORIES,
                "statuses": SCHEME_STATUSES,
                "action": "/admin/schemes/add",
                "flash": ("error", " ".join(errors)),
            },
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
    # Re-encode JSON fields back to pretty strings for the textarea
    scheme["eligibility_rules"] = (
        json.dumps(scheme["eligibility_rules"], indent=2)
        if scheme.get("eligibility_rules") else ""
    )
    scheme["documents_required"] = (
        json.dumps(scheme["documents_required"], indent=2)
        if scheme.get("documents_required") else ""
    )
    scheme["scheme_data"] = (
        json.dumps(scheme["scheme_data"], indent=2)
        if scheme.get("scheme_data") else ""
    )
    return _templates(request).TemplateResponse(request, 
        "admin/scheme_form.html",
        {
            "request": request,
            "user": user,
            "scheme": scheme,
            "categories": scheme_service.CATEGORIES,
            "statuses": SCHEME_STATUSES,
            "action": f"/admin/schemes/{scheme_id}/edit",
        },
    )


@router.post("/admin/schemes/{scheme_id}/edit", response_class=HTMLResponse)
async def edit_scheme_submit(request: Request, scheme_id: int):
    user = await require_admin(request)
    form = await request.form()
    data, errors = _extract_scheme_form(form)
    if errors:
        return _templates(request).TemplateResponse(request, 
            "admin/scheme_form.html",
            {
                "request": request,
                "user": user,
                "scheme": _form_to_scheme_view(form, scheme_id),
                "categories": scheme_service.CATEGORIES,
                "statuses": SCHEME_STATUSES,
                "action": f"/admin/schemes/{scheme_id}/edit",
                "flash": ("error", " ".join(errors)),
            },
            status_code=400,
        )
    await scheme_service.update_scheme(scheme_id, data)
    return RedirectResponse("/admin/schemes?msg=Scheme+updated", status_code=303)


def _form_to_scheme_view(form, scheme_id=None) -> dict:
    """Re-present submitted form values so the form repopulates on error."""
    view = {key: form.get(key) for key in form.keys()}
    if scheme_id is not None:
        view["id"] = scheme_id
    return view
