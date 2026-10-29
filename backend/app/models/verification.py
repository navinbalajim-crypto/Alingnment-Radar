"""Email verification challenge model for passwordless OTP authentication."""

import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, DateTime, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, utc_now


class VerificationChallenge(Base):
    """Stores hashed single-use OTP codes with expiration and attempt counters."""

    __tablename__ = "verification_challenges"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    hashed_code: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)  # "registration", "login", "invitation"
    invitation_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    is_consumed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    def is_expired(self) -> bool:
        from app.db.base import ensure_utc
        exp = ensure_utc(self.expires_at)
        return exp is not None and utc_now() > exp

    def has_exceeded_attempts(self) -> bool:
        return self.attempts >= self.max_attempts
