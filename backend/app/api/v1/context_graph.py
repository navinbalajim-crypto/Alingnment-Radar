"""API endpoints for Live Conversation Context Graph."""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.context_graph import (
    ContextGraphResponse,
    ContextInconsistencyRead,
    ContextNodeRead,
    InconsistencyActionRequest,
    ResolveNodeRequest,
)
from app.services.context_graph_service import ContextGraphService

router = APIRouter(prefix="/conversations", tags=["Conversation Context Graph"])


@router.get(
    "/{conversation_id}/context-graph",
    response_model=ContextGraphResponse,
    status_code=status.HTTP_200_OK,
)
async def get_conversation_context_graph(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve active context nodes and detected inconsistencies for a conversation."""
    service = ContextGraphService(db)
    return await service.get_conversation_graph(conversation_id, user_id=current_user.id)


@router.post(
    "/{conversation_id}/context-graph/inconsistencies/{inconsistency_id}/dismiss",
    response_model=ContextInconsistencyRead,
    status_code=status.HTTP_200_OK,
)
async def dismiss_context_inconsistency(
    conversation_id: uuid.UUID,
    inconsistency_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dismiss a contextual inconsistency/contradiction suggestion."""
    service = ContextGraphService(db)
    return await service.dismiss_inconsistency(
        conversation_id=conversation_id,
        inconsistency_id=inconsistency_id,
        user_id=current_user.id,
    )


@router.post(
    "/{conversation_id}/context-graph/inconsistencies/{inconsistency_id}/resolve",
    response_model=ContextInconsistencyRead,
    status_code=status.HTTP_200_OK,
)
async def resolve_context_inconsistency(
    conversation_id: uuid.UUID,
    inconsistency_id: uuid.UUID,
    payload: Optional[InconsistencyActionRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a contextual inconsistency as resolved following participant clarification."""
    service = ContextGraphService(db)
    note = payload.note if payload else None
    return await service.resolve_inconsistency(
        conversation_id=conversation_id,
        inconsistency_id=inconsistency_id,
        user_id=current_user.id,
        note=note,
    )


@router.post(
    "/{conversation_id}/context-graph/nodes/{node_id}/resolve",
    response_model=ContextNodeRead,
    status_code=status.HTTP_200_OK,
)
async def resolve_context_node(
    conversation_id: uuid.UUID,
    node_id: uuid.UUID,
    payload: Optional[ResolveNodeRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a context task, commitment, or question as resolved/completed."""
    service = ContextGraphService(db)
    target_status = payload.status if payload else "completed"
    note = payload.resolution_note if payload else None
    return await service.resolve_node(
        conversation_id=conversation_id,
        node_id=node_id,
        user_id=current_user.id,
        status=target_status,
        resolution_note=note,
    )
