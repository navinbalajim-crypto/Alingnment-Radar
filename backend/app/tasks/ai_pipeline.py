"""Asynchronous background task runner for AI alignment analysis and recommendations."""

import asyncio
import uuid
from typing import Optional
from app.core.logging import logger
from app.services.ai_decision_engine import AIDecisionEngine


async def execute_ai_pipeline(conversation_id: uuid.UUID, message_id: uuid.UUID) -> None:
    """
    Direct asynchronous execution of the AI pipeline for conversation analysis.
    Evaluates active finding resolution, new misalignment detection, and contextual recommendations.
    """
    try:
        await AIDecisionEngine.process_conversation(conversation_id, triggering_message_id=message_id)
    except Exception as exc:
        logger.error(f"Unhandled error in execute_ai_pipeline: {exc}")


def schedule_ai_pipeline(conversation_id: uuid.UUID, message_id: uuid.UUID) -> asyncio.Task:
    """
    Schedule debounced asynchronous execution of AI pipeline outside the HTTP request path.
    Batches rapid incoming messages within a 2.0s window before triggering inference.
    """
    return asyncio.create_task(AIDecisionEngine.handle_message_event(conversation_id, message_id))
