"""Schemas package."""

from app.schemas.auth import (
    RequestCodeRequest,
    RequestCodeResponse,
    VerifyCodeRequest,
    VerifyRegisterCodeResponse,
    CompleteRegistrationRequest,
    TokenResponse,
    RefreshTokenRequest,
    LogoutRequest,
    MessageResponse,
)
from app.schemas.user import UserPublic, UserPrivate, UsernameAvailabilityResponse
from app.schemas.conversation import (
    CreateDirectConversationRequest,
    ConversationSummary,
    ConversationDetail,
)
from app.schemas.message import MessageCreate, MessageRead, MessageHistoryResponse
from app.schemas.group import (
    CreateGroupRequest,
    GroupMemberResponse,
    GroupDetailResponse,
    CreateInvitationRequest,
    InvitationResponse,
)
from app.schemas.invitation import (
    InvitationPreviewResponse,
    InvitationRequestCodeRequest,
    InvitationVerifyCodeRequest,
    InvitationVerifyCodeResponse,
    InvitationCompleteRegistrationRequest,
)
from app.schemas.ai import (
    AlignmentAnalysisResult,
    AlignmentFindingResponse,
    RecommendationItemResponse,
    ConversationAiItemsResponse,
    ShareRecommendationRequest,
    ConfirmAlignmentRequest,
    ResolveAlignmentRequest,
    DismissAlignmentRequest,
    DismissRecommendationRequest,
)
from app.schemas.events import (
    ClientJoinPayload,
    ClientSendMessagePayload,
    ServerMessageAckPayload,
    ServerMessageNewPayload,
    ServerMessageErrorPayload,
    ServerAiAlignmentPayload,
    ServerAiRecommendationPayload,
)
from app.schemas.oauth import (
    GoogleAuthUrlResponse,
    GoogleAuthCallbackRequest,
    OAuthStatusResponse,
)
from app.schemas.contact import (
    ContactItem,
    ContactListResponse,
    SyncContactsResponse,
)

__all__ = [
    "RequestCodeRequest",
    "RequestCodeResponse",
    "VerifyCodeRequest",
    "VerifyRegisterCodeResponse",
    "CompleteRegistrationRequest",
    "TokenResponse",
    "RefreshTokenRequest",
    "LogoutRequest",
    "MessageResponse",
    "UserPublic",
    "UserPrivate",
    "UsernameAvailabilityResponse",
    "CreateDirectConversationRequest",
    "ConversationSummary",
    "ConversationDetail",
    "MessageCreate",
    "MessageRead",
    "MessageHistoryResponse",
    "CreateGroupRequest",
    "GroupMemberResponse",
    "GroupDetailResponse",
    "CreateInvitationRequest",
    "InvitationResponse",
    "InvitationPreviewResponse",
    "InvitationRequestCodeRequest",
    "InvitationVerifyCodeRequest",
    "InvitationVerifyCodeResponse",
    "InvitationCompleteRegistrationRequest",
    "AlignmentAnalysisResult",
    "AlignmentFindingResponse",
    "RecommendationItemResponse",
    "ConversationAiItemsResponse",
    "ShareRecommendationRequest",
    "ClientJoinPayload",
    "ClientSendMessagePayload",
    "ServerMessageAckPayload",
    "ServerMessageNewPayload",
    "ServerMessageErrorPayload",
    "ServerAiAlignmentPayload",
    "ServerAiRecommendationPayload",
    "GoogleAuthUrlResponse",
    "GoogleAuthCallbackRequest",
    "OAuthStatusResponse",
    "ContactItem",
    "ContactListResponse",
    "SyncContactsResponse",
]
