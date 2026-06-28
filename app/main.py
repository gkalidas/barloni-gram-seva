"""FastAPI application factory, middleware, and startup tasks."""
import os

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.database import init_db, get_db
from app.auth import AuthRedirect, AdminForbidden, hash_password, get_current_user

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)


async def ensure_default_admin() -> None:
    """Create the default admin user from env vars if no admin exists."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id FROM users WHERE role = 'admin' LIMIT 1"
        )
        existing = await cursor.fetchone()
        if existing is None:
            await db.execute(
                """INSERT INTO users (username, mobile, password_hash, role)
                   VALUES (?, ?, ?, 'admin')""",
                (
                    settings.ADMIN_USERNAME,
                    settings.ADMIN_MOBILE,
                    hash_password(settings.ADMIN_PASSWORD),
                ),
            )
            await db.commit()
    finally:
        await db.close()


async def load_seed_users() -> None:
    """Import users from settings.SEED_USERS_CSV if that file exists.

    Idempotent: the importer skips users whose mobile/username already exist,
    so this is safe to run on every startup. Errors never block startup.
    """
    csv_path = settings.SEED_USERS_CSV
    if not csv_path or not os.path.isfile(csv_path):
        return
    from app.services import import_export_service
    try:
        with open(csv_path, "rb") as fh:
            raw = fh.read()
        summary = await import_export_service.import_users(raw)
        note = (
            f"[startup] Loaded users from {csv_path}: "
            f"added {summary['added']}, skipped {summary['skipped']}"
        )
        if summary["errors"]:
            note += f", {len(summary['errors'])} row error(s)"
        print(note)
    except Exception as exc:  # never let a bad file stop the app
        print(f"[startup] Could not load users from {csv_path}: {exc}")


def create_app() -> FastAPI:
    app = FastAPI(title="barloni-gram-seva")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # Make templates available to routers via app state
    app.state.templates = templates

    # Expose common values to all templates
    templates.env.globals["village_name"] = settings.VILLAGE_NAME
    templates.env.globals["app_name"] = settings.APP_NAME

    # Routers (imported here to avoid circular imports)
    from app.routes import public, auth_routes, user, admin

    app.include_router(public.router)
    app.include_router(auth_routes.router)
    app.include_router(user.router)
    app.include_router(admin.router)

    @app.on_event("startup")
    async def on_startup():
        await init_db()
        await ensure_default_admin()
        # Seed the master document catalogue and sample schemes on first run
        from app.services import document_service
        await document_service.seed_documents()
        from seed_schemes import seed
        await seed()
        # Make sure every document a scheme requires is in the master list,
        # so users can always upload it from their locker.
        await document_service.sync_scheme_documents()
        # Optionally auto-load users from a CSV (idempotent: skips existing).
        await load_seed_users()

    # Exception handlers for auth dependencies
    @app.exception_handler(AuthRedirect)
    async def auth_redirect_handler(request: Request, exc: AuthRedirect):
        return RedirectResponse(url=exc.location, status_code=303)

    @app.exception_handler(AdminForbidden)
    async def admin_forbidden_handler(request: Request, exc: AdminForbidden):
        html = templates.get_template("base.html")
        return HTMLResponse(
            content=(
                "<!doctype html><html><body style='font-family:sans-serif;"
                "padding:2rem;text-align:center'><h1>403 — Forbidden</h1>"
                "<p>You do not have permission to access this page.</p>"
                "<a href='/'>Go home</a></body></html>"
            ),
            status_code=403,
        )

    return app


app = create_app()
