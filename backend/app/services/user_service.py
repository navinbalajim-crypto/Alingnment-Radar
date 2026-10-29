"""User service for discovery, profile access, and availability checks."""

import uuid
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.errors import NotFoundError
from app.core.security import normalize_username, validate_username_format
from app.repositories.user_repo import UserRepository
from app.schemas.user import UserPrivate, UserPublic, UsernameAvailabilityResponse


class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)

    async def get_me(self, user_id: uuid.UUID) -> UserPrivate:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError("User not found.")
        return UserPrivate.model_validate(user)

    async def search_users(self, query: str, current_user_id: uuid.UUID, limit: int = 20) -> List[UserPublic]:
        cleaned = query.strip()
        if not cleaned:
            return []
        users = await self.user_repo.search_users(query=cleaned, exclude_user_id=current_user_id, limit=limit)
        return [UserPublic.model_validate(u) for u in users]

    async def check_username_availability(self, username: str) -> UsernameAvailabilityResponse:
        try:
            valid_username = validate_username_format(username)
        except ValueError as exc:
            return UsernameAvailabilityResponse(
                username=username,
                available=False,
                message=str(exc),
            )

        is_taken = await self.user_repo.is_username_taken(valid_username)
        if is_taken:
            return UsernameAvailabilityResponse(
                username=valid_username,
                available=False,
                message="Username is already taken.",
            )

        return UsernameAvailabilityResponse(
            username=valid_username,
            available=True,
            message="Username is available.",
        )
