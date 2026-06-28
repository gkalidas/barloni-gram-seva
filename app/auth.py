"""Authentication utilities: password hashing, session cookies, dependencies."""
from typing import Optional

from fastapi import Request
from fastapi.responses import RedirectResponse
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from passlib.context import CryptContext

from app.config import settings
from app.database import get_db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="session")


class AuthRedirect(Exception):
    """Raised by dependencies to signal a redirect to login."""

    def __init__(self, location: str = "/login"):
        self.location = location


class AdminForbidden(Exception):
    """Raised when a non-admin tries to access an admin-only route."""


# Password helpers ----------------------------------------------------------

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return pwd_context.verify(password, password_hash)
    except ValueError:
        return False


# Session cookie helpers ----------------------------------------------------

def create_session(user_id: int, role: str) -> str:
    return _serializer.dumps({"user_id": user_id, "role": role})


def read_session(token: str) -> Optional[dict]:
    try:
        return _serializer.loads(token, max_age=settings.SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def set_session_cookie(response, user_id: int, role: str) -> None:
    token = create_session(user_id, role)
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(settings.SESSION_COOKIE_NAME)


# Dependencies --------------------------------------------------------------

async def get_current_user(request: Request) -> Optional[dict]:
    """Return the full user row as a dict if logged in, else None."""
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not token:
        return None
    data = read_session(token)
    if not data:
        return None
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM users WHERE id = ?", (data["user_id"],)
        )
        row = await cursor.fetchone()
    finally:
        await db.close()
    if row is None:
        return None
    return dict(row)


async def require_user(request: Request) -> dict:
    """Return the logged-in user or raise AuthRedirect to login."""
    user = await get_current_user(request)
    if user is None:
        raise AuthRedirect("/login?next=" + request.url.path)
    return user


async def require_admin(request: Request) -> dict:
    """Return the logged-in admin user or raise (redirect/forbidden)."""
    user = await get_current_user(request)
    if user is None:
        raise AuthRedirect("/login?next=" + request.url.path)
    if user.get("role") != "admin":
        raise AdminForbidden()
    return user
