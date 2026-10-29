"""User profile schemas."""

import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime


class UserPrivate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    username: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool
    created_at: datetime


class UsernameAvailabilityResponse(BaseModel):
    username: str
    available: bool
    message: str


class AiPreferences(BaseModel):
    """Per-user consent for external processing of unsent drafts. All default to disabled."""
    ai_draft_analysis: bool = False
    ai_autocomplete: bool = False
    draft_recommendations: bool = False


class AiPreferencesUpdate(BaseModel):
    ai_draft_analysis: Optional[bool] = None
    ai_autocomplete: Optional[bool] = None
    draft_recommendations: Optional[bool] = None
