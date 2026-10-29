"""AI Alignment Detection service managing conversation analysis, lifecycle, and resolution."""

import asyncio
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.errors import ForbiddenError, NotFoundError
from app.core.logging import logger
from app.db.base import utc_now
from app.models.alignment import AlignmentFinding
from app.models.message import Message
from app.repositories.ai_repo import AiRepository
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.user_repo import UserRepository
from app.schemas.ai import AlignmentFindingResponse
from app.services.ai_router import ai_router

# In-memory timestamp tracking for cooldown per conversation
_last_analysis_time: Dict[uuid.UUID, float] = {}

# Serializes detection per conversation so concurrent Check Alignment calls cannot both insert.
_conversation_locks: Dict[uuid.UUID, asyncio.Lock] = {}

_CLOSED_STATUSES = ("resolved", "dismissed")
_STOPWORDS = {"the", "a", "an", "of", "for", "to", "in", "on", "and", "is", "unclear", "missing", "detected"}


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _closed_at(finding: AlignmentFinding) -> datetime:
    if finding.resolved_at:
        return _aware(finding.resolved_at)
    for entry in reversed(finding.status_history or []):
        if entry.get("status") in _CLOSED_STATUSES and entry.get("changed_at"):
            try:
                return _aware(datetime.fromisoformat(entry["changed_at"]))
            except ValueError:
                break
    return _aware(finding.created_at)


