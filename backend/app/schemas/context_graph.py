"""Live Conversation Context Graph schemas."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ContextNodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    node_type: str = Field(..., description="task, commitment, question, confirmation, entity")
    topic: str
    description: str
    responsible_person: Optional[str] = None
    responsible_user_id: Optional[uuid.UUID] = None
    deadline: Optional[str] = None
    deadline_at: Optional[datetime] = None
    status: str = Field("pending", description="pending, in_progress, completed, uncertain, cancelled")
    evidence_message_ids: List[str] = Field(default_factory=list)
    confidence: float = 0.8
    is_resolved: bool = False
    resolution_note: Optional[str] = None
    last_updated_by_message_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime


class ContextInconsistencyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    node_id: Optional[uuid.UUID] = None
    title: str
    description: str
    earlier_evidence_message_id: Optional[uuid.UUID] = None
    later_evidence_message_id: Optional[uuid.UUID] = None
    clarification_prompt: str
    status: str = Field("detected", description="detected, clarified, dismissed, resolved")
    is_dismissed: bool = False
    created_at: datetime
    updated_at: datetime


class ContextGraphResponse(BaseModel):
    conversation_id: uuid.UUID
    active_nodes: List[ContextNodeRead] = Field(default_factory=list)
    inconsistencies: List[ContextInconsistencyRead] = Field(default_factory=list)
    total_active_nodes: int = 0
    total_inconsistencies: int = 0


class InconsistencyActionRequest(BaseModel):
    action: str = Field("dismiss", description="'dismiss' or 'resolve'")
    note: Optional[str] = None


class ResolveNodeRequest(BaseModel):
    resolution_note: Optional[str] = Field(None, description="Optional note describing resolution")
    status: str = Field("completed", description="Target status: completed, cancelled, resolved")
