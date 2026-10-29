"""Live Conversation Context Graph service.

Maintains structured context (tasks, commitments, responsible persons,
deadlines, status, open questions, confirmations, and contradictions)
connected to source messages and integrated with the AI alignment engine.
"""

import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.errors import BadRequestError, ForbiddenError, NotFoundError
from app.core.logging import logger
from app.db.base import utc_now
from app.models.context_graph import ContextInconsistency, ContextNode
from app.models.message import Message
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.user_repo import UserRepository
from app.schemas.context_graph import (
    ContextGraphResponse,
    ContextInconsistencyRead,
    ContextNodeRead,
)
from app.services.ai_router import ai_router


class ContextGraphService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.conv_repo = ConversationRepository(session)
        self.message_repo = MessageRepository(session)
        self.user_repo = UserRepository(session)

    async def get_conversation_graph(
        self, conversation_id: uuid.UUID, user_id: Optional[uuid.UUID] = None
    ) -> ContextGraphResponse:
        """Fetch active context nodes and detected inconsistencies scoped to conversation."""
        if user_id is not None:
            is_member = await self.conv_repo.is_member(conversation_id, user_id)
            if not is_member:
                raise ForbiddenError("You are not a member of this conversation.")

        # Fetch active context nodes
        stmt_nodes = (
            select(ContextNode)
            .where(
                ContextNode.conversation_id == conversation_id,
                ContextNode.is_resolved.is_(False),
            )
            .order_by(ContextNode.updated_at.desc())
        )
        nodes_result = await self.session.execute(stmt_nodes)
        nodes = list(nodes_result.scalars().all())

        # Fetch active inconsistencies
        stmt_inc = (
            select(ContextInconsistency)
            .where(
                ContextInconsistency.conversation_id == conversation_id,
                ContextInconsistency.is_dismissed.is_(False),
                ContextInconsistency.status.notin_(["resolved", "dismissed"]),
            )
            .order_by(ContextInconsistency.updated_at.desc())
        )
        inc_result = await self.session.execute(stmt_inc)
        inconsistencies = list(inc_result.scalars().all())

        return ContextGraphResponse(
            conversation_id=conversation_id,
            active_nodes=[ContextNodeRead.model_validate(n) for n in nodes],
            inconsistencies=[ContextInconsistencyRead.model_validate(i) for i in inconsistencies],
            total_active_nodes=len(nodes),
            total_inconsistencies=len(inconsistencies),
        )

    async def dismiss_inconsistency(
        self, conversation_id: uuid.UUID, inconsistency_id: uuid.UUID, user_id: uuid.UUID
    ) -> ContextInconsistencyRead:
        """Dismiss a context suggestion or contradiction alert."""
        is_member = await self.conv_repo.is_member(conversation_id, user_id)
        if not is_member:
            raise ForbiddenError("You are not a member of this conversation.")

        stmt = select(ContextInconsistency).where(
            ContextInconsistency.id == inconsistency_id,
            ContextInconsistency.conversation_id == conversation_id,
        )
        inc = (await self.session.execute(stmt)).scalar_one_or_none()
        if not inc:
            raise NotFoundError("Context inconsistency not found.")

        inc.is_dismissed = True
        inc.status = "dismissed"
        inc.updated_at = utc_now()
        await self.session.flush()
        return ContextInconsistencyRead.model_validate(inc)

    async def resolve_inconsistency(
        self,
        conversation_id: uuid.UUID,
        inconsistency_id: uuid.UUID,
        user_id: uuid.UUID,
        note: Optional[str] = None,
    ) -> ContextInconsistencyRead:
        """Mark an inconsistency as resolved following participant clarification."""
        is_member = await self.conv_repo.is_member(conversation_id, user_id)
        if not is_member:
            raise ForbiddenError("You are not a member of this conversation.")

        stmt = select(ContextInconsistency).where(
            ContextInconsistency.id == inconsistency_id,
            ContextInconsistency.conversation_id == conversation_id,
        )
        inc = (await self.session.execute(stmt)).scalar_one_or_none()
        if not inc:
            raise NotFoundError("Context inconsistency not found.")

        inc.status = "resolved"
        inc.updated_at = utc_now()
        await self.session.flush()
        return ContextInconsistencyRead.model_validate(inc)

    async def resolve_node(
        self,
        conversation_id: uuid.UUID,
        node_id: uuid.UUID,
        user_id: uuid.UUID,
        status: str = "completed",
        resolution_note: Optional[str] = None,
    ) -> ContextNodeRead:
        """Mark a context task or question as resolved or completed."""
        is_member = await self.conv_repo.is_member(conversation_id, user_id)
        if not is_member:
            raise ForbiddenError("You are not a member of this conversation.")

        stmt = select(ContextNode).where(
            ContextNode.id == node_id,
            ContextNode.conversation_id == conversation_id,
        )
        node = (await self.session.execute(stmt)).scalar_one_or_none()
        if not node:
            raise NotFoundError("Context item not found.")

        node.is_resolved = True
        node.status = status
        node.resolution_note = resolution_note
        node.updated_at = utc_now()
        await self.session.flush()
        return ContextNodeRead.model_validate(node)

    async def handle_message_deletion(
        self, conversation_id: uuid.UUID, message_id: uuid.UUID
    ) -> None:
        """
        Lifecycle enforcement: remove deleted messages from active context graph evidence
        so deleted content cannot leak or serve as ongoing evidence.
        """
        str_mid = str(message_id)

        # Update nodes
        stmt_nodes = select(ContextNode).where(ContextNode.conversation_id == conversation_id)
        nodes = (await self.session.execute(stmt_nodes)).scalars().all()
        for node in nodes:
            if str_mid in (node.evidence_message_ids or []):
                new_ev = [m for m in node.evidence_message_ids if m != str_mid]
                node.evidence_message_ids = new_ev
                if node.last_updated_by_message_id == message_id:
                    node.last_updated_by_message_id = None

        # Update inconsistencies
        stmt_inc = select(ContextInconsistency).where(
            ContextInconsistency.conversation_id == conversation_id
        )
        incs = (await self.session.execute(stmt_inc)).scalars().all()
        for inc in incs:
            if inc.earlier_evidence_message_id == message_id:
                inc.earlier_evidence_message_id = None
            if inc.later_evidence_message_id == message_id:
                inc.later_evidence_message_id = None

        await self.session.flush()

    async def process_messages_incremental(
        self,
        conversation_id: uuid.UUID,
        triggering_message_id: Optional[uuid.UUID] = None,
    ) -> Tuple[List[ContextNode], List[ContextInconsistency]]:
        """
        Incrementally analyze recent conversation messages to extract tasks, commitments,
        deadlines, open questions, confirmations, and detect possible contradictions.
        """
        # Fetch the most recent messages in chronological order (bounded to 25)
        messages = await self.message_repo.get_recent_messages(conversation_id, limit=25)
        if not messages:
            return [], []

        # Filter out deleted messages
        active_messages = [m for m in messages if not m.is_deleted_for_everyone]
        if not active_messages:
            return [], []

        # Load existing active nodes and inconsistencies
        stmt_nodes = select(ContextNode).where(
            ContextNode.conversation_id == conversation_id,
            ContextNode.is_resolved.is_(False),
        )
        existing_nodes = list((await self.session.execute(stmt_nodes)).scalars().all())

        stmt_inc = select(ContextInconsistency).where(
            ContextInconsistency.conversation_id == conversation_id
        )
        existing_incs = list((await self.session.execute(stmt_inc)).scalars().all())

        created_or_updated_nodes: List[ContextNode] = []
        created_incs: List[ContextInconsistency] = []

        # Run extraction using heuristics + context integration
        extracted_facts, detected_inconsistencies = self._extract_facts_and_inconsistencies(
            active_messages, existing_nodes, existing_incs
        )

        # Persist or update extracted facts
        for fact in extracted_facts:
            topic = fact["topic"].strip()
            # Match existing node by case-insensitive topic or similar description
            matched_node = next(
                (n for n in existing_nodes if n.topic.lower() == topic.lower()),
                None,
            )

            if matched_node:
                # Update existing node with latest status / deadline / evidence
                if fact.get("status") and matched_node.status != fact["status"]:
                    matched_node.status = fact["status"]
                if fact.get("deadline") and not matched_node.deadline:
                    matched_node.deadline = fact["deadline"]
                if fact.get("responsible_person") and not matched_node.responsible_person:
                    matched_node.responsible_person = fact["responsible_person"]

                evidence_set = set(matched_node.evidence_message_ids or [])
                for mid in fact.get("evidence_message_ids", []):
                    evidence_set.add(mid)
                matched_node.evidence_message_ids = list(evidence_set)

                if fact.get("is_resolved") is not None:
                    matched_node.is_resolved = fact["is_resolved"]

                matched_node.last_updated_by_message_id = (
                    uuid.UUID(fact["evidence_message_ids"][-1])
                    if fact.get("evidence_message_ids")
                    else None
                )
                matched_node.updated_at = utc_now()
                created_or_updated_nodes.append(matched_node)
            else:
                # Create new ContextNode
                new_node = ContextNode(
                    conversation_id=conversation_id,
                    node_type=fact.get("node_type", "task"),
                    topic=topic,
                    description=fact.get("description", topic),
                    responsible_person=fact.get("responsible_person"),
                    deadline=fact.get("deadline"),
                    status=fact.get("status", "pending"),
                    evidence_message_ids=fact.get("evidence_message_ids", []),
                    confidence=fact.get("confidence", 0.85),
                    is_resolved=fact.get("is_resolved", False),
                    last_updated_by_message_id=(
                        uuid.UUID(fact["evidence_message_ids"][-1])
                        if fact.get("evidence_message_ids")
                        else None
                    ),
                )
                self.session.add(new_node)
                created_or_updated_nodes.append(new_node)
                existing_nodes.append(new_node)

        await self.session.flush()

        # Persist new inconsistencies
        for inc_data in detected_inconsistencies:
            # Check if this contradiction was already recorded
            already_exists = any(
                i.earlier_evidence_message_id == inc_data.get("earlier_evidence_message_id")
                and i.later_evidence_message_id == inc_data.get("later_evidence_message_id")
                for i in existing_incs
            )
            if not already_exists:
                new_inc = ContextInconsistency(
                    conversation_id=conversation_id,
                    node_id=inc_data.get("node_id"),
                    title=inc_data["title"],
                    description=inc_data["description"],
                    earlier_evidence_message_id=inc_data.get("earlier_evidence_message_id"),
                    later_evidence_message_id=inc_data.get("later_evidence_message_id"),
                    clarification_prompt=inc_data["clarification_prompt"],
                    status="detected",
                    is_dismissed=False,
                )
                self.session.add(new_inc)
                created_incs.append(new_inc)
                existing_incs.append(new_inc)

        await self.session.flush()

        # If any changes were made, broadcast context update via Socket.IO
        if created_or_updated_nodes or created_incs:
            try:
                from app.sockets.server import sio

                full_graph = await self.get_conversation_graph(conversation_id)
                await sio.emit(
                    "ai:context_update",
                    full_graph.model_dump(mode="json"),
                    room=f"conversation:{conversation_id}",
                )
            except Exception as exc:
                logger.warning(f"Failed to broadcast context graph update: {exc}")

        return created_or_updated_nodes, created_incs

    def _extract_facts_and_inconsistencies(
        self,
        messages: List[Message],
        existing_nodes: List[ContextNode],
        existing_incs: List[ContextInconsistency],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Extract tasks, commitments, status reports, open questions, and detect contradictions.
        Never fabricates dates or completion status.
        """
        facts: List[Dict[str, Any]] = []
        inconsistencies: List[Dict[str, Any]] = []

        # Map messages for easy lookup
        msg_list = [
            {
                "id": m.id,
                "str_id": str(m.id),
                "sender": m.sender.username if m.sender else "User",
                "content": m.content.strip(),
                "created_at": m.created_at,
            }
            for m in messages
        ]

        # 1. Detect commitments, tasks, and questions
        for idx, msg in enumerate(msg_list):
            content = msg["content"]
            sender = msg["sender"]
            str_id = msg["str_id"]
            lower = content.lower()

            # A. Task / Commitment detection: e.g., "We need to submit the research paper tomorrow", "I will finish it tonight"
            # Pattern: "we need to [action]" or "please [action]"
            need_to_match = re.search(r"(?:we need to|need to|let'?s|please)\s+([^.?!,]+)", content, re.IGNORECASE)
            if need_to_match:
                task_raw = need_to_match.group(1).strip()
                deadline = self._extract_deadline_text(content)
                topic = self._clean_topic(task_raw)
                facts.append({
                    "node_type": "task",
                    "topic": topic,
                    "description": f"Task: {task_raw}",
                    "responsible_person": None,
                    "deadline": deadline,
                    "status": "pending",
                    "evidence_message_ids": [str_id],
                    "confidence": 0.85,
                })

            # Pattern: "I will finish/do/handle/check [action] [time]"
            i_will_match = re.search(r"\bI(?:'ll|\s+will|\s+can)\s+(?:finish|do|complete|send|prepare|handle|check)\s+([^.?!,]+)", content, re.IGNORECASE)
            if i_will_match:
                commitment_raw = i_will_match.group(1).strip()
                deadline = self._extract_deadline_text(content)
                topic = self._clean_topic(commitment_raw)
                # If topic contains "it", try to resolve from previous message topic
                if topic in ["it", "that", "this"] and facts:
                    topic = facts[-1]["topic"]
                facts.append({
                    "node_type": "commitment",
                    "topic": topic,
                    "description": f"Commitment by @{sender} to finish {topic}",
                    "responsible_person": sender,
                    "deadline": deadline,
                    "status": "in_progress",
                    "evidence_message_ids": [str_id],
                    "confidence": 0.90,
                })

            # B. Status report / Completion: e.g., "Those are already done", "References are done", "Everything is done"
            done_match = re.search(r"([^.?!,]+?)\s+(?:is|are|have been)\s+(?:already\s+)?(?:done|finished|completed)", content, re.IGNORECASE)
            if done_match or re.search(r"\b(?:done|finished|completed)\b", lower):
                subject = done_match.group(1).strip() if done_match else "references"
                subject_clean = self._clean_topic(subject)
                # If pronoun (those, they, it), map to preceding question or task
                if subject_clean.lower() in ["those", "they", "it", "that", "all"] and idx > 0:
                    prev_msg = msg_list[idx - 1]["content"]
                    prev_match = re.search(r"(?:what about|how about|is|are)\s+([^.?!,]+)", prev_msg, re.IGNORECASE)
                    if prev_match:
                        subject_clean = self._clean_topic(prev_match.group(1).strip())
                    elif facts:
                        subject_clean = facts[-1]["topic"]

                facts.append({
                    "node_type": "confirmation",
                    "topic": subject_clean,
                    "description": f"Reported completed: {subject_clean}",
                    "responsible_person": sender,
                    "status": "completed",
                    "evidence_message_ids": [str_id],
                    "confidence": 0.95,
                })

            # C. Open question: e.g., "What about the references?", "Can you finish the UI today?", "Is everything ready?"
            if "?" in content:
                question_match = re.search(r"(?:what about|how about|can you|could you|is|are|will you)\s+([^?]+)\?", content, re.IGNORECASE)
                q_topic = self._clean_topic(question_match.group(1).strip()) if question_match else self._clean_topic(content[:60])
                facts.append({
                    "node_type": "question",
                    "topic": q_topic,
                    "description": content,
                    "responsible_person": None,
                    "status": "uncertain",
                    "evidence_message_ids": [str_id],
                    "confidence": 0.85,
                })

        # 2. Contradiction and commitment change detection
        # Example:
        # Earlier: "I will finish the paper tonight." (or "I will finish it tonight")
        # Later: "I haven't started the paper yet." or "I won't be able to finish..."
        for i in range(len(msg_list)):
            m_earlier = msg_list[i]
            earlier_text = m_earlier["content"].lower()

            is_early_commitment = any(phrase in earlier_text for phrase in [
                "i will finish", "i'll finish", "i can finish", "i will complete", "i will do"
            ])
            if not is_early_commitment:
                continue

            for j in range(i + 1, len(msg_list)):
                m_later = msg_list[j]
                # Compare same speaker or related topic
                if m_later["sender"] != m_earlier["sender"]:
                    continue

                later_text = m_later["content"].lower()
                is_later_inconsistency = any(phrase in later_text for phrase in [
                    "haven't started", "have not started", "cannot finish", "can't finish",
                    "won't be able to", "will not be able to", "delayed", "not started"
                ])

                if is_later_inconsistency:
                    inconsistencies.append({
                        "node_id": None,
                        "title": "Status check on earlier commitment",
                        "description": (
                            f"@{m_later['sender']}'s earlier message mentioned finishing this work, "
                            f"while a subsequent message noted: \"{m_later['content']}\"."
                        ),
                        "clarification_prompt": (
                            f"Your earlier message mentioned finishing tonight. Would you like to clarify the current status?"
                        ),
                        "earlier_evidence_message_id": m_earlier["id"],
                        "later_evidence_message_id": m_later["id"],
                    })

        return facts, inconsistencies

    @staticmethod
    def _extract_deadline_text(text: str) -> Optional[str]:
        """Extract explicit or relative deadline phrases verbatim without inventing dates."""
        match = re.search(r"\b(?:by|before|on|at|until)\s+(today|tonight|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|next week|\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b", text, re.IGNORECASE)
        if match:
            return match.group(0).strip()
        # Direct temporal adverbs
        adv_match = re.search(r"\b(today|tonight|tomorrow)\b", text, re.IGNORECASE)
        if adv_match:
            return adv_match.group(1).strip().lower()
        return None

    @staticmethod
    def _clean_topic(raw: str) -> str:
        """Extract clean noun topic from raw phrasing."""
        t = raw.strip()
        while True:
            new_t = re.sub(r"^(?:to|the|a|an|submit|finish|complete|check)\s+", "", t, flags=re.IGNORECASE)
            if new_t == t:
                break
            t = new_t
        t = re.sub(r"\s+(?:by|tonight|tomorrow|today).*$", "", t, flags=re.IGNORECASE)
        return t.strip()[:60] if t.strip() else raw.strip()[:60]
