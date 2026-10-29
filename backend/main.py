"""Vercel entrypoint re-exporting the main ASGI application."""

from app.main import app

__all__ = ["app"]
