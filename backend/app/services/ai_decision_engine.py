"""AI Decision Engine orchestrating real-time debounced analysis, active finding resolution, and recommendations."""

import asyncio
import time
from typing import Dict, Optional
import uuid
from app.core.config import settings
from app.core.logging import logger
from app.db.session import AsyncSessionLocal
from app.services.alignment_service import AlignmentService
from app.services.analysis_queue import AnalysisQueue, process_conversation_jobs
from app.services.context_graph_service import ContextGraphService
from app.services.recommendation_service import RecommendationService

# In-memory debounce tasks per conversation
_debounce_tasks: Dict[uuid.UUID, asyncio.Task] = {}
_concurrency_semaphore = asyncio.Semaphore(5)
# Conversations whose debounced task has already started; such a task must not be cancelled mid-run.
_running: set = set()


class AIDecisionEngine:
    """Coordinates conversation analysis with debounce window, lifecycle evaluation, and context-aware recommendations."""

    DEBOUNCE_SECONDS = 2.0

    @classmethod
    async def handle_message_event(
        cls, conversation_id: uuid.UUID, message_id: uuid.UUID
    ) -> None:
        """
        Entry point called when a new message is saved.
        Cancels any existing pending debounce task for this conversation and starts a new one.
        """
        # The job row is the durable record; the debounce task only batches the work.
        try:
            async with AsyncSessionLocal() as session:
                await AnalysisQueue(session).enqueue(message_id, conversation_id)
                await session.commit()
        except Exception as exc:
            logger.error(f"Failed to enqueue analysis job: {type(exc).__name__}")

        existing_task = _debounce_tasks.get(conversation_id)
        if existing_task and not existing_task.done() and conversation_id not in _running:
            existing_task.cancel()

        task = asyncio.create_task(
            cls._debounced_execution(conversation_id, message_id)
        )
        _debounce_tasks[conversation_id] = task

    @classmethod
    async def _debounced_execution(
        cls, conversation_id: uuid.UUID, message_id: uuid.UUID
    ) -> None:
        try:
            await asyncio.sleep(cls.DEBOUNCE_SECONDS)
        except asyncio.CancelledError:
            # A newer message arrived during the debounce window
            return

        _running.add(conversation_id)
        try:
            async with AsyncSessionLocal() as session:
                await AnalysisQueue(session).revive_failed(conversation_id)
            async with _concurrency_semaphore:
                await cls.process_conversation(conversation_id, triggering_message_id=message_id)
        except Exception as exc:
            logger.error(f"Error in AIDecisionEngine for conversation={conversation_id}: {exc}")
        finally:
            _running.discard(conversation_id)

    @classmethod
    async def recover_pending(cls) -> None:
        """On startup: release expired leases and drain every conversation with pending jobs."""
        try:
            async with AsyncSessionLocal() as session:
                queue = AnalysisQueue(session)
                released = await queue.recover_stale()
                released += await queue.revive_failed()
                conv_ids = await queue.pending_conversation_ids()
            if released or conv_ids:
                logger.info(f"Recovering analysis jobs: released={released}, conversations={len(conv_ids)}")
            for conv_id in conv_ids:
                await cls.drain_conversation(conv_id)
        except Exception as exc:
            logger.error(f"Analysis job recovery failed: {type(exc).__name__}")

    @classmethod
    async def drain_conversation(cls, conversation_id: uuid.UUID) -> None:
        """Process due jobs (bounded passes), broadcast any new finding, schedule bounded retries."""
        from app.sockets.server import sio
        for _ in range(5):
            async with AsyncSessionLocal() as session:
                finding, retry_delay, processed = await process_conversation_jobs(session, conversation_id)
            if finding is not None:
                findings_to_broadcast = finding if isinstance(finding, list) else [finding]
                for f in findings_to_broadcast:
                    await sio.emit(
                        "ai:alignment",
                        {"finding": f.model_dump(mode="json")},
                        room=f"conversation:{conversation_id}",
                    )

            if retry_delay is not None:
                asyncio.create_task(cls._retry_later(conversation_id, retry_delay))
            if not processed:
                break

    @classmethod
    async def _retry_later(cls, conversation_id: uuid.UUID, delay: float) -> None:
        await asyncio.sleep(delay + 0.1)
        await cls.drain_conversation(conversation_id)

    @classmethod
    async def process_conversation(
        cls,
        conversation_id: uuid.UUID,
        triggering_message_id: Optional[uuid.UUID] = None,
    ) -> None:
        """
        Core pipeline:
        Runs alignment analysis and contextual recommendation detection concurrently
        with isolated database sessions so neither pipeline blocks normal messaging.
        """
        await asyncio.gather(
            cls._process_alignment(conversation_id, triggering_message_id),
            cls._process_recommendations(conversation_id, triggering_message_id),
            cls._process_context_graph(conversation_id, triggering_message_id),
            return_exceptions=True,
        )

    @classmethod
    async def _process_alignment(
        cls, conversation_id: uuid.UUID, triggering_message_id: Optional[uuid.UUID] = None
    ) -> None:
        from app.sockets.server import sio
        # Step 1: Active finding resolution check
        try:
            async with AsyncSessionLocal() as session:
                alignment_service = AlignmentService(session)
                updated_finding = await alignment_service.evaluate_active_findings(conversation_id)
                await session.commit()

            if updated_finding:
                logger.info(
                    f"Broadcasting updated alignment finding {updated_finding.id} status={updated_finding.status} to room conversation:{conversation_id}"
                )
                await sio.emit(
                    "ai:alignment_update",
                    {"finding": updated_finding.model_dump(mode="json")},
                    room=f"conversation:{conversation_id}",
                )
        except Exception as exc:
            logger.error(f"Failed active finding evaluation in decision engine: {exc}")

        # Step 2: durable per-message analysis (no debounce/cooldown can drop a message)
        try:
            await cls.drain_conversation(conversation_id)
        except Exception as exc:
            logger.error(f"Failed alignment job processing in decision engine: {type(exc).__name__}")

    @classmethod
    async def _process_recommendations(
        cls, conversation_id: uuid.UUID, triggering_message_id: Optional[uuid.UUID] = None
    ) -> None:
        from app.sockets.server import sio
        # Step 3: Recommendation intent check
        try:
            async with AsyncSessionLocal() as session:
                recommendation_service = RecommendationService(session)
                recommendations = await recommendation_service.evaluate_and_fetch_recommendations(
                    conversation_id=conversation_id,
                    triggering_message_id=triggering_message_id,
                )
                await session.commit()

            for rec in recommendations:
                logger.info(
                    f"Broadcasting recommendation {rec.id} to room conversation:{conversation_id}"
                )
                await sio.emit(
                    "ai:recommendation",
                    {"recommendation": rec.model_dump(mode="json")},
                    room=f"conversation:{conversation_id}",
                )
        except Exception as exc:
            logger.error(f"Failed recommendation evaluation in decision engine: {exc}")

    @classmethod
    async def _process_context_graph(
        cls, conversation_id: uuid.UUID, triggering_message_id: Optional[uuid.UUID] = None
    ) -> None:
        """Incrementally update context graph with tasks, commitments, status, and inconsistencies."""
        try:
            async with AsyncSessionLocal() as session:
                context_service = ContextGraphService(session)
                await context_service.process_messages_incremental(
                    conversation_id=conversation_id,
                    triggering_message_id=triggering_message_id,
                )
                await session.commit()
        except Exception as exc:
            logger.error(f"Failed context graph evaluation in decision engine: {exc}")

