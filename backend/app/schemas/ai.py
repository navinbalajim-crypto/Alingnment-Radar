"""AI alignment and contextual recommendation schemas."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

MismatchCategory = Literal[
    "ambiguity",
    "deadlines",
    "scope",
    "goals",
    "responsibilities",
    "definition_of_done",
    "conflicting_interpretations",
    "unclear_references",
    "missing_details",
    "other",
]

AlignmentStatus = Literal[
    "detected",
    "clarifying",
    "awaiting_confirmation",
    "resolved",
    "dismissed",
    "reopened",
]


class AlignmentFindingItem(BaseModel):
    """A distinct alignment finding detected in conversation analysis."""

    mismatch_detected: bool = Field(True, description="Whether a misalignment or misunderstanding was identified")
    category: Optional[str] = Field("ambiguity", description="Category of mismatch or ambiguity")
    severity: Optional[str] = Field("medium", description="Severity level: low, medium, or high")
    title: Optional[str] = Field(None, description="Concise finding headline")
    explanation: str = Field(..., description="Neutral explanation of the perspective divergence")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0")
    supporting_message_ids: List[str] = Field(default_factory=list, description="IDs of messages providing evidence")
    clarification_question: Optional[str] = Field(None, description="Suggested neutral question to align parties")
    suggested_reply: Optional[str] = Field(None, description="Suggested reply to align conversation")
    intended_outcome: Optional[str] = Field(None, description="Identified shared goal or agreement target")
    suggested_rewrite: Optional[str] = Field(None, description="Optional neutral rewritten message text")


class AlignmentAnalysisResult(BaseModel):
    """
    Structured output from AI inference supporting batch message analysis,
    multiple distinct findings, and explicit message coverage tracking.
    """

    mismatch_detected: bool = Field(False, description="Whether any misalignment or misunderstanding was identified")
    findings: List[AlignmentFindingItem] = Field(default_factory=list, description="List of distinct alignment findings")
    analyzed_message_ids: List[str] = Field(default_factory=list, description="IDs of messages considered in this analysis")

    # Legacy fields preserved for backward compatibility
    category: Optional[str] = Field(None, description="Category of mismatch or ambiguity")
    severity: Optional[str] = Field("medium", description="Severity level: low, medium, or high")
    title: Optional[str] = Field(None, description="Concise finding headline")
    explanation: str = Field("", description="Neutral explanation of the perspective divergence")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0")
    supporting_message_ids: List[str] = Field(default_factory=list, description="IDs of messages providing evidence")
    clarification_question: Optional[str] = Field(None, description="Suggested neutral question to align parties")
    suggested_reply: Optional[str] = Field(None, description="Suggested reply to align conversation")
    intended_outcome: Optional[str] = Field(None, description="Identified shared goal or agreement target")
    suggested_rewrite: Optional[str] = Field(None, description="Optional neutral rewritten message text")

    @model_validator(mode="before")
    @classmethod
    def sync_findings_and_legacy_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        findings = data.get("findings")
        mismatch_detected = data.get("mismatch_detected", False)

        if findings:
            if not mismatch_detected:
                data["mismatch_detected"] = any(
                    (f.get("mismatch_detected", True) if isinstance(f, dict) else getattr(f, "mismatch_detected", True))
                    for f in findings
                )
            first_item = findings[0]
            if isinstance(first_item, dict):
                data.setdefault("category", first_item.get("category"))
                data.setdefault("severity", first_item.get("severity", "medium"))
                data.setdefault("title", first_item.get("title"))
                data.setdefault("explanation", first_item.get("explanation", ""))
                data.setdefault("confidence", first_item.get("confidence", 0.0))
                data.setdefault("clarification_question", first_item.get("clarification_question"))
                data.setdefault("suggested_reply", first_item.get("suggested_reply"))
                data.setdefault("suggested_rewrite", first_item.get("suggested_rewrite"))
                data.setdefault("intended_outcome", first_item.get("intended_outcome"))
            elif hasattr(first_item, "category"):
                data.setdefault("category", first_item.category)
                data.setdefault("severity", first_item.severity)
                data.setdefault("title", first_item.title)
                data.setdefault("explanation", first_item.explanation)
                data.setdefault("confidence", first_item.confidence)
                data.setdefault("clarification_question", first_item.clarification_question)
                data.setdefault("suggested_reply", first_item.suggested_reply)
                data.setdefault("suggested_rewrite", first_item.suggested_rewrite)
                data.setdefault("intended_outcome", first_item.intended_outcome)

            if not data.get("supporting_message_ids"):
                all_ids = []
                for f in findings:
                    ids = f.get("supporting_message_ids", []) if isinstance(f, dict) else getattr(f, "supporting_message_ids", [])
                    for mid in ids:
                        if mid not in all_ids:
                            all_ids.append(mid)
                data["supporting_message_ids"] = all_ids
        elif mismatch_detected:
            explanation = data.get("explanation", "")
            supp_ids = data.get("supporting_message_ids", [])
            data["findings"] = [
                {
                    "mismatch_detected": True,
                    "category": data.get("category") or "ambiguity",
                    "severity": data.get("severity", "medium") or "medium",
                    "title": data.get("title"),
                    "explanation": explanation,
                    "confidence": data.get("confidence", 0.0),
                    "supporting_message_ids": list(supp_ids),
                    "clarification_question": data.get("clarification_question"),
                    "suggested_reply": data.get("suggested_reply"),
                    "suggested_rewrite": data.get("suggested_rewrite"),
                    "intended_outcome": data.get("intended_outcome"),
                }
            ]

        return data



class ResolutionEvaluationResult(BaseModel):
    """Structured assessment evaluating whether conversation resolved an active alignment finding."""

    has_resolution_evidence: bool = Field(False, description="Whether evidence indicates the original ambiguity was addressed")
    is_resolved: bool = Field(..., description="Whether evidence indicates the original ambiguity was addressed")
    status_update: str = Field("clarifying", description="Updated status: clarifying, awaiting_confirmation, resolved, unresolved")
    evidence_summary: Optional[str] = Field(None, description="Specific textual evidence showing what was agreed/clarified")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Confidence in resolution assessment")


class AlignmentFindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    triggered_by_message_id: Optional[uuid.UUID] = None
    mismatch_detected: bool
    category: Optional[str] = None
    severity: Optional[str] = "medium"
    title: Optional[str] = None
    status: str = "detected"
    explanation: str
    confidence: float
    supporting_message_ids: List[str]
    clarification_question: Optional[str] = None
    suggested_reply: Optional[str] = None
    intended_outcome: Optional[str] = None
    status_history: List[Dict[str, Any]] = Field(default_factory=list)
    confirmations: List[Dict[str, Any]] = Field(default_factory=list)
    resolution_evidence: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by_id: Optional[uuid.UUID] = None
    suggested_rewrite: Optional[str] = None
    clarification_request_message_id: Optional[uuid.UUID] = None
    clarification_requested_by_id: Optional[uuid.UUID] = None
    clarification_requested_at: Optional[datetime] = None
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def sync_suggested_reply_and_rewrite(cls, data: Any) -> Any:
        if hasattr(data, "__dict__"):
            reply = getattr(data, "suggested_reply", None)
            rewrite = getattr(data, "suggested_rewrite", None)
            return {
                "id": data.id,
                "conversation_id": data.conversation_id,
                "triggered_by_message_id": data.triggered_by_message_id,
                "mismatch_detected": data.mismatch_detected,
                "category": data.category,
                "severity": getattr(data, "severity", "medium") or "medium",
                "title": getattr(data, "title", None),
                "status": getattr(data, "status", "detected") or "detected",
                "explanation": data.explanation,
                "confidence": data.confidence,
                "supporting_message_ids": data.supporting_message_ids or [],
                "clarification_question": data.clarification_question,
                "suggested_reply": reply or rewrite,
                "intended_outcome": getattr(data, "intended_outcome", None),
                "status_history": getattr(data, "status_history", []) or [],
                "confirmations": getattr(data, "confirmations", []) or [],
                "resolution_evidence": getattr(data, "resolution_evidence", None),
                "resolved_at": getattr(data, "resolved_at", None),
                "resolved_by_id": getattr(data, "resolved_by_id", None),
                "suggested_rewrite": rewrite or reply,
                "clarification_request_message_id": getattr(data, "clarification_request_message_id", None),
                "clarification_requested_by_id": getattr(data, "clarification_requested_by_id", None),
                "clarification_requested_at": getattr(data, "clarification_requested_at", None),
                "created_at": data.created_at,
            }
        elif isinstance(data, dict):
            if not data.get("suggested_rewrite") and data.get("suggested_reply"):
                data["suggested_rewrite"] = data["suggested_reply"]
            elif not data.get("suggested_reply") and data.get("suggested_rewrite"):
                data["suggested_reply"] = data["suggested_rewrite"]
        return data


class RecommendationItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    triggered_by_message_id: Optional[uuid.UUID] = None
    source: str
    title: str
    url: str
    snippet: Optional[str] = None
    category: Optional[str] = None
    published_date: Optional[str] = None
    extra_data: Dict[str, Any]
    is_shared_in_chat: bool
    is_dismissed: bool = False
    dismissed_by_id: Optional[uuid.UUID] = None
    created_at: datetime


class ConversationAiItemsResponse(BaseModel):
    findings: List[AlignmentFindingResponse]
    recommendations: List[RecommendationItemResponse]


class ConfirmAlignmentRequest(BaseModel):
    comment: Optional[str] = Field(None, description="Optional confirmation note from participant")


class ResolveAlignmentRequest(BaseModel):
    evidence: Optional[str] = Field(None, description="Manual resolution description or evidence note")


class DismissAlignmentRequest(BaseModel):
    reason: Optional[str] = Field(None, description="Optional dismissal reason")


class DismissRecommendationRequest(BaseModel):
    reason: Optional[str] = Field(None, description="Optional dismissal reason")


class ShareRecommendationRequest(BaseModel):
    recommendation_id: uuid.UUID


class RequestRecommendationsRequest(BaseModel):
    query: Optional[str] = Field(None, description="Optional custom search query. If omitted, derives from recent conversation.")
    category: Optional[str] = Field(None, description="Optional category: music, cricket, movie, place, web")


class TriggerAlignmentRequest(BaseModel):
    pass


# --- Draft Analysis Schemas ---

class DraftAnalysisRequest(BaseModel):
    draft: str = Field(..., min_length=1, max_length=5000, description="Current draft text in the composer")
    conversation_id: uuid.UUID = Field(..., description="Active conversation ID for context")
    draft_revision: str = Field(..., max_length=64, description="Client-side revision ID to prevent stale responses")


class DraftSuggestRequest(BaseModel):
    draft: str = Field(..., min_length=1, max_length=600, description="Text typed before the caret")
    conversation_id: uuid.UUID = Field(..., description="Active conversation ID for context")
    draft_revision: str = Field(..., max_length=64)


class CorrectionSuggestion(BaseModel):
    original: str = Field(..., description="The original text segment")
    corrected: str = Field(..., description="The suggested correction")
    reason: str = Field(..., description="Brief reason for the correction")
    confidence: float = Field(0.8, ge=0.0, le=1.0)


class CompletionSuggestion(BaseModel):
    text: str = Field(..., description="Suggested completion text")
    confidence: float = Field(0.7, ge=0.0, le=1.0)


class DraftSuggestResponse(BaseModel):
    draft_revision: str
    suggestions: List[CompletionSuggestion] = Field(default_factory=list)
    ai_available: bool = False


class DraftAnalysisResponse(BaseModel):
    draft_revision: str = Field(..., description="Echoed revision ID for staleness check")
    corrected_text: Optional[str] = Field(None, description="Full corrected version of the draft, if corrections exist")
    corrections: List[CorrectionSuggestion] = Field(default_factory=list)
    completions: List[CompletionSuggestion] = Field(default_factory=list)
    tone: Optional[str] = Field(None, description="Detected tone: professional, casual, academic, etc.")
    recommendations: List[RecommendationItemResponse] = Field(default_factory=list)
    ambiguity_detected: bool = Field(False, description="Whether the draft was detected as ambiguous or unclear")
    ambiguity_details: Optional[str] = Field(None, description="Explanation of missing details or ambiguity")
    suggested_actions: List[str] = Field(default_factory=list, description="Suggested actions to clarify message")
    clarification_prompt: Optional[str] = Field(None, description="Prompt asking sender for missing info")
    improved_draft: Optional[str] = Field(None, description="Improved draft template for sender to review and edit")
    ai_available: bool = Field(True, description="False when the writing assistant could not analyze this draft")
    ai_consent_required: bool = Field(False, description="True when external AI analysis is off because the user has not opted in")


class DraftRecommendationsRequest(BaseModel):
    draft: str = Field(..., min_length=1, max_length=5000, description="Current draft text in the composer")
    conversation_id: uuid.UUID = Field(..., description="Active conversation ID for context")
    draft_revision: str = Field(..., max_length=64, description="Client-side revision ID to prevent stale responses")


class DraftRecommendationsResponse(BaseModel):
    draft_revision: str = Field(..., description="Echoed revision ID for staleness check")
    has_intent: bool = Field(False, description="Whether contextual recommendation intent was recognized")
    category: Optional[str] = Field(None, description="Category of recommendations: music, movie, cricket, etc.")
    query: Optional[str] = Field(None, description="Resolved search query")
    recommendations: List[RecommendationItemResponse] = Field(default_factory=list)
