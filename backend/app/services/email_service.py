"""Email service orchestrating email delivery for authentication and invitations."""

from app.core.logging import logger
from app.providers.email_provider import email_provider


class EmailService:
    def __init__(self, provider=email_provider):
        self.provider = provider

    async def send_auth_code(self, email: str, code: str, purpose: str = "registration") -> bool:
        """Send verification OTP code to user."""
        logger.info(f"Sending {purpose} code to email")
        return await self.provider.send_verification_email(
            recipient_email=email,
            code=code,
            purpose=purpose,
        )

    async def send_invitation_code(self, email: str, code: str, group_title: str) -> bool:
        """Send verification OTP code for group invitation onboarding."""
        logger.info("Sending group invitation verification code to email")
        return await self.provider.send_verification_email(
            recipient_email=email,
            code=code,
            purpose=f"joining '{group_title}'",
        )


email_service = EmailService()
