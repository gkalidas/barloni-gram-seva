"""Public routes: landing page and scheme browsing (no auth required)."""
import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, FileResponse, Response

from app.auth import get_current_user, is_admin
from app.services import (
    scheme_service, user_document_service, eligibility_service, complaint_service,
)

router = APIRouter()


def _templates(request: Request):
    return request.app.state.templates


@router.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    user = await get_current_user(request)
    return _templates(request).TemplateResponse(request, 
        "landing.html", {"request": request, "user": user}
    )


@router.get("/help", response_class=HTMLResponse)
async def help_page(request: Request):
    user = await get_current_user(request)
    return _templates(request).TemplateResponse(request,
        "help.html", {"request": request, "user": user})


@router.get("/schemes", response_class=HTMLResponse)
async def browse_schemes(request: Request, q: str = "", category: str = ""):
    user = await get_current_user(request)
    schemes = await scheme_service.list_schemes(
        search=q or None, category=category or None, only_active=True
    )
    return _templates(request).TemplateResponse(request, 
        "schemes/browse.html",
        {
            "request": request,
            "user": user,
            "schemes": schemes,
            "q": q,
            "category": category,
            "categories": scheme_service.CATEGORIES,
        },
    )


@router.get("/schemes/{scheme_id}", response_class=HTMLResponse)
async def scheme_detail(request: Request, scheme_id: int):
    user = await get_current_user(request)
    scheme = await scheme_service.get_scheme(scheme_id)
    if scheme is None:
        return _templates(request).TemplateResponse(request, 
            "schemes/browse.html",
            {
                "request": request,
                "user": user,
                "schemes": [],
                "q": "",
                "category": "",
                "categories": scheme_service.CATEGORIES,
                "flash": ("error", "Scheme not found."),
            },
            status_code=404,
        )
    # Count a public view (skip admins so the metric reflects resident interest).
    if not is_admin(user):
        await scheme_service.increment_views(scheme_id)
    # Public source references (GR file + official links).
    sources = await scheme_service.list_sources(scheme_id)
    # For a logged-in non-admin user, show which required documents they have,
    # whether they qualify, and any eligibility dispute they've already raised.
    approved_docs = None
    has_profile = False
    is_eligible = None        # None = unknown (not a resident / no profile)
    existing_dispute = None
    if user and not is_admin(user):
        approved_docs = await user_document_service.approved_document_names(user["id"])
        from app.services import user_service
        profile = user_service.get_profile(user)
        if profile:
            has_profile = True
            is_eligible = eligibility_service.evaluate_scheme(
                profile, scheme.get("eligibility_rules"))
            existing_dispute = await complaint_service.get_user_dispute_for_scheme(
                user["id"], scheme_id)
    return _templates(request).TemplateResponse(request,
        "schemes/detail.html",
        {
            "request": request,
            "user": user,
            "scheme": scheme,
            "sources": sources,
            "approved_docs": approved_docs,
            "has_profile": has_profile,
            "is_eligible": is_eligible,
            "existing_dispute": existing_dispute,
        },
    )


@router.get("/schemes/{scheme_id}/sources/{source_id}/file")
async def scheme_source_file(request: Request, scheme_id: int, source_id: int):
    """Serve a scheme's source/GR file. Public — these are reference documents.
    Served as a download (attachment) to avoid rendering risky types inline."""
    source = await scheme_service.get_source(source_id)
    if (not source or source.get("scheme_id") != scheme_id
            or source.get("kind") != "file" or not source.get("file_path")):
        return Response("Not found", status_code=404)
    if not os.path.isfile(source["file_path"]):
        return Response("File missing", status_code=404)
    download_name = source.get("original_name") or os.path.basename(source["file_path"])
    return FileResponse(
        source["file_path"],
        filename=download_name,
        content_disposition_type="attachment",
    )
