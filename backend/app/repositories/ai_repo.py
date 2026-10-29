"""AI repository for alignment findings and recommendation records with lifecycle support."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.base import utc_now
from app.models.alignment import AlignmentFinding
from app.models.message import Message
from app.models.recommendation import RecommendationItem


class AiRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_alignment_finding(
        self,
        conversation_id: uuid.UUID,
        mismatch_detected: bool,
        explanation: str,
        confidence: float,
        supporting_message_ids: List[str],
        category: Optional[str] = None,
        title: Optional[str] = None,
        severity: str = "medium",
        status: str = "detected",
        clarification_question: Optional[str] = None,
        suggested_reply: Optional[str] = None,
        intended_outcome: Optional[str] = None,
        triggered_by_message_id: Optional[uuid.UUID] = None,
    ) -> AlignmentFinding:
        now = utc_now()
        initial_history = [
            {
                "status": status,
                "changed_at": now.isoformat(),
                "reason": "Initial detection",
            }
        ]
        finding = AlignmentFinding(
            conversation_id=conversation_id,
            triggered_by_message_id=triggered_by_message_id,
            mismatch_detected=mismatch_detected,
            category=category,
            title=title,
            severity=severity or "medium",
            status=status,
            explanation=explanation,
            confidence=confidence,
            supporting_message_ids=supporting_message_ids,
            clarification_question=clarification_question,
            suggested_reply=suggested_reply,
            intended_outcome=intended_outcome,
            status_history=initial_history,
            confirmations=[],
            created_at=now,
        )
        self.session.add(finding)
        await self.session.flush()
        return finding

    async def get_finding_by_id(
        self, finding_id: uuid.UUID
    ) -> Optional[AlignmentFinding]:
        stmt = select(AlignmentFinding).where(AlignmentFinding.id == finding_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_findings_by_conversation(
        self, conversation_id: uuid.UUID, limit: int = 50
    ) -> List[AlignmentFinding]:
        stmt = (
            select(AlignmentFinding)
            .where(AlignmentFinding.conversation_id == conversation_id)
            .order_by(AlignmentFinding.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_unresolved_findings(
        self, conversation_id: uuid.UUID
    ) -> List[AlignmentFinding]:
        """Fetch all non-resolved, non-dismissed alignment findings for a conversation."""
        stmt = (
            select(AlignmentFinding)
            .where(
                AlignmentFinding.conversation_id == conversation_id,
                AlignmentFinding.mismatch_detected.is_(True),
                AlignmentFinding.status.notin_(["resolved", "dismissed"]),
            )
            .order_by(AlignmentFinding.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_finding(
        self, conversation_id: uuid.UUID
    ) -> Optional[AlignmentFinding]:
        stmt = (
            select(AlignmentFinding)
            .where(
                AlignmentFinding.conversation_id == conversation_id,
                AlignmentFinding.mismatch_detected.is_(True),
            )
            .order_by(AlignmentFinding.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_finding_status(
        self,
        finding: AlignmentFinding,
        new_status: str,
        reason: str,
        user_id: Optional[uuid.UUID] = None,
        evidence: Optional[str] = None,
    ) -> AlignmentFinding:
        """Update finding status, append to status history, and record resolution metadata."""
        now = utc_now()
        finding.status = new_status
        if evidence:
            finding.resolution_evidence = evidence
        if new_status == "resolved":
            finding.resolved_at = now
            finding.resolved_by_id = user_id

        current_history = list(finding.status_history or [])
        current_history.append({
            "status": new_status,
            "changed_at": now.isoformat(),
            "reason": reason,
            "user_id": str(user_id) if user_id else None,
            "evidence": evidence,
        })
        finding.status_history = current_history
        await self.session.flush()
        return finding

    async def merge_finding_evidence(
        self,
        finding: AlignmentFinding,
        extra_message_ids: List[str],
    ) -> AlignmentFinding:
        """Fold newly-cited evidence into an existing finding when a repeat detection is suppressed,
        so later messages referencing only the new evidence still match this same issue."""
        current = list(finding.supporting_message_ids or [])
        merged = current + [mid for mid in extra_message_ids if mid not in current]
        if merged != current:
            finding.supporting_message_ids = merged
            await self.session.flush()
        return finding

    async def add_finding_confirmation(
        self,
        finding: AlignmentFinding,
        user_id: uuid.UUID,
        username: str,
        comment: Optional[str] = None,
    ) -> AlignmentFinding:
        """Record participant confirmation for an alignment finding."""
        now = utc_now()
        existing_confirmations = list(finding.confirmations or [])
        user_id_str = str(user_id)
        if not any(c.get("user_id") == user_id_str for c in existing_confirmations):
            existing_confirmations.append({
                "user_id": user_id_str,
                "username": username,
                "confirmed_at": now.isoformat(),
                "comment": comment,
            })
            finding.confirmations = existing_confirmations
            await self.session.flush()
        return finding

    async def dismiss_finding(
        self,
        finding: AlignmentFinding,
        user_id: uuid.UUID,
        reason: Optional[str] = None,
    ) -> AlignmentFinding:
        """Dismiss an alignment finding."""
        return await self.update_finding_status(
            finding=finding,
            new_status="dismissed",
            reason=reason or "Dismissed by participant",
            user_id=user_id,
        )

    async def create_recommendation(
        self,
        conversation_id: uuid.UUID,
        source: str,
        title: str,
        url: str,
        snippet: Optional[str] = None,
        category: Optional[str] = None,
        published_date: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None,
        triggered_by_message_id: Optional[uuid.UUID] = None,
    ) -> RecommendationItem:
        item = RecommendationItem(
            conversation_id=conversation_id,
            triggered_by_message_id=triggered_by_message_id,
            source=source,
            title=title,
            url=url,
            snippet=snippet,
            category=category,
            published_date=published_date,
            extra_data=extra_data or {},
            is_shared_in_chat=False,
            is_dismissed=False,
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def get_recommendations_by_conversation(
        self,
        conversation_id: uuid.UUID,
        limit: int = 50,
        include_dismissed: bool = False,
        recent_message_window: Optional[int] = None,
    ) -> List[RecommendationItem]:
        stmt = (
            select(RecommendationItem)
            .where(RecommendationItem.conversation_id == conversation_id)
        )
        if recent_message_window:
            recent_ids = (
                select(Message.id)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.desc())
                .limit(recent_message_window)
            )
            stmt = stmt.where(RecommendationItem.triggered_by_message_id.in_(recent_ids))
        if not include_dismissed:
            stmt = stmt.where(RecommendationItem.is_dismissed.is_(False))
        stmt = stmt.order_by(RecommendationItem.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_recommendation_by_id(
        self, recommendation_id: uuid.UUID
    ) -> Optional[RecommendationItem]:
        stmt = select(RecommendationItem).where(RecommendationItem.id == recommendation_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_recommendation_shared(
        self, item: RecommendationItem
    ) -> None:
        item.is_shared_in_chat = True
        await self.session.flush()

    async def dismiss_recommendation(
        self, item: RecommendationItem, user_id: uuid.UUID
    ) -> RecommendationItem:
        """Mark recommendation as dismissed by participant."""
        item.is_dismissed = True
        item.dismissed_by_id = user_id
        await self.session.flush()
        return item
