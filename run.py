"""Entry point: run the app with uvicorn (development).

For one-click setup + launch (auto-installs dependencies), use start.py instead.
"""
import uvicorn

from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
    )
