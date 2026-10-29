"""Socket.IO AsyncServer initialization and ASGI app integration."""

import socketio
from app.core.config import settings
from app.core.logging import logger

client_manager = None
if settings.REDIS_URL:
    try:
        client_manager = socketio.AsyncRedisManager(settings.REDIS_URL)
        logger.info("Socket.IO initialized with Redis message manager.")
    except Exception as exc:
        logger.warning(f"Could not initialize Redis client manager: {exc}. Falling back to default memory manager.")

# Initialize Socket.IO AsyncServer
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=settings.FRONTEND_ORIGINS if settings.FRONTEND_ORIGINS != ["*"] else "*",
    client_manager=client_manager,
    logger=False,
    engineio_logger=False,
    max_http_buffer_size=1024 * 1024,  # 1MB limit for socket payloads
)


def create_socket_app(fastapi_app):
    """
    Wrap FastAPI app with Socket.IO ASGI application.
    Incoming requests to /socket.io are intercepted by python-socketio;
    all other HTTP requests are forwarded to FastAPI.
    """
    return socketio.ASGIApp(
        socketio_server=sio,
        other_asgi_app=fastapi_app,
        socketio_path="socket.io",
    )
