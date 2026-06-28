"""Application configuration loaded from environment / .env file."""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-this-to-a-random-string")
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin123")
    ADMIN_MOBILE: str = os.getenv("ADMIN_MOBILE", "9999999999")
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/gramseva.db")

    # Session cookie config
    SESSION_COOKIE_NAME: str = "session"
    SESSION_MAX_AGE: int = 60 * 60 * 24  # 24 hours in seconds

    # Village branding (white-label)
    VILLAGE_NAME: str = os.getenv("VILLAGE_NAME", "Barloni")
    APP_NAME: str = os.getenv("APP_NAME", "Gram Seva")


settings = Settings()
