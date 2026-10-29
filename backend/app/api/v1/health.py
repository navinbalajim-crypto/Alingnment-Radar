"""Health and readiness operations endpoints under /api/v1."""

from fastapi import APIRouter, Response, status
from app.core.config import settings
from app.db.session import check_database_connection

router = APIRouter(tags=["Operations"])


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """Liveness probe returning application metadata."""
    return {
        "status": "ok",
        "app_name": settings.APP_NAME,
        "environment": settings.APP_ENV,
    }


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_check(response: Response):
    """Readiness probe validating database connectivity and provider configuration."""
    db_ok = await check_database_connection()
    checks = settings.startup_checks()
    checks["database_connected"] = db_ok

    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        checks["status"] = "degraded"
    else:
        checks["status"] = "ready"

    return checks
