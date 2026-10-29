"""Durable per-message analysis queue: enqueue, atomic claim, bounded retry, crash recovery."""

import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.logging import logger
from app.db.base import utc_now
from app.models.analysis_job import MessageAnalysisJob
from app.models.message import Message
from app.schemas.ai import AlignmentFindingResponse
from app.services.alignment_service import AlignmentService

MAX_ATTEMPTS = 3
LEASE_SECONDS = 120
BACKOFF_SECONDS = (5, 20)  # delay before retry 2 and retry 3
REVIVE_MAX_AGE = timedelta(hours=24)  # provider outages longer than the backoff window get one more attempt

# Exact-match pure acknowledgements. Never a length rule: "Submit it tomorrow" must still be analyzed.
_CASUAL = {
    "hi", "hello", "hey", "ok", "okay", "k", "yes", "no", "yep", "yeah", "nope", "thanks", "thank you",
    "thx", "ty", "lol", "haha", "sounds good", "cool", "sure", "got it", "great", "nice", "bye",
    "good morning", "good night", "np", "no problem", "fine",
}


def is_casual_acknowledgement(text: str) -> bool:
    normalized = re.sub(r"[^a-z0-9 ]+", "", (text or "").lower()).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized in _CASUAL


class AnalysisQueue:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def enqueue(self, message_id: uuid.UUID, conversation_id: uuid.UUID) -> bool:
        """Idempotent: one job per message. Returns True if newly queued."""
        existing = await self.session.execute(
            select(MessageAnalysisJob.id).where(MessageAnalysisJob.message_id == message_id)
        )
        if existing.scalar_one_or_none():
            return False
        try:
            # Savepoint: a concurrent enqueue for the same message loses on the unique constraint without
            # poisoning the caller's transaction.
            async with self.session.begin_nested():
                self.session.add(MessageAnalysisJob(message_id=message_id, conversation_id=conversation_id))
        except IntegrityError:
            return False
        return True

    async def recover_stale(self) -> int:
        """Return jobs whose worker died mid-processing (expired lease) to pending."""
        cutoff = utc_now() - timedelta(seconds=LEASE_SECONDS)
        res = await self.session.execute(
            update(MessageAnalysisJob)
            .where(MessageAnalysisJob.status == "processing", MessageAnalysisJob.claimed_at < cutoff)
            .values(status="pending", claimed_at=None)
        )
        await self.session.commit()
        return res.rowcount or 0

    async def revive_failed(self, conversation_id: Optional[uuid.UUID] = None) -> int:
        """
        Give recently failed provider jobs exactly one more attempt (called on startup and when a new message
        arrives, never from the drain loop). Prevents a short outage from permanently dropping AI coverage.
        """
        stmt = (
            update(MessageAnalysisJob)
            .where(
                MessageAnalysisJob.status == "failed",
                MessageAnalysisJob.outcome == "provider_failed",
                MessageAnalysisJob.created_at >= utc_now() - REVIVE_MAX_AGE,
            )
            .values(status="pending", outcome=None, attempts=MAX_ATTEMPTS - 1, next_attempt_at=utc_now(), claimed_at=None)
            .execution_options(synchronize_session=False)
        )
        if conversation_id is not None:
            stmt = stmt.where(MessageAnalysisJob.conversation_id == conversation_id)
        res = await self.session.execute(stmt)
        await self.session.commit()
        return res.rowcount or 0

    async def pending_conversation_ids(self) -> List[uuid.UUID]:
        res = await self.session.execute(
            select(MessageAnalysisJob.conversation_id).where(MessageAnalysisJob.status == "pending").distinct()
        )
        return list(res.scalars().all())

    async def claim(self, conversation_id: uuid.UUID) -> List[MessageAnalysisJob]:
        """Atomically claim due pending jobs; the conditional UPDATE lets exactly one worker win each job."""
        now = utc_now()
        res = await self.session.execute(
            select(MessageAnalysisJob)
            .where(
                MessageAnalysisJob.conversation_id == conversation_id,
                MessageAnalysisJob.status == "pending",
                MessageAnalysisJob.next_attempt_at <= now,
            )
            .order_by(MessageAnalysisJob.created_at)
        )
        claimed: List[MessageAnalysisJob] = []
        for job in res.scalars().all():
            upd = await self.session.execute(
                update(MessageAnalysisJob)
                .where(MessageAnalysisJob.id == job.id, MessageAnalysisJob.status == "pending")
                .values(status="processing", claimed_at=now, attempts=MessageAnalysisJob.attempts + 1)
            )
            if upd.rowcount == 1:
                claimed.append(job)
        await self.session.commit()
        for job in claimed:
            await self.session.refresh(job)
        return claimed

    async def _finish(self, jobs: List[MessageAnalysisJob], status: str, outcome: str, error: Optional[str] = None) -> None:
        for job in jobs:
            job.status = status
            job.outcome = outcome
            job.last_error = error
            job.claimed_at = None
        await self.session.commit()

    async def complete(self, jobs, outcome: str) -> None:
        await self._finish(jobs, "done", outcome)

    async def skip(self, jobs, outcome: str) -> None:
        await self._finish(jobs, "skipped", outcome)

    async def fail(self, jobs: List[MessageAnalysisJob], error: str) -> Optional[float]:
        """Bounded retry with backoff. Returns the delay (s) until the next retry, or None if exhausted."""
        delay: Optional[float] = None
        for job in jobs:
            job.last_error = error[:300]
            job.claimed_at = None
            if job.attempts >= MAX_ATTEMPTS:
                job.status, job.outcome = "failed", "provider_failed"
            else:
                d = BACKOFF_SECONDS[min(job.attempts - 1, len(BACKOFF_SECONDS) - 1)]
                job.status = "pending"
                job.next_attempt_at = utc_now() + timedelta(seconds=d)
                delay = d if delay is None else min(delay, d)
        await self.session.commit()
        return delay


