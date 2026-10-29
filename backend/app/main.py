"""Main application entry point integrating FastAPI REST APIs and Socket.IO ASGI server."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api.v1 import api_v1_router
from app.api.v1.health import router as health_router
from app.core.config import settings
from app.core.errors import AppException
from app.core.logging import logger
from app.db.session import engine
from app.sockets.server import create_socket_app


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle event handler."""
    logger.info("Initializing Alignment Radar backend services...")
    checks = settings.startup_checks()
    logger.info(f"Startup configuration: env={checks['environment']}, providers={checks['providers']}")

    try:
        from app.db.session import init_db_models
        await init_db_models()
        logger.info("Database tables initialized successfully.")
    except Exception as exc:
        logger.warning(f"Database initialization notice: {exc}")

    import asyncio
    from app.services.ai_decision_engine import AIDecisionEngine
    from app.tasks.reminder_worker import start_reminder_worker, stop_reminder_worker
    recovery_task = asyncio.create_task(AIDecisionEngine.recover_pending())
    reminder_task = start_reminder_worker(interval_seconds=10.0)

    yield

    stop_reminder_worker()
    recovery_task.cancel()
    logger.info("Shutting down Alignment Radar backend, disposing DB connection pool...")
    await engine.dispose()
    logger.info("Shutdown complete.")


def create_fastapi_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    application = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        # interactive API docs are a development aid; they are not served in production
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
        lifespan=lifespan,
    )

    @application.get("/")
    async def root_status():
        """Simple root endpoint so infrastructure checks and root probes do not 404."""
        return {
            "status": "ok",
            "app_name": settings.APP_NAME,
            "environment": settings.APP_ENV,
        }

    # CORS configuration
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.FRONTEND_ORIGINS,
        # Credentialed requests are never combined with a wildcard origin.
        allow_credentials="*" not in settings.FRONTEND_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception Handlers
    @application.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
            headers=exc.headers,
        )

    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "code": "VALIDATION_ERROR",
                "message": "Validation error in request payload or query parameters.",
                "details": exc.errors(),
            },
        )

    @application.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled server error: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An internal server error occurred.",
            },
        )

    # Mount API routes
    application.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)
    # Also mount root health checks for infrastructure orchestrators
    application.include_router(health_router)

    return application


# Initialize FastAPI app
fastapi_app = create_fastapi_app()

# Wrap with Socket.IO ASGI server
app = create_socket_app(fastapi_app)
asgi_app = app

__all__ = ["app", "asgi_app", "fastapi_app"]
