"""Authentication routes: signup, login, logout."""
import re

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import (
    get_current_user,
    verify_password,
    set_session_cookie,
    clear_session_cookie,
    password_problems,
)
from app.captcha import make_captcha, verify_captcha
from app.rate_limit import (
    login_is_blocked, login_record_failure, login_reset,
    signup_attempts, client_ip,
)
from app.services import user_service

router = APIRouter()


def _templates(request: Request):
    return request.app.state.templates


def _safe_next(next_url: str) -> str:
    """Only allow same-site relative paths, to prevent open-redirect attacks.

    A value like ``//evil.com`` or ``/\\evil.com`` starts with ``/`` but is
    treated by browsers as a protocol-relative URL to another host, so we
    reject anything whose second character is a slash or backslash.
    """
    if (
        next_url
        and next_url.startswith("/")
        and not next_url.startswith("//")
        and not next_url.startswith("/\\")
    ):
        return next_url
    return "/dashboard"


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, next: str = "/dashboard"):
    user = await get_current_user(request)
    if user:
        return RedirectResponse("/dashboard", status_code=303)
    return _templates(request).TemplateResponse(request, 
        "auth/login.html", {"request": request, "user": None, "next": next}
    )


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/dashboard"),
):
    ip = client_ip(request)
    wait = login_is_blocked(ip, username)
    if wait:
        return _templates(request).TemplateResponse(request,
            "auth/login.html",
            {
                "request": request,
                "user": None,
                "next": next,
                "flash": ("error",
                          "Too many failed attempts. Please try again in "
                          f"about {max(1, wait // 60)} minute(s)."),
                "username": username,
            },
            status_code=429,
        )

    user = await user_service.get_user_by_username(username.strip())
    if user is None or not verify_password(password, user["password_hash"]):
        login_record_failure(ip, username)
        return _templates(request).TemplateResponse(request,
            "auth/login.html",
            {
                "request": request,
                "user": None,
                "next": next,
                "flash": ("error", "Invalid username or password."),
                "username": username,
            },
            status_code=401,
        )
    if not user.get("active", 1):
        return _templates(request).TemplateResponse(request,
            "auth/login.html",
            {
                "request": request,
                "user": None,
                "next": next,
                "flash": ("error", "Your account has been deactivated. Please contact an admin."),
                "username": username,
            },
            status_code=403,
        )
    login_reset(ip, username)
    destination = _safe_next(next)
    response = RedirectResponse(destination, status_code=303)
    set_session_cookie(response, user["id"], user["role"])
    return response


@router.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request):
    user = await get_current_user(request)
    if user:
        return RedirectResponse("/dashboard", status_code=303)
    return _templates(request).TemplateResponse(request,
        "auth/signup.html", {"request": request, "user": None, "captcha": make_captcha()}
    )


@router.post("/signup", response_class=HTMLResponse)
async def signup_submit(
    request: Request,
    username: str = Form(...),
    mobile: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    captcha_token: str = Form(""),
    captcha_answer: str = Form(""),
):
    ip = client_ip(request)

    def render_signup(status_code, error):
        # Always hand out a fresh challenge when re-showing the form, since a
        # token is single-use in spirit and may have expired.
        return _templates(request).TemplateResponse(request,
            "auth/signup.html",
            {
                "request": request,
                "user": None,
                "flash": ("error", error),
                "username": username,
                "mobile": mobile,
                "captcha": make_captcha(),
            },
            status_code=status_code,
        )

    if signup_attempts.is_blocked(ip):
        wait = signup_attempts.retry_after(ip)
        return render_signup(
            429,
            "Too many sign-up attempts from this network. Please "
            f"try again in about {max(1, wait // 60)} minute(s).")

    username = username.strip()
    mobile = mobile.strip()

    # Check the CAPTCHA before anything else so bots never reach validation.
    if not verify_captcha(captcha_token, captcha_answer):
        return render_signup(400, "Incorrect answer to the verification question. Please try again.")

    errors = []
    if len(username) < 3:
        errors.append("Username must be at least 3 characters.")
    if not re.fullmatch(r"\d{10}", mobile):
        errors.append("Mobile number must be exactly 10 digits.")
    errors.extend(password_problems(password))
    if password != confirm_password:
        errors.append("Passwords do not match.")

    if not errors:
        if await user_service.get_user_by_username(username):
            errors.append("That username is already taken.")
        if await user_service.get_user_by_mobile(mobile):
            errors.append("That mobile number is already registered.")

    if errors:
        return render_signup(400, " ".join(errors))

    user_id = await user_service.create_user(username, mobile, password, "user")
    signup_attempts.record(ip)
    response = RedirectResponse("/dashboard", status_code=303)
    set_session_cookie(response, user_id, "user")
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse("/", status_code=303)
    clear_session_cookie(response)
    return response
