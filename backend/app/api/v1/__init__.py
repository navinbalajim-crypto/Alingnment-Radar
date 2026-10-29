"""API v1 routers aggregator."""

from fastapi import APIRouter
from app.api.v1 import (
    ai,
    attachments,
    auth,
    contacts,
    context_graph,
    conversations,
    gmail,
    groups,
    health,
    invitations,
    meetings,
    reminders,
    users,
    voice,
)

api_v1_router = APIRouter()

api_v1_router.include_router(auth.router)
api_v1_router.include_router(users.router)
api_v1_router.include_router(contacts.router)
api_v1_router.include_router(gmail.router)
api_v1_router.include_router(conversations.router)
api_v1_router.include_router(context_graph.router)
api_v1_router.include_router(attachments.router)
api_v1_router.include_router(meetings.router)
api_v1_router.include_router(voice.router)
api_v1_router.include_router(reminders.router)
api_v1_router.include_router(groups.router)
api_v1_router.include_router(invitations.router)
api_v1_router.include_router(ai.router)
api_v1_router.include_router(health.router)

__all__ = ["api_v1_router"]

