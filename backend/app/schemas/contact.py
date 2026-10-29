"""User contacts schemas for address book and colleague discovery."""

import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ContactItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contact_email: str
    contact_name: Optional[str] = None
    is_registered: bool = Field(False, description="Whether this contact is already registered on Alignment Radar")
    registered_username: Optional[str] = Field(None, description="Username on platform if registered")
    registered_user_id: Optional[uuid.UUID] = Field(None, description="User ID on platform if registered")
    avatar_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ContactListResponse(BaseModel):
    contacts: List[ContactItem]
    total: int


class SyncContactsResponse(BaseModel):
    synced_count: int
    matched_registered_count: int
    message: str
