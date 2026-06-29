"""Public routes: landing page and scheme browsing (no auth required)."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.auth import get_current_user
from app.services import scheme_service, user_document_service

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
    # For a logged-in non-admin user, show which required documents they have.
    approved_docs = None
    if user and user.get("role") != "admin":
        approved_docs = await user_document_service.approved_document_names(user["id"])
    return _templates(request).TemplateResponse(request,
        "schemes/detail.html",
        {
            "request": request,
            "user": user,
            "scheme": scheme,
            "approved_docs": approved_docs,
        },
    )
