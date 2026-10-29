"""UserContact entity model for imported external contacts."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.user import User


class UserContact(Base):
    """Imported contact records strictly private to the owner user."""

    __tablename__ = "user_contacts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_email_normalized: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    contact_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    google_resource_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="contacts")

    __table_args__ = (
        UniqueConstraint("user_id", "contact_email_normalized", name="uq_user_contacts_user_email"),
        Index("ix_user_contacts_user_email", "user_id", "contact_email_normalized"),
    )

    def __repr__(self) -> str:
        return f"<UserContact user_id={self.user_id} email={self.contact_email_normalized}>"