class FindingBatch(list):
    """
    List of findings that behaves both as a list and as the primary finding
    for backwards compatibility.
    """

    def __getattr__(self, name: str):
        if self:
            return getattr(self[0], name)
        raise AttributeError(name)

    def model_dump(self, *args, **kwargs):
        if self:
            return self[0].model_dump(*args, **kwargs)
        return {}


async def process_conversation_jobs(
    session: AsyncSession, conversation_id: uuid.UUID
) -> Tuple[Optional[Any], Optional[float], bool]:
    """
    Claim and analyze all due jobs for a conversation as one batch.
    Guarantees per-message coverage:
    - Casual acknowledgements are completed with 'skipped_casual' without AI calls.
    - All non-casual eligible messages are evaluated.
    - Zero, one, or multiple distinct findings can be detected and persisted.
    - If the AI omits any eligible message from coverage, a bounded targeted follow-up
      analyzes the uncovered message(s).
    - If a batch partially fails, successfully persisted findings are preserved and only
      the remaining work is scheduled for retry.
    Returns (findings_batch_or_none, retry_delay_seconds, processed_anything).
    """
    queue = AnalysisQueue(session)
    jobs = await queue.claim(conversation_id)
    if not jobs:
        return None, None, False

    job_by_msg_id = {j.message_id: j for j in jobs}
    msg_rows = await session.execute(select(Message).where(Message.id.in_(list(job_by_msg_id.keys()))))
    messages = sorted(msg_rows.scalars().all(), key=lambda m: m.created_at)

    # Filter casual messages: complete their individual jobs as skipped_casual
    casual_jobs = []
    eligible_messages = []
    eligible_jobs = []

    for m in messages:
        if m.message_type == "text" and is_casual_acknowledgement(m.content):
            j = job_by_msg_id.get(m.id)
            if j:
                casual_jobs.append(j)
        else:
            eligible_messages.append(m)
            j = job_by_msg_id.get(m.id)
            if j:
                eligible_jobs.append(j)

    if casual_jobs:
        await queue.complete(casual_jobs, "skipped_casual")

    if not eligible_messages:
        # All claimed jobs were casual acknowledgements
        return None, None, True

    if not settings.AI_ANALYSIS_ENABLED or not (
        settings.is_provider_configured("nvidia") or settings.is_provider_configured("groq")
    ):
        await queue.skip(eligible_jobs, "ai_not_configured")
        return None, None, True

    service = AlignmentService(session)
    all_new_findings: List[AlignmentFindingResponse] = []
    covered_job_outcomes: Dict[uuid.UUID, str] = {}

    try:
        # Pass 1: primary batch analysis for all eligible messages
        findings, analyzed_ids, outcomes_by_mid = await service._detect_and_persist_batch(
            conversation_id, target_messages=eligible_messages
        )
    except Exception as exc:
        await session.rollback()
        logger.error(f"Analysis job failed conv={conversation_id}: {type(exc).__name__}")
        for j in eligible_jobs:
            await session.refresh(j)
        return None, await queue.fail(eligible_jobs, type(exc).__name__), True

    if service.last_ai_failed:
        for j in eligible_jobs:
            await session.refresh(j)
        return None, await queue.fail(eligible_jobs, "provider_unavailable"), True

    all_new_findings.extend(findings)

    # Check which eligible messages were covered
    uncovered_messages: List[Message] = []
    for m in eligible_messages:
        mid_str = str(m.id)
        if mid_str in outcomes_by_mid:
            covered_job_outcomes[m.id] = outcomes_by_mid[mid_str]
        elif mid_str in analyzed_ids:
            covered_job_outcomes[m.id] = "no_issue"
        else:
            uncovered_messages.append(m)

    # If some messages were omitted by AI, run a bounded targeted follow-up analysis for them
    if uncovered_messages:
        logger.info(
            f"AI omitted {len(uncovered_messages)} messages from coverage in conv={conversation_id}. Running targeted follow-up."
        )
        try:
            fu_findings, fu_analyzed_ids, fu_outcomes = await service._detect_and_persist_batch(
                conversation_id, target_messages=uncovered_messages
            )
            if not service.last_ai_failed:
                all_new_findings.extend(fu_findings)
                for m in uncovered_messages:
                    mid_str = str(m.id)
                    if mid_str in fu_outcomes:
                        covered_job_outcomes[m.id] = fu_outcomes[mid_str]
                    elif mid_str in fu_analyzed_ids:
                        covered_job_outcomes[m.id] = "no_issue"
        except Exception as exc:
            logger.warning(f"Targeted follow-up failed in conv={conversation_id}: {exc}")

    # Complete covered jobs with their specific outcomes
    for m_id, outcome in covered_job_outcomes.items():
        j = job_by_msg_id.get(m_id)
        if j:
            j.status = "done"
            j.outcome = outcome
            j.last_error = None
            j.claimed_at = None

    # Any still uncovered jobs remain pending with retry
    uncovered_jobs = [j for j in eligible_jobs if j.message_id not in covered_job_outcomes]
    retry_delay: Optional[float] = None
    if uncovered_jobs:
        logger.warning(f"{len(uncovered_jobs)} jobs remained uncovered after follow-up; scheduling bounded retry.")
        retry_delay = await queue.fail(uncovered_jobs, "uncovered_omitted")

    await session.commit()

    result_batch = FindingBatch(all_new_findings) if all_new_findings else None
    return result_batch, retry_delay, True