def _title_tokens(title: Optional[str]) -> Set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (title or "").lower()) if t not in _STOPWORDS}


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class AlignmentService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.ai_repo = AiRepository(session)
        self.conv_repo = ConversationRepository(session)
        self.message_repo = MessageRepository(session)
        self.user_repo = UserRepository(session)
        self.last_was_new = False
        self.last_ai_failed = False
        self.last_outcome = "no_issue"
        self.last_created_findings: List[AlignmentFindingResponse] = []

    async def analyze_conversation(
        self,
        conversation_id: uuid.UUID,
        triggering_message_id: Optional[uuid.UUID] = None,
    ) -> Optional[AlignmentFindingResponse]:
        """
        Automatic (post-message) analysis. Enforces cooldown, then runs the shared
        detect/dedupe/persist path so resolved issues are never re-created.
        """
        if not settings.AI_ANALYSIS_ENABLED:
            return None

        if not (settings.is_provider_configured("nvidia") or settings.is_provider_configured("groq")):
            logger.info("Neither NVIDIA nor Groq provider configured; skipping alignment analysis.")
            return None

        now = time.time()
        last_time = _last_analysis_time.get(conversation_id, 0.0)
        if now - last_time < settings.AI_COOLDOWN_SECONDS:
            logger.info(f"Alignment analysis skipped due to cooldown ({int(now - last_time)}s < {settings.AI_COOLDOWN_SECONDS}s)")
            return None

        try:
            finding = await self._detect_and_persist(conversation_id, triggering_message_id)
        except Exception as exc:
            logger.error(f"Alignment analysis error: {type(exc).__name__}: {exc}")
            return None

        if finding is not None and self.last_was_new:
            _last_analysis_time[conversation_id] = now
            return finding
        return None

    async def _detect_and_persist_batch(
        self,
        conversation_id: uuid.UUID,
        target_messages: Optional[List[Message]] = None,
    ) -> Tuple[List[AlignmentFindingResponse], Set[str], Dict[str, str]]:
        """
        Batch serialized path for detection:
        - Loads existing findings (including resolved) and context
        - Executes multi-finding AI detection
        - Validates each candidate finding and deduplicates against existing (and batch-sibling) findings
        - Persists all genuinely distinct new findings
        - Returns (new_findings, analyzed_message_ids, outcomes_by_message_id)
        """
        self.last_was_new = False
        self.last_ai_failed = False
        self.last_outcome = "no_issue"
        self.last_created_findings = []
        async with _conversation_locks.setdefault(conversation_id, asyncio.Lock()):
            messages = await self.message_repo.get_recent_messages(
                conversation_id=conversation_id,
                limit=settings.MAX_CONVERSATION_CONTEXT_MESSAGES,
            )
            if not messages:
                return [], set(), {}

            valid_message_ids: Set[str] = {str(m.id) for m in messages}
            message_times = {str(m.id): m.created_at for m in messages}
            context = [
                {
                    "id": str(m.id),
                    "sender_username": m.sender.username if m.sender else "User",
                    "content": m.content,
                }
                for m in messages
            ]
            existing = await self.ai_repo.get_findings_by_conversation(conversation_id, limit=200)
            established = self._build_established_context(existing)

            # Integrate Live Conversation Context Graph into Intent Mirror AI
            try:
                from app.services.context_graph_service import ContextGraphService
                c_service = ContextGraphService(self.session)
                graph = await c_service.get_conversation_graph(conversation_id)
                for node in graph.active_nodes:
                    established.append({
                        "issue": f"{node.node_type.upper()}: {node.topic} (assigned: @{node.responsible_person or 'unassigned'})",
                        "confirmed_answer": f"Status: {node.status}; Deadline: {node.deadline or 'none specified'}",
                    })
            except Exception as exc:
                logger.debug(f"Context graph integration notice: {exc}")

            target_ids = [str(m.id) for m in target_messages] if target_messages else None

            result = await ai_router.detect_alignment(
                conversation_context=context,
                valid_message_ids=valid_message_ids,
                established_context=established,
                target_message_ids=target_ids,
            )
            if result is None:
                self.last_ai_failed = True
                self.last_outcome = "provider_failed"
                return [], set(), {}

            explicit_coverage = bool(result.analyzed_message_ids)
            if explicit_coverage:
                analyzed_ids: Set[str] = set(
                    str(mid) for mid in result.analyzed_message_ids if str(mid) in valid_message_ids
                )
            else:
                analyzed_ids: Set[str] = set(target_ids) if target_ids else set(valid_message_ids)


            # Re-read inside the lock so concurrent commits are visible
            existing = await self.ai_repo.get_findings_by_conversation(conversation_id, limit=200)

            outcomes_by_id: Dict[str, str] = {}
            created_findings: List[AlignmentFinding] = []
            accepted_in_batch: List[AlignmentFinding] = []

            for item in (result.findings or []):
                if not item.mismatch_detected:
                    continue

                grounded_ids = [
                    str(mid) for mid in (item.supporting_message_ids or [])
                    if str(mid) in valid_message_ids
                ]
                if not grounded_ids:
                    if target_ids and len(target_ids) == 1:
                        grounded_ids = list(target_ids)
                    else:
                        continue

                analyzed_ids.update(grounded_ids)

                # 1. Deduplicate against existing findings in DB
                match = self._match_existing_finding(
                    existing, grounded_ids, item.category, item.title, message_times
                )
                if match is not None:
                    logger.info(f"Suppressing repeat of {match.status} alignment finding {match.id}")
                    if match.status not in _CLOSED_STATUSES:
                        await self.ai_repo.merge_finding_evidence(match, grounded_ids)
                    for mid in grounded_ids:
                        outcomes_by_id.setdefault(mid, "duplicate_suppressed")
                    continue

                # 2. Deduplicate against findings accepted earlier in this same batch
                batch_match = None
                new_tokens = _title_tokens(item.title)
                for accepted in accepted_in_batch:
                    overlap = bool(set(grounded_ids) & set(accepted.supporting_message_ids or []))
                    similar_title = _jaccard(new_tokens, _title_tokens(accepted.title)) >= 0.5
                    # Same evidence (even under a different category/title) or same category with a
                    # similar title both indicate the same underlying issue (see _match_existing_finding).
                    if overlap or (accepted.category == item.category and similar_title):
                        batch_match = accepted
                        break

                if batch_match is not None:
                    logger.info(f"Deduplicating sibling finding in batch: matches {batch_match.title}")
                    await self.ai_repo.merge_finding_evidence(batch_match, grounded_ids)
                    for mid in grounded_ids:
                        outcomes_by_id.setdefault(mid, "finding_created")
                    continue

                # 3. New genuinely distinct finding!
                anchor_id: Optional[uuid.UUID] = None
                if target_ids:
                    target_set = set(target_ids)
                    for mid in reversed(grounded_ids):
                        if mid in target_set:
                            anchor_id = uuid.UUID(mid)
                            break
                if anchor_id is None and grounded_ids:
                    anchor_id = uuid.UUID(grounded_ids[-1])
                if anchor_id is None:
                    anchor_id = messages[-1].id

                finding = await self.ai_repo.create_alignment_finding(
                    conversation_id=conversation_id,
                    triggered_by_message_id=anchor_id,
                    mismatch_detected=True,
                    category=item.category,
                    title=item.title,
                    severity=item.severity or "medium",
                    status="detected",
                    explanation=item.explanation,
                    confidence=item.confidence,
                    supporting_message_ids=grounded_ids,
                    clarification_question=item.clarification_question,
                    suggested_reply=item.suggested_reply or item.suggested_rewrite,
                    intended_outcome=item.intended_outcome,
                )
                created_findings.append(finding)
                accepted_in_batch.append(finding)
                for mid in grounded_ids:
                    outcomes_by_id[mid] = "finding_created"

            for mid in analyzed_ids:
                outcomes_by_id.setdefault(mid, "no_issue")

            await self.session.commit()

            response_findings = [AlignmentFindingResponse.model_validate(f) for f in created_findings]
            self.last_was_new = len(response_findings) > 0
            self.last_created_findings = response_findings
            if response_findings:
                self.last_outcome = "finding_created"
            elif any(v == "duplicate_suppressed" for v in outcomes_by_id.values()):
                self.last_outcome = "duplicate_suppressed"
            else:
                self.last_outcome = "no_issue"

            return response_findings, analyzed_ids, outcomes_by_id

    async def _detect_and_persist(
        self,
        conversation_id: uuid.UUID,
        triggering_message_id: Optional[uuid.UUID] = None,
    ) -> Optional[AlignmentFindingResponse]:
        """
        Single serialized path for detection: preserves backward compatibility with single finding callers.
        """
        target = None
        if triggering_message_id:
            msg = await self.message_repo.get_by_id(triggering_message_id)
            if msg:
                target = [msg]
        findings, analyzed, outcomes = await self._detect_and_persist_batch(conversation_id, target_messages=target)
        if findings:
            return findings[0]
        existing = await self.ai_repo.get_findings_by_conversation(conversation_id, limit=200)
        active = [f for f in existing if f.mismatch_detected and f.status not in _CLOSED_STATUSES]
        if active and self.last_outcome == "duplicate_suppressed":
            return AlignmentFindingResponse.model_validate(active[0])
        return None

    @staticmethod
    def _build_established_context(findings: List[AlignmentFinding]) -> List[Dict[str, str]]:
        """Concise record of resolved issues and their confirmed answers (this conversation only)."""
        established: List[Dict[str, str]] = []
        for f in findings:
            if f.status != "resolved":
                continue
            comments = [c.get("comment") for c in (f.confirmations or []) if c.get("comment")]
            answer = f.resolution_evidence or "; ".join(comments)
            established.append({
                "issue": (f.clarification_question or f.title or f.explanation or "")[:300],
                "confirmed_answer": (answer or "")[:300],
            })
            if len(established) >= 10:
                break
        return established

    @staticmethod
    def _match_existing_finding(
        findings: List[AlignmentFinding],
        grounded_ids: List[str],
        category: Optional[str],
        title: Optional[str],
        message_times: Dict[str, datetime],
    ) -> Optional[AlignmentFinding]:
        """
        Semantic duplicate check independent of AI wording. A new result repeats an existing
        finding when it cites the same evidence messages. For closed (resolved/dismissed) findings
        it only counts as new if it cites a message posted after the closure AND describes a
        different issue; otherwise a resolved issue is never silently reopened.
        """
        grounded = set(grounded_ids)
        new_tokens = _title_tokens(title)
        for f in findings:
            if not f.mismatch_detected:
                continue
            evidence = set(f.supporting_message_ids or [])
            if not evidence and f.triggered_by_message_id:
                evidence = {str(f.triggered_by_message_id)}
            overlap = bool(evidence & grounded)
            similar_title = _jaccard(new_tokens, _title_tokens(f.title)) >= 0.5
            if not grounded:
                if f.category == category and similar_title:
                    return f
                continue
            if f.status not in _CLOSED_STATUSES:
                # Any shared evidence message means this is the same underlying issue, even if the
                # AI labeled it with a different category/title this time (e.g. "missing reminder
                # details" vs. "unclear reference" for the same vague message).
                if overlap:
                    return f
                if f.category == category and similar_title:
                    return f
                continue
            if not overlap:
                continue
            closed_at = _closed_at(f)
            has_newer = any(
                message_times.get(mid) is not None and _aware(message_times[mid]) > closed_at
                for mid in grounded
            )
            if not has_newer:
                return f
            if f.category == category and similar_title:
                return f
        return None


    async def evaluate_active_findings(
        self,
        conversation_id: uuid.UUID,
    ) -> Optional[AlignmentFindingResponse]:
        """
        Evaluate whether recent messages clarify or resolve an existing active finding.
        Casual acknowledgments ('ok', 'fine') leave findings in 'clarifying'.
        Concrete resolution evidence transitions them to 'awaiting_confirmation'.
        """
        if not settings.AI_ANALYSIS_ENABLED or not settings.is_provider_configured("nvidia"):
            return None

        active_findings = await self.ai_repo.get_active_unresolved_findings(conversation_id)
        if not active_findings:
            return None

        latest_active = active_findings[0]
        messages = await self.message_repo.get_recent_messages(
            conversation_id=conversation_id,
            limit=settings.MAX_CONVERSATION_CONTEXT_MESSAGES,
        )
        if not messages:
            return None

        context = [
            {
                "id": str(m.id),
                "sender_username": m.sender.username if m.sender else "User",
                "content": m.content,
            }
            for m in messages
        ]

        finding_info = {
            "title": latest_active.title,
            "category": latest_active.category,
            "explanation": latest_active.explanation,
            "clarification_question": latest_active.clarification_question,
        }

        try:
            eval_result = await ai_router.evaluate_resolution(
                conversation_context=context,
                finding_info=finding_info,
            )
            if not eval_result:
                return None

            if eval_result.has_resolution_evidence:
                target_status = eval_result.status_update
                # Resolution requires participant confirmation; the AI can only propose it.
                target_status = "awaiting_confirmation"

                updated = await self.ai_repo.update_finding_status(
                    finding=latest_active,
                    new_status=target_status,
                    reason="Substantive resolution evidence provided in chat",
                    evidence=eval_result.evidence_summary,
                )
                return AlignmentFindingResponse.model_validate(updated)

            # If no concrete evidence, but discussion has started since detection, transition to 'clarifying'
            if latest_active.status == "detected":
                updated = await self.ai_repo.update_finding_status(
                    finding=latest_active,
                    new_status="clarifying",
                    reason="Participants actively discussing or acknowledging issue",
                )
                return AlignmentFindingResponse.model_validate(updated)

            return None
        except Exception as exc:
            logger.error(f"Error evaluating active finding resolution: {exc}")
            return None

    async def trigger_alignment_analysis(
        self,
        conversation_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> Optional[AlignmentFindingResponse]:
        """
        Manually trigger alignment analysis (Check Alignment), bypassing the cooldown but not
        deduplication: resolved/dismissed issues are not recreated and concurrent calls are serialized.
        """
        is_member = await self.conv_repo.is_member(conversation_id, current_user_id)
        if not is_member:
            raise ForbiddenError("You are not a member of this conversation.")
        return await self._detect_and_persist(conversation_id)

    async def request_clarification(
        self,
        conversation_id: uuid.UUID,
        finding_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ):
        """
        Receiver-initiated clarification: posts a structured request message into the same
        conversation, linked to the finding and the original message. Idempotent per finding.
        Returns (finding, message, created).
        """
        from app.core.errors import BadRequestError
        from app.schemas.message import MessageCreate
        from app.services.conversation_service import ConversationService

        if not await self.conv_repo.is_member(conversation_id, current_user_id):
            raise ForbiddenError("You are not a member of this conversation.")

        finding = await self.ai_repo.get_finding_by_id(finding_id)
        if not finding or finding.conversation_id != conversation_id:
            raise NotFoundError("Alignment finding not found in this conversation.")
        if finding.status in _CLOSED_STATUSES:
            raise BadRequestError("This alignment finding is already closed.")

        original_id = None
        for mid in (finding.supporting_message_ids or []):
            original_id = mid
            break
        if original_id is None and finding.triggered_by_message_id:
            original_id = str(finding.triggered_by_message_id)
        original = None
        if original_id:
            original = await self.message_repo.get_by_id(uuid.UUID(str(original_id)))
            if original and original.conversation_id != conversation_id:
                original = None
        if original and original.sender_id == current_user_id:
            raise BadRequestError("You wrote this message; the other participants can request clarification.")

        user = await self.user_repo.get_by_id(current_user_id)
        username = user.username if user else "User"
        question = finding.clarification_question or "Could you clarify this message?"
        snippet = (original.content[:200] if original else "")
        content = f'@{username} asks for clarification on "{snippet}": {question}' if snippet else f"@{username} asks for clarification: {question}"

        conv_service = ConversationService(self.session)
        message = await conv_service.save_message(
            conversation_id=conversation_id,
            sender_id=current_user_id,
            message_in=MessageCreate(
                content=content[:5000],
                message_type="ai_alignment",
                msg_metadata={
                    "kind": "clarification_request",
                    "finding_id": str(finding.id),
                    "original_message_id": str(original_id) if original_id else None,
                    "question": question,
                },
                client_id=f"clarify:{finding.id}",
            ),
        )

        created = finding.clarification_request_message_id is None
        if created:
            finding.clarification_request_message_id = message.id
            finding.clarification_requested_by_id = current_user_id
            finding.clarification_requested_at = utc_now()
            if finding.status == "detected":
                await self.ai_repo.update_finding_status(
                    finding=finding,
                    new_status="clarifying",
                    reason=f"Clarification requested by @{username}",
                    user_id=current_user_id,
                )
            else:
                await self.session.flush()
        return AlignmentFindingResponse.model_validate(finding), message, created

    async def confirm_alignment_finding(
        self,
        conversation_id: uuid.UUID,
        finding_id: uuid.UUID,
        current_user_id: uuid.UUID,
        comment: Optional[str] = None,
    ) -> AlignmentFindingResponse:
        """Record participant confirmation for an alignment finding."""
        is_member = await self.conv_repo.is_member(conversation_id, current_user_id)
        if not is_member:
            raise ForbiddenError("You are not a member of this conversation.")

        finding = await self.ai_repo.get_finding_by_id(finding_id)
        if not finding or finding.conversation_id != conversation_id:
            raise NotFoundError("Alignment finding not found in this conversation.")

        user = await self.user_repo.get_by_id(current_user_id)
        username = user.username if user else "User"

        await self.ai_repo.add_finding_confirmation(
            finding=finding,
            user_id=current_user_id,
            username=username,
            comment=comment,
        )

        # In 1-on-1 or multi-party chats:
        # Check confirmations. If finding was awaiting_confirmation or already has >= 2 confirmations (or confirmed by participant):
        # We transition to resolved.
        confirmations = list(finding.confirmations or [])
        members = await self.conv_repo.get_members(conversation_id)
        total_members = len(members)

        # If all members confirmed, or at least 2 distinct confirmations, or 1-on-1 where the non-creator confirmed
        if len(confirmations) >= max(2, total_members) or finding.status == "awaiting_confirmation":
            await self.ai_repo.update_finding_status(
                finding=finding,
                new_status="resolved",
                reason=f"Mutual confirmation completed ({len(confirmations)} confirmations recorded)",
                user_id=current_user_id,
            )
        elif finding.status in ["detected", "clarifying"]:
            await self.ai_repo.update_finding_status(
                finding=finding,
                new_status="awaiting_confirmation",
                reason=f"Confirmation recorded from @{username}; awaiting other participants",
                user_id=current_user_id,
            )

        return AlignmentFindingResponse.model_validate(finding)

    async def resolve_alignment_finding(
        self,
        conversation_id: uuid.UUID,
        finding_id: uuid.UUID,
        current_user_id: uuid.UUID,
        evidence: Optional[str] = None,
    ) -> AlignmentFindingResponse:
        """Manually mark an alignment finding as resolved by a participant."""
        is_member = await self.conv_repo.is_member(conversation_id, current_user_id)
        if not is_member:
            raise ForbiddenError("You are not a member of this conversation.")

        finding = await self.ai_repo.get_finding_by_id(finding_id)
        if not finding or finding.conversation_id != conversation_id:
            raise NotFoundError("Alignment finding not found in this conversation.")

        user = await self.user_repo.get_by_id(current_user_id)
        username = user.username if user else "User"

        updated = await self.ai_repo.update_finding_status(
            finding=finding,
            new_status="resolved",
            reason=f"Resolved by @{username}",
            user_id=current_user_id,
            evidence=evidence or "Participant marked issue as resolved",
        )
        return AlignmentFindingResponse.model_validate(updated)

    async def dismiss_alignment_finding(
        self,
        conversation_id: uuid.UUID,
        finding_id: uuid.UUID,
        current_user_id: uuid.UUID,
        reason: Optional[str] = None,
    ) -> AlignmentFindingResponse:
        """Dismiss an alignment finding."""
        is_member = await self.conv_repo.is_member(conversation_id, current_user_id)
        if not is_member:
            raise ForbiddenError("You are not a member of this conversation.")

        finding = await self.ai_repo.get_finding_by_id(finding_id)
        if not finding or finding.conversation_id != conversation_id:
            raise NotFoundError("Alignment finding not found in this conversation.")

        dismissed = await self.ai_repo.dismiss_finding(
            finding=finding,
            user_id=current_user_id,
            reason=reason,
        )
        return AlignmentFindingResponse.model_validate(dismissed)

    async def get_conversation_findings(
        self, conversation_id: uuid.UUID, current_user_id: uuid.UUID, limit: int = 50
    ) -> List[AlignmentFindingResponse]:
        is_member = await self.conv_repo.is_member(conversation_id, current_user_id)
        if not is_member:
            raise ForbiddenError("You are not a member of this conversation.")

        findings = await self.ai_repo.get_findings_by_conversation(conversation_id, limit=limit)
        return [AlignmentFindingResponse.model_validate(f) for f in findings]
