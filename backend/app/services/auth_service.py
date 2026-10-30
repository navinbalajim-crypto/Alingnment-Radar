"""Authentication service managing passwordless flows, tickets, tokens, and sessions."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.errors import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    UnauthorizedError,
)
from app.core.logging import logger
from app.core.security import (
    create_access_token,
    create_password_reset_ticket,
    create_registration_ticket,
    generate_otp_code,
    generate_secure_token,
    hash_otp_code,
    hash_password,
    hash_token,
    normalize_email,
    normalize_username,
    rate_limiter,
    validate_password_complexity,
    validate_username_format,
    verify_otp_code,
    verify_password,
    verify_password_reset_ticket,
    verify_registration_ticket,
)
from app.db.base import utc_now
from app.models.user import User
from app.repositories.session_repo import SessionRepository
from app.repositories.user_repo import UserRepository
from app.repositories.verification_repo import VerificationRepository
from app.schemas.auth import (
    MessageResponse,
    RequestCodeResponse,
    ResetPasswordVerifyResponse,
    TokenResponse,
    UserTokenPayload,
    VerifyRegisterCodeResponse,
)
from app.services.email_service import email_service


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.verification_repo = VerificationRepository(session)
        self.session_repo = SessionRepository(session)

    async def request_registration_code(self, raw_email: str) -> RequestCodeResponse:
        email = normalize_email(raw_email)

        # Enforce rate limit per email: max 5 requests per 10 minutes, with cooldown
        rate_limiter.enforce(f"otp:reg:{email}", max_attempts=settings.OTP_MAX_ATTEMPTS, window_seconds=600, action_name="code request")
        rate_limiter.enforce(f"otp:cooldown:{email}", max_attempts=1, window_seconds=settings.OTP_RESEND_COOLDOWN_SECONDS, action_name="resend")

        existing_user = await self.user_repo.get_by_email(email)
        if existing_user:
            raise ConflictError("An account with this email address already exists. Please sign in instead.")

        code = generate_otp_code()
        hashed_code = hash_otp_code(code)
        expires_at = utc_now() + timedelta(seconds=settings.OTP_EXPIRE_SECONDS)

        await self.verification_repo.create_challenge(
            email=email,
            hashed_code=hashed_code,
            purpose="registration",
            expires_at=expires_at,
            max_attempts=settings.OTP_MAX_ATTEMPTS,
        )

        await email_service.send_auth_code(email=email, code=code, purpose="account registration")

        return RequestCodeResponse(
            message="Verification code sent to your email address.",
            email=email,
            cooldown_seconds=settings.OTP_RESEND_COOLDOWN_SECONDS,
        )

    async def verify_registration_code(self, raw_email: str, code: str) -> VerifyRegisterCodeResponse:
        email = normalize_email(raw_email)
        challenge = await self.verification_repo.get_latest_active_challenge(email=email, purpose="registration")

        if not challenge:
            raise BadRequestError("No active registration code found for this email. Please request a new code.")

        if challenge.is_expired():
            raise BadRequestError("Verification code has expired. Please request a new code.")

        if challenge.has_exceeded_attempts():
            raise BadRequestError("Maximum verification attempts exceeded. Please request a new code.")

        is_valid = verify_otp_code(code, challenge.hashed_code)
        if not is_valid:
            attempts = await self.verification_repo.increment_attempts(challenge)
            remaining = max(0, challenge.max_attempts - attempts)
            raise BadRequestError(f"Invalid verification code. {remaining} attempt(s) remaining.")

        await self.verification_repo.mark_consumed(challenge)

        # Issue short-lived ticket
        ticket = create_registration_ticket(email=email)
        return VerifyRegisterCodeResponse(
            message="Email verified successfully. Please choose a username to finish registration.",
            registration_ticket=ticket,
            email=email,
        )

    async def complete_registration(
        self,
        registration_ticket: str,
        raw_username: str,
        display_name: Optional[str] = None,
        password: Optional[str] = None,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> TokenResponse:
        verified_email = verify_registration_ticket(registration_ticket, consume=True)

        # Validate username format
        try:
            valid_username = validate_username_format(raw_username)
        except ValueError as exc:
            raise BadRequestError(str(exc))

        # Check unique username case-insensitively
        is_taken = await self.user_repo.is_username_taken(valid_username)
        if is_taken:
            raise ConflictError("Username is already taken. Please choose another username.")

        # Double check email uniqueness
        existing_user = await self.user_repo.get_by_email(verified_email)
        if existing_user:
            raise ConflictError("An account with this email address already exists.")

        # Validate and hash password if provided
        pwd_hash = None
        if password:
            try:
                validate_password_complexity(password)
                pwd_hash = hash_password(password)
            except ValueError as exc:
                raise BadRequestError(str(exc))

        # Create user
        user = await self.user_repo.create_user(
            email=verified_email,
            username=valid_username,
            display_name=display_name,
            password_hash=pwd_hash,
        )

        return await self._create_tokens_for_user(user, user_agent=user_agent, ip_address=ip_address)

    async def request_login_code(self, raw_email: str) -> RequestCodeResponse:
        email = normalize_email(raw_email)

        rate_limiter.enforce(f"otp:login:{email}", max_attempts=settings.OTP_MAX_ATTEMPTS, window_seconds=600, action_name="code request")
        rate_limiter.enforce(f"otp:cooldown:{email}", max_attempts=1, window_seconds=settings.OTP_RESEND_COOLDOWN_SECONDS, action_name="resend")

        user = await self.user_repo.get_by_email(email)
        if not user:
            raise NotFoundError("No account found with this email address. Please register first.")

        if not user.is_active:
            raise UnauthorizedError("Account is inactive.")

        code = generate_otp_code()
        hashed_code = hash_otp_code(code)
        expires_at = utc_now() + timedelta(seconds=settings.OTP_EXPIRE_SECONDS)

        await self.verification_repo.create_challenge(
            email=email,
            hashed_code=hashed_code,
            purpose="login",
            expires_at=expires_at,
            max_attempts=settings.OTP_MAX_ATTEMPTS,
        )

        await email_service.send_auth_code(email=email, code=code, purpose="login")

        return RequestCodeResponse(
            message="Sign-in verification code sent to your email address.",
            email=email,
            cooldown_seconds=settings.OTP_RESEND_COOLDOWN_SECONDS,
        )

    async def verify_login_code(
        self,
        raw_email: str,
        code: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> TokenResponse:
        email = normalize_email(raw_email)
        challenge = await self.verification_repo.get_latest_active_challenge(email=email, purpose="login")

        if not challenge:
            raise BadRequestError("No active sign-in code found for this email. Please request a new code.")

        if challenge.is_expired():
            raise BadRequestError("Sign-in code has expired. Please request a new code.")

        if challenge.has_exceeded_attempts():
            raise BadRequestError("Maximum verification attempts exceeded. Please request a new code.")

        is_valid = verify_otp_code(code, challenge.hashed_code)
        if not is_valid:
            attempts = await self.verification_repo.increment_attempts(challenge)
            remaining = max(0, challenge.max_attempts - attempts)
            raise BadRequestError(f"Invalid sign-in code. {remaining} attempt(s) remaining.")

        await self.verification_repo.mark_consumed(challenge)

        user = await self.user_repo.get_by_email(email)
        if not user or not user.is_active:
            raise UnauthorizedError("User account not found or disabled.")

        return await self._create_tokens_for_user(user, user_agent=user_agent, ip_address=ip_address)

    async def refresh_tokens(
        self,
        raw_refresh_token: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> TokenResponse:
        token_hash = hash_token(raw_refresh_token)
        session = await self.session_repo.get_active_session_by_hash(token_hash)

        if not session or not session.is_active():
            raise UnauthorizedError("Invalid or expired refresh token. Please sign in again.")

        user = await self.user_repo.get_by_id(session.user_id)
        if not user or not user.is_active:
            raise UnauthorizedError("User account not found or disabled.")

        # Rotate refresh token
        new_refresh_token = generate_secure_token(48)
        new_token_hash = hash_token(new_refresh_token)
        new_expires_at = utc_now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        await self.session_repo.rotate_session(
            old_session=session,
            new_token_hash=new_token_hash,
            new_expires_at=new_expires_at,
        )

        access_token = create_access_token(user_id=str(user.id), username=user.username)
        expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        has_pwd = bool(user.password_hash)

        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=expires_in,
            user=UserTokenPayload(
                id=user.id,
                email=user.email,
                username=user.username,
                display_name=user.display_name,
                avatar_url=user.avatar_url,
                has_password=has_pwd,
            ),
            has_password=has_pwd,
        )

    async def logout(self, raw_refresh_token: str) -> None:
        token_hash = hash_token(raw_refresh_token)
        session = await self.session_repo.get_active_session_by_hash(token_hash)
        if session:
            await self.session_repo.revoke_session(session)

    async def login_with_password(
        self,
        identifier: str,
        password: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> TokenResponse:
        rate_limiter.enforce(f"login:pwd:{ip_address or 'global'}", max_attempts=15, window_seconds=300, action_name="login")

        user = await self.user_repo.get_by_username_or_email(identifier)
        if not user or not user.is_active:
            raise UnauthorizedError("Invalid username or password.")

        if not user.password_hash:
            raise UnauthorizedError(
                "This account does not have a password set. Please sign in using an email code or Google, or use 'Forgot password?' to set one."
            )

        if not verify_password(password, user.password_hash):
            raise UnauthorizedError("Invalid username or password.")

        return await self._create_tokens_for_user(user, user_agent=user_agent, ip_address=ip_address)

    async def set_user_password(self, user_id: uuid.UUID, new_password: str) -> MessageResponse:
        try:
            validate_password_complexity(new_password)
        except ValueError as exc:
            raise BadRequestError(str(exc))

        user = await self.user_repo.get_by_id(user_id)
        if not user or not user.is_active:
            raise NotFoundError("User not found.")

        pwd_hash = hash_password(new_password)
        await self.user_repo.set_password_hash(user.id, pwd_hash)
        return MessageResponse(message="Password set successfully.")

    async def request_password_reset(self, raw_email: str) -> MessageResponse:
        email = normalize_email(raw_email)

        rate_limiter.enforce(f"otp:pwdreset:{email}", max_attempts=settings.OTP_MAX_ATTEMPTS, window_seconds=600, action_name="password reset request")
        rate_limiter.enforce(f"otp:cooldown:{email}", max_attempts=1, window_seconds=settings.OTP_RESEND_COOLDOWN_SECONDS, action_name="resend")

        user = await self.user_repo.get_by_email(email)
        # To prevent account enumeration, return generic response even if email is not found
        if not user or not user.is_active:
            return MessageResponse(message="If an account with that email address exists, a verification code has been sent.")

        code = generate_otp_code()
        hashed_code = hash_otp_code(code)
        expires_at = utc_now() + timedelta(seconds=settings.OTP_EXPIRE_SECONDS)

        await self.verification_repo.create_challenge(
            email=email,
            hashed_code=hashed_code,
            purpose="password_reset",
            expires_at=expires_at,
            max_attempts=settings.OTP_MAX_ATTEMPTS,
        )

        await email_service.send_auth_code(email=email, code=code, purpose="password reset")

        return MessageResponse(message="If an account with that email address exists, a verification code has been sent.")

    async def verify_password_reset_code(self, raw_email: str, code: str) -> ResetPasswordVerifyResponse:
        email = normalize_email(raw_email)
        rate_limiter.enforce(f"otp:verify:{email}", max_attempts=10, window_seconds=600, action_name="code verification")
        challenge = await self.verification_repo.get_latest_active_challenge(email=email, purpose="password_reset")

        if not challenge:
            raise BadRequestError("No active password reset code found for this email. Please request a new code.")

        if challenge.is_expired():
            raise BadRequestError("Verification code has expired. Please request a new code.")

        if challenge.has_exceeded_attempts():
            raise BadRequestError("Maximum verification attempts exceeded. Please request a new code.")

        is_valid = verify_otp_code(code, challenge.hashed_code)
        if not is_valid:
            attempts = await self.verification_repo.increment_attempts(challenge)
            remaining = max(0, challenge.max_attempts - attempts)
            raise BadRequestError(f"Invalid verification code. {remaining} attempt(s) remaining.")

        await self.verification_repo.mark_consumed(challenge)

        ticket = create_password_reset_ticket(email=email)
        return ResetPasswordVerifyResponse(
            message="Code verified successfully. Please enter your new password.",
            reset_ticket=ticket,
            email=email,
        )

    async def complete_password_reset(self, reset_ticket: str, new_password: str) -> MessageResponse:
        verified_email = verify_password_reset_ticket(reset_ticket, consume=True)
        rate_limiter.enforce(f"pwdreset:complete:{verified_email}", max_attempts=10, window_seconds=600, action_name="password reset")

        try:
            validate_password_complexity(new_password)
        except ValueError as exc:
            raise BadRequestError(str(exc))

        user = await self.user_repo.get_by_email(verified_email)
        if not user or not user.is_active:
            raise NotFoundError("Account not found or inactive.")

        pwd_hash = hash_password(new_password)
        await self.user_repo.set_password_hash(user.id, pwd_hash)

        return MessageResponse(message="Password reset successfully. You can now sign in with your new password.")

    async def _create_tokens_for_user(
        self,
        user: User,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> TokenResponse:
        access_token = create_access_token(user_id=str(user.id), username=user.username)
        refresh_token = generate_secure_token(48)
        token_hash = hash_token(refresh_token)
        expires_at = utc_now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        await self.session_repo.create_session(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        has_pwd = bool(user.password_hash)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=expires_in,
            user=UserTokenPayload(
                id=user.id,
                email=user.email,
                username=user.username,
                display_name=user.display_name,
                avatar_url=user.avatar_url,
                has_password=has_pwd,
            ),
            has_password=has_pwd,
        )
