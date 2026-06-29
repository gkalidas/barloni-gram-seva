"""Application configuration loaded from environment / .env file."""
import os
import re
from dotenv import load_dotenv

load_dotenv()

_HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _color(env_name: str, default: str) -> str:
    """Read a hex colour from the environment, falling back to a safe default.

    Validated so an operator-supplied value can only ever be a `#rgb`/`#rrggbb`
    colour — it is injected into a <style> block, so this also blocks CSS/HTML
    injection via the branding config.
    """
    value = (os.getenv(env_name) or "").strip()
    return value if _HEX_COLOR.match(value) else default


class Settings:
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-this-to-a-random-string")
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin123")
    ADMIN_MOBILE: str = os.getenv("ADMIN_MOBILE", "9999999999")
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/gramseva.db")

    # Optional CSV auto-loaded on startup (idempotent: skips existing users).
    # Holds PII + passwords, so it is gitignored by default.
    SEED_USERS_CSV: str = os.getenv("SEED_USERS_CSV", "users.csv")

    # Server
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))

    # Session cookie config
    SESSION_COOKIE_NAME: str = "session"
    SESSION_MAX_AGE: int = 60 * 60 * 24  # 24 hours in seconds
    # Set true in production (HTTPS) so the session cookie is only sent over
    # TLS. Leave false for local http:// development, or the cookie won't be
    # sent and login will appear to silently fail.
    SESSION_COOKIE_SECURE: bool = (
        os.getenv("SESSION_COOKIE_SECURE", "false").strip().lower()
        in ("true", "1", "yes", "on")
    )

    # Village branding (white-label)
    VILLAGE_NAME: str = os.getenv("VILLAGE_NAME", "Barloni")
    APP_NAME: str = os.getenv("APP_NAME", "Gram Seva")
    # Emoji/character shown as the logo mark in the top bar.
    BRAND_EMOJI: str = (os.getenv("BRAND_EMOJI", "").strip() or "🏛️")
    # Footer tagline.
    BRAND_TAGLINE: str = os.getenv(
        "BRAND_TAGLINE", "A village civic platform · Built for the community")
    # Theme colours (validated hex). Primary = top bar / links; accent = CTAs.
    BRAND_PRIMARY: str = _color("BRAND_PRIMARY", "#1a365d")
    BRAND_ACCENT: str = _color("BRAND_ACCENT", "#2f855a")

    # Complaints: wards/areas a villager can pick from (per-village list).
    COMPLAINT_WARDS: list = [
        w.strip() for w in os.getenv(
            "COMPLAINT_WARDS", "Ward 1,Ward 2,Ward 3,Ward 4,Ward 5"
        ).split(",") if w.strip()
    ]


settings = Settings()
