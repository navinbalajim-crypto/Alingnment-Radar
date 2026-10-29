"""Services package."""

from app.services.email_service import EmailService, email_service
from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.services.conversation_service import ConversationService
from app.services.group_service import GroupService
from app.services.invitation_service import InvitationService
from app.services.alignment_service import AlignmentService
from app.services.recommendation_service import RecommendationService
from app.services.google_auth_service import GoogleAuthService
from app.services.contact_service import ContactService
from app.services.gmail_service import GmailNotificationService

__all__ = [
    "EmailService",
    "email_service",
    "AuthService",
    "UserService",
    "ConversationService",
    "GroupService",
    "InvitationService",
    "AlignmentService",
    "RecommendationService",
    "GoogleAuthService",
    "ContactService",
    "GmailNotificationService",
]


