"""AI and contextual recommendations endpoints under /api/v1."""

import re
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.ai import (
    AlignmentFindingResponse,
    ConfirmAlignmentRequest,
    ConversationAiItemsResponse,
    CorrectionSuggestion,
    CompletionSuggestion,
    DismissAlignmentRequest,
    DismissRecommendationRequest,
    DraftAnalysisRequest,
    DraftAnalysisResponse,
    DraftRecommendationsRequest,
    DraftRecommendationsResponse,
    DraftSuggestRequest,
    DraftSuggestResponse,
    RecommendationItemResponse,
    RequestRecommendationsRequest,
    ResolveAlignmentRequest,
    TriggerAlignmentRequest,
)
from app.core.config import settings
from app.core.errors import ForbiddenError
from app.core.logging import logger
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.message_repo import MessageRepository
from app.services.ai_router import ai_router
from app.services.autocomplete_service import autocomplete_service
from app.schemas.events import ServerMessageNewPayload
from app.schemas.message import MessageRead
from app.services.alignment_service import AlignmentService
from app.services.recommendation_service import RecommendationService
from app.sockets.server import sio

router = APIRouter(tags=["AI & Recommendations"])


from app.services.spelling_engine import get_spelling_corrections
from app.services.ambiguity_detector import detect_draft_ambiguity


