"""Socket.IO real-time package."""

from app.sockets.server import sio, create_socket_app
import app.sockets.events  # Ensure event handlers are registered

__all__ = ["sio", "create_socket_app"]
