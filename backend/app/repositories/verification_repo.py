"""Verification challenge repository for OTP database operations."""

import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import normalize_email
from app.db.base import utc_now
from app.models.verification import VerificationChallenge


class VerificationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_challenge(
        self,
        email: str,
        hashed_code: str,
        purpose: str,
        expires_at: datetime,
        invitation_id: Optional[uuid.UUID] = None,
        max_attempts: int = 5,
    ) -> VerificationChallenge:
        challenge = VerificationChallenge(
            email=normalize_email(email),
            hashed_code=hashed_code,
            purpose=purpose,
            invitation_id=invitation_id,
            expires_at=expires_at,
            max_attempts=max_attempts,
            attempts=0,
            is_consumed=False,
        )
        self.session.add(challenge)
        await self.session.flush()
        return challenge

    async def get_latest_active_challenge(
        self,
        email: str,
        purpose: str,
        invitation_id: Optional[uuid.UUID] = None,
    ) -> Optional[VerificationChallenge]:
        normalized = normalize_email(email)
        stmt = (
            select(VerificationChallenge)
            .where(
                VerificationChallenge.email == normalized,
                VerificationChallenge.purpose == purpose,
                VerificationChallenge.is_consumed.is_(False),
            )
            .order_by(VerificationChallenge.created_at.desc())
        )
        if invitation_id is not None:
            stmt = stmt.where(VerificationChallenge.invitation_id == invitation_id)

        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def increment_attempts(self, challenge: VerificationChallenge) -> int:
        challenge.attempts += 1
        await self.session.flush()
        return challenge.attempts

    async def mark_consumed(self, challenge: VerificationChallenge) -> None:
        challenge.is_consumed = True
        await self.session.flush()