@router.post(
    "/draft/analyze",
    response_model=DraftAnalysisResponse,
    status_code=status.HTTP_200_OK,
)
async def analyze_draft(
    payload: DraftAnalysisRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Analyze a draft message for writing corrections and completions.
    Uses conversation context to determine tone and provide context-aware suggestions.
    Does not persist the draft or send any message.
    """
    conv_repo = ConversationRepository(db)
    is_member = await conv_repo.is_member(payload.conversation_id, current_user.id)
    if not is_member:
        raise ForbiddenError("You are not a member of this conversation.")

    msg_repo = MessageRepository(db)
    messages = await msg_repo.get_recent_messages(
        conversation_id=payload.conversation_id,
        limit=8,
    )

    context = [
        {
            "id": str(m.id),
            "sender_username": m.sender.username if m.sender else "User",
            "content": m.content,
        }
        for m in messages
    ]

    ambiguity_info = detect_draft_ambiguity(payload.draft, context)

    # Unsent drafts may only leave the server with the user's stored, explicit consent.
    # The decision is read from the database; nothing in the request can grant it.
    if not current_user.ai_draft_analysis_consent:
        return _local_only_draft_response(payload, ambiguity_info=ambiguity_info)

    try:
        result = await ai_router.analyze_draft(
            draft=payload.draft,
            conversation_context=context,
        )
    except Exception as exc:
        logger.warning(f"Draft analysis unavailable: {type(exc).__name__}")
        return DraftAnalysisResponse(
            draft_revision=payload.draft_revision,
            ai_available=False,
            ambiguity_detected=bool(ambiguity_info.get("ambiguity_detected")) if ambiguity_info else False,
            ambiguity_details=ambiguity_info.get("ambiguity_details") if ambiguity_info else None,
            suggested_actions=ambiguity_info.get("suggested_actions", []) if ambiguity_info else [],
            clarification_prompt=ambiguity_info.get("clarification_prompt") if ambiguity_info else None,
            improved_draft=ambiguity_info.get("improved_draft") if ambiguity_info else None,
        )

    if not isinstance(result, dict):
        return DraftAnalysisResponse(
            draft_revision=payload.draft_revision,
            ai_available=False,
            ambiguity_detected=bool(ambiguity_info.get("ambiguity_detected")) if ambiguity_info else False,
            ambiguity_details=ambiguity_info.get("ambiguity_details") if ambiguity_info else None,
            suggested_actions=ambiguity_info.get("suggested_actions", []) if ambiguity_info else [],
            clarification_prompt=ambiguity_info.get("clarification_prompt") if ambiguity_info else None,
            improved_draft=ambiguity_info.get("improved_draft") if ambiguity_info else None,
        )

    # In professional / mixed tone, enrich with high-confidence spelling mistakes
    tone = result.get("tone") or "professional"
    if tone != "casual":
        local_corrections, _ = get_spelling_corrections(payload.draft)
        existing_origs = {str(c.get("original", "")).lower() for c in result.get("corrections", []) if isinstance(c, dict)}
        for lc in local_corrections:
            if lc["original"].lower() not in existing_origs:
                if "corrections" not in result or not isinstance(result["corrections"], list):
                    result["corrections"] = []
                result["corrections"].append(lc)

    recommendations_list: List[RecommendationItemResponse] = []
    try:
        if not current_user.draft_recommendations_consent:
            raise PermissionError("draft recommendations not enabled")
        rec_service = RecommendationService(db)
        rec_res = await rec_service.evaluate_draft_recommendations(
            conversation_id=payload.conversation_id,
            draft=payload.draft,
            current_user_id=current_user.id,
        )
        recommendations_list = rec_res.get("recommendations", [])
    except Exception as exc:
        logger.debug(f"Draft recommendation skipped in analyze_draft: {type(exc).__name__}")

    return _build_draft_response(
        payload.draft,
        payload.draft_revision,
        result,
        recommendations=recommendations_list,
        ambiguity_info=ambiguity_info,
    )


@router.post(
    "/draft/suggest",
    response_model=DraftSuggestResponse,
    status_code=status.HTTP_200_OK,
)
async def suggest_draft_completions(
    payload: DraftSuggestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Opt-in AI autocomplete for the composer. Stateless: never stores the draft, never creates
    messages or alignment findings. Uses only this conversation's recent messages (membership checked).
    """
    conv_repo = ConversationRepository(db)
    if not await conv_repo.is_member(payload.conversation_id, current_user.id):
        raise ForbiddenError("You are not a member of this conversation.")

    empty = DraftSuggestResponse(draft_revision=payload.draft_revision, ai_available=False)
    if not current_user.ai_autocomplete_consent or not autocomplete_service.eligible(payload.draft):
        return empty

    messages = await MessageRepository(db).get_recent_messages(
        conversation_id=payload.conversation_id, limit=6
    )
    context = [
        {"id": str(m.id), "sender_username": m.sender.username if m.sender else "User", "content": m.content}
        for m in messages
    ]
    texts = await autocomplete_service.suggest(
        user_id=current_user.id,
        conversation_id=payload.conversation_id,
        draft=payload.draft,
        context=context,
        consent=bool(current_user.ai_autocomplete_consent),
    )
    if texts is None:
        return empty
    return DraftSuggestResponse(
        draft_revision=payload.draft_revision,
        suggestions=[CompletionSuggestion(text=t, confidence=0.7) for t in texts],
        ai_available=True,
    )


@router.post(
    "/draft/recommendations",
    response_model=DraftRecommendationsResponse,
    status_code=status.HTTP_200_OK,
)
async def analyze_draft_recommendations(
    payload: DraftRecommendationsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Evaluate contextual recommendations for the current draft in the composer.
    Returns real Spotify/YouTube recommendations without requiring message sending.
    """
    if not await ConversationRepository(db).is_member(payload.conversation_id, current_user.id):
        raise ForbiddenError("You are not a member of this conversation.")
    if not current_user.draft_recommendations_consent:
        return DraftRecommendationsResponse(draft_revision=payload.draft_revision, has_intent=False, recommendations=[])
    rec_service = RecommendationService(db)
    result = await rec_service.evaluate_draft_recommendations(
        conversation_id=payload.conversation_id,
        draft=payload.draft,
        current_user_id=current_user.id,
    )
    return DraftRecommendationsResponse(
        draft_revision=payload.draft_revision,
        has_intent=result.get("has_intent", False),
        category=result.get("category"),
        query=result.get("query"),
        recommendations=result.get("recommendations", []),
    )


def _local_only_draft_response(
    payload: DraftAnalysisRequest,
    ambiguity_info: Optional[dict] = None,
) -> DraftAnalysisResponse:
    """Consent not granted: only the local spelling engine runs; no external provider is contacted."""
    corrections = []
    for c in get_spelling_corrections(payload.draft)[0]:
        try:
            corrections.append(CorrectionSuggestion(
                original=c["original"], corrected=c["corrected"],
                reason=str(c.get("reason") or ""), confidence=float(c.get("confidence", 0.8)),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    corrected = payload.draft
    for c in corrections:
        corrected = corrected.replace(c.original, c.corrected)
    return DraftAnalysisResponse(
        draft_revision=payload.draft_revision,
        corrected_text=corrected if corrections and corrected != payload.draft else None,
        corrections=corrections,
        ambiguity_detected=bool(ambiguity_info.get("ambiguity_detected")) if ambiguity_info else False,
        ambiguity_details=ambiguity_info.get("ambiguity_details") if ambiguity_info else None,
        suggested_actions=ambiguity_info.get("suggested_actions", []) if ambiguity_info else [],
        clarification_prompt=ambiguity_info.get("clarification_prompt") if ambiguity_info else None,
        improved_draft=ambiguity_info.get("improved_draft") if ambiguity_info else None,
        ai_available=False,
        ai_consent_required=True,
    )


def _normalize_for_compare(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", text).lower()


def _build_draft_response(
    draft: str,
    revision: str,
    result: dict,
    recommendations: Optional[List[RecommendationItemResponse]] = None,
    ambiguity_info: Optional[dict] = None,
) -> DraftAnalysisResponse:
    corrections: List[CorrectionSuggestion] = []
    raw_corrections = result.get("corrections")
    for c in raw_corrections if isinstance(raw_corrections, list) else []:
        if not isinstance(c, dict):
            continue
        original = str(c.get("original") or "").strip()
        corrected = str(c.get("corrected") or "").strip()
        # Drop no-ops and punctuation/capitalisation-only nitpicks.
        if not original or not corrected or _normalize_for_compare(original) == _normalize_for_compare(corrected):
            continue
        try:
            corrections.append(CorrectionSuggestion(
                original=original,
                corrected=corrected,
                reason=str(c.get("reason") or ""),
                confidence=min(max(float(c.get("confidence", 0.8)), 0.0), 1.0),
            ))
        except (TypeError, ValueError):
            continue

    corrected_text = result.get("corrected_text")
    if not corrections:
        corrected_text = None
    elif not isinstance(corrected_text, str) or not corrected_text.strip() or corrected_text.strip() == draft.strip():
        temp = draft
        for c in corrections:
            temp = temp.replace(c.original, c.corrected)
        corrected_text = temp if temp != draft else None

    completions: List[CompletionSuggestion] = []
    draft_norm = _normalize_for_compare(draft)
    raw_completions = result.get("completions")
    # A draft ending in sentence punctuation is finished; don't pad it with suggested extra sentences.
    if not re.search(r"[.!?]\s*$", draft):
        for comp in raw_completions if isinstance(raw_completions, list) else []:
            if not isinstance(comp, dict):
                continue
            text = str(comp.get("text") or "").strip()
            text_norm = _normalize_for_compare(text)
            if not text or text_norm == draft_norm or not text_norm.startswith(draft_norm[: max(len(draft_norm) - 3, 1)]):
                continue
            try:
                completions.append(CompletionSuggestion(
                    text=text,
                    confidence=min(max(float(comp.get("confidence", 0.7)), 0.0), 1.0),
                ))
            except (TypeError, ValueError):
                continue
            if len(completions) == 2:
                break

    tone = result.get("tone")
    return DraftAnalysisResponse(
        draft_revision=revision,
        corrected_text=corrected_text,
        corrections=corrections,
        completions=completions,
        tone=tone if isinstance(tone, str) else None,
        recommendations=recommendations or [],
        ambiguity_detected=bool(ambiguity_info.get("ambiguity_detected")) if ambiguity_info else False,
        ambiguity_details=ambiguity_info.get("ambiguity_details") if ambiguity_info else None,
        suggested_actions=ambiguity_info.get("suggested_actions", []) if ambiguity_info else [],
        clarification_prompt=ambiguity_info.get("clarification_prompt") if ambiguity_info else None,
        improved_draft=ambiguity_info.get("improved_draft") if ambiguity_info else None,
    )


@router.get(
    "/conversations/{conversation_id}/ai-items",
    response_model=ConversationAiItemsResponse,
    status_code=status.HTTP_200_OK,
)
async def get_conversation_ai_items(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve persisted AI alignment findings and contextual recommendations for a conversation."""
    alignment_service = AlignmentService(db)
    recommendation_service = RecommendationService(db)

    findings = await alignment_service.get_conversation_findings(
        conversation_id=conversation_id,
        current_user_id=current_user.id,
    )
    recommendations = await recommendation_service.get_conversation_recommendations(
        conversation_id=conversation_id,
        current_user_id=current_user.id,
    )

    return ConversationAiItemsResponse(
        findings=findings,
        recommendations=recommendations,
    )


@router.post(
    "/conversations/{conversation_id}/recommendations/{recommendation_id}/share",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
)
async def share_recommendation_in_chat(
    conversation_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Explicitly share a selected contextual recommendation into the conversation.
    Creates a link_share chat message and broadcasts to room.
    """
    recommendation_service = RecommendationService(db)
    message = await recommendation_service.share_recommendation_in_chat(
        conversation_id=conversation_id,
        recommendation_id=recommendation_id,
        current_user_id=current_user.id,
    )

    # Broadcast shared message to Socket.IO room
    room_name = f"conversation:{conversation_id}"
    new_event = ServerMessageNewPayload(message=message)
    await sio.emit("message:new", new_event.model_dump(mode="json"), room=room_name)

    return message


@router.post(
    "/conversations/{conversation_id}/recommendations/request",
    response_model=List[RecommendationItemResponse],
    status_code=status.HTTP_200_OK,
)
async def request_conversation_recommendations(
    conversation_id: uuid.UUID,
    payload: Optional[RequestRecommendationsRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Explicitly request contextual recommendations for the conversation.
    Searches external providers (YouTube, Spotify, Tavily), persists new items,
    and broadcasts to the conversation room.
    """
    recommendation_service = RecommendationService(db)
    query = payload.query if payload else None
    category = payload.category if payload else None

    items = await recommendation_service.request_recommendations(
        conversation_id=conversation_id,
        current_user_id=current_user.id,
        query=query,
        category=category,
    )
    await db.commit()

    room_name = f"conversation:{conversation_id}"
    for rec in items:
        await sio.emit(
            "ai:recommendation",
            {"recommendation": rec.model_dump(mode="json")},
            room=room_name,
        )

    return items


@router.post(
    "/conversations/{conversation_id}/alignment/analyze",
    response_model=Optional[AlignmentFindingResponse],
    status_code=status.HTTP_200_OK,
)
async def trigger_conversation_alignment(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Explicitly trigger alignment analysis on the conversation history.
    Detects ambiguities or misunderstandings, persists findings,
    and broadcasts to the conversation room.
    """
    alignment_service = AlignmentService(db)
    finding = await alignment_service.trigger_alignment_analysis(
        conversation_id=conversation_id,
        current_user_id=current_user.id,
    )
    await db.commit()

    created_findings = getattr(alignment_service, "last_created_findings", [])
    room_name = f"conversation:{conversation_id}"
    if created_findings:
        for f in created_findings:
            if f.mismatch_detected:
                await sio.emit(
                    "ai:alignment",
                    {"finding": f.model_dump(mode="json")},
                    room=room_name,
                )
    elif finding and finding.mismatch_detected and alignment_service.last_was_new:
        await sio.emit(
            "ai:alignment",
            {"finding": finding.model_dump(mode="json")},
            room=room_name,
        )

    return finding


@router.post(
    "/conversations/{conversation_id}/alignment/{finding_id}/request-clarification",
    response_model=AlignmentFindingResponse,
    status_code=status.HTTP_200_OK,
)
async def request_alignment_clarification(
    conversation_id: uuid.UUID,
    finding_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Receiver asks the author to clarify; posts a linked request message in the same conversation."""
    alignment_service = AlignmentService(db)
    finding, message, created = await alignment_service.request_clarification(
        conversation_id=conversation_id,
        finding_id=finding_id,
        current_user_id=current_user.id,
    )
    await db.commit()

    if created:
        room_name = f"conversation:{conversation_id}"
        await sio.emit("message:new", ServerMessageNewPayload(message=message).model_dump(mode="json"), room=room_name)
        await sio.emit("ai:alignment_update", {"finding": finding.model_dump(mode="json")}, room=room_name)
    return finding


@router.post(
    "/conversations/{conversation_id}/alignment/{finding_id}/confirm",
    response_model=AlignmentFindingResponse,
    status_code=status.HTTP_200_OK,
)
async def confirm_conversation_alignment(
    conversation_id: uuid.UUID,
    finding_id: uuid.UUID,
    payload: Optional[ConfirmAlignmentRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Confirm an alignment resolution or clarification from a conversation participant."""
    alignment_service = AlignmentService(db)
    comment = payload.comment if payload else None
    finding = await alignment_service.confirm_alignment_finding(
        conversation_id=conversation_id,
        finding_id=finding_id,
        current_user_id=current_user.id,
        comment=comment,
    )
    await db.commit()

    room_name = f"conversation:{conversation_id}"
    await sio.emit(
        "ai:alignment_update",
        {"finding": finding.model_dump(mode="json")},
        room=room_name,
    )
    return finding


@router.post(
    "/conversations/{conversation_id}/alignment/{finding_id}/resolve",
    response_model=AlignmentFindingResponse,
    status_code=status.HTTP_200_OK,
)
async def resolve_conversation_alignment(
    conversation_id: uuid.UUID,
    finding_id: uuid.UUID,
    payload: Optional[ResolveAlignmentRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Explicitly mark an alignment finding as resolved with evidence summary."""
    alignment_service = AlignmentService(db)
    evidence = payload.evidence if payload else None
    finding = await alignment_service.resolve_alignment_finding(
        conversation_id=conversation_id,
        finding_id=finding_id,
        current_user_id=current_user.id,
        evidence=evidence,
    )
    await db.commit()

    room_name = f"conversation:{conversation_id}"
    await sio.emit(
        "ai:alignment_update",
        {"finding": finding.model_dump(mode="json")},
        room=room_name,
    )
    return finding


@router.post(
    "/conversations/{conversation_id}/alignment/{finding_id}/dismiss",
    response_model=AlignmentFindingResponse,
    status_code=status.HTTP_200_OK,
)
async def dismiss_conversation_alignment(
    conversation_id: uuid.UUID,
    finding_id: uuid.UUID,
    payload: Optional[DismissAlignmentRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dismiss an alignment finding so it no longer appears in the active chat view."""
    alignment_service = AlignmentService(db)
    reason = payload.reason if payload else None
    finding = await alignment_service.dismiss_alignment_finding(
        conversation_id=conversation_id,
        finding_id=finding_id,
        current_user_id=current_user.id,
        reason=reason,
    )
    await db.commit()

    room_name = f"conversation:{conversation_id}"
    await sio.emit(
        "ai:alignment_update",
        {"finding": finding.model_dump(mode="json")},
        room=room_name,
    )
    return finding


@router.post(
    "/conversations/{conversation_id}/recommendations/{recommendation_id}/dismiss",
    response_model=RecommendationItemResponse,
    status_code=status.HTTP_200_OK,
)
async def dismiss_conversation_recommendation(
    conversation_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    payload: Optional[DismissRecommendationRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dismiss a recommendation item so it is hidden from the drawer."""
    recommendation_service = RecommendationService(db)
    dismissed = await recommendation_service.dismiss_recommendation(
        conversation_id=conversation_id,
        recommendation_id=recommendation_id,
        current_user_id=current_user.id,
    )
    await db.commit()

    room_name = f"conversation:{conversation_id}"
    await sio.emit(
        "ai:recommendation_dismiss",
        {"recommendation_id": str(recommendation_id), "conversation_id": str(conversation_id)},
        room=room_name,
    )
    return dismissed
 
 
@router.get(
    "/routing-stats",
    status_code=status.HTTP_200_OK,
)
async def get_routing_stats(
    current_user: User = Depends(get_current_user),
):
    """
    Returns telemetry metrics for AI provider routing, EWMA latency, circuit breaker states,
    and fallback statistics without exposing API keys or private message text.
    """
    return ai_router.get_routing_stats()
