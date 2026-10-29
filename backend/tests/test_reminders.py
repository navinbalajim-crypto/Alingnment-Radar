"""Tests for task extraction, persistent reminder scheduling, and notification delivery."""

from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utc_now
from app.models.conversation import Conversation
from app.models.user import User
from app.services.conversation_service import ConversationService
from app.services.task_extractor import extract_task_from_text
from app.tasks.reminder_worker import check_and_dispatch_reminders


@pytest.fixture
async def direct_conversation(db_session: AsyncSession, test_user: User, test_user_b: User) -> Conversation:
    conv_service = ConversationService(db_session)
    summary = await conv_service.get_or_create_direct_conversation(test_user.id, test_user_b.username)
    await db_session.commit()
    conv = await conv_service.conv_repo.get_by_id(summary.id)
    assert conv is not None
    return conv


def test_natural_language_task_extraction():
    # 1. Clear deadline message
    kolkata_tz = timezone(timedelta(hours=5, minutes=30))
    ref_dt = datetime(2026, 10, 27, 9, 0, tzinfo=kolkata_tz)
    task1 = extract_task_from_text("Tomorrow at 10 AM, we need to submit the frontend.", reference_dt=ref_dt)
    assert task1 is not None
    assert "frontend" in task1["title"].lower() or "submit" in task1["title"].lower()
    assert task1["due_at"].startswith("2026-10-28T10:00:00")

    # 2. Assignment deadline
    task2 = extract_task_from_text("The project report is due Friday at 5 PM.", reference_dt=ref_dt)
    assert task2 is not None
    assert "project report" in task2["title"].lower()

    # 3. Incidental past remark (must NOT create a task!)
    past = extract_task_from_text("Yesterday I watched a movie at 10 PM.", reference_dt=ref_dt)
    assert past is None

    # 4. Casual conversation (must NOT create a task!)
    casual = extract_task_from_text("Hi bro, how are you?", reference_dt=ref_dt)
    assert casual is None


@pytest.mark.asyncio
async def test_extract_endpoint(client: AsyncClient, direct_conversation: Conversation, auth_headers: dict):
    res = await client.post(
        f"/api/v1/conversations/{direct_conversation.id}/reminders/extract",
        json={"text": "Tomorrow at 10 AM, we need to submit the frontend.", "timezone": "Asia/Kolkata"},
        headers=auth_headers,
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["task_detected"] is True
    assert payload["due_at"] is not None


@pytest.mark.asyncio
async def test_create_and_query_persistent_reminder(
    client: AsyncClient, direct_conversation: Conversation, auth_headers: dict, test_user_b: User
):
    now = utc_now()
    due_at = now + timedelta(hours=2)

    create_payload = {
        "title": "Submit Frontend Implementation",
        "due_at": due_at.isoformat(),
        "advance_reminder_minutes": 30,
        "responsible_user_id": str(test_user_b.id),
        "timezone": "Asia/Kolkata",
    }

    res = await client.post(
        f"/api/v1/conversations/{direct_conversation.id}/reminders",
        json=create_payload,
        headers=auth_headers,
    )
    assert res.status_code == 201
    reminder = res.json()
    assert reminder["title"] == "Submit Frontend Implementation"
    assert reminder["advance_reminder_minutes"] == 30
    assert reminder["status"] == "pending"

    # Query reminders for conversation
    conv_rems = await client.get(
        f"/api/v1/conversations/{direct_conversation.id}/reminders",
        headers=auth_headers,
    )
    assert conv_rems.status_code == 200
    assert len(conv_rems.json()) >= 1


@pytest.mark.asyncio
async def test_worker_dispatches_advance_and_due_notifications_idempotently(
    client: AsyncClient, direct_conversation: Conversation, auth_headers: dict, test_user: User, db_session: AsyncSession
):
    now = utc_now()
    # Reminder where advance is due now (due in 20 mins, advance was 30 mins)
    due_at = now + timedelta(minutes=20)

    res = await client.post(
        f"/api/v1/conversations/{direct_conversation.id}/reminders",
        json={
            "title": "Review API Contract",
            "due_at": due_at.isoformat(),
            "advance_reminder_minutes": 30,
            "timezone": "Asia/Kolkata",
        },
        headers=auth_headers,
    )
    assert res.status_code == 201

    # First check & dispatch run
    delivered = await check_and_dispatch_reminders(db=db_session)
    assert delivered >= 1

    # Check notification persisted
    notifs_res = await client.get("/api/v1/notifications", headers=auth_headers)
    assert notifs_res.status_code == 200
    notifs = notifs_res.json()
    assert any("Review API Contract" in n["title"] or "Review API Contract" in n["message"] for n in notifs)

    # Second dispatch run immediately should NOT duplicate delivery
    delivered_again = await check_and_dispatch_reminders(db=db_session)
    assert delivered_again == 0


@pytest.mark.asyncio
async def test_completed_task_stops_notifications(
    client: AsyncClient, direct_conversation: Conversation, auth_headers: dict, db_session: AsyncSession
):
    now = utc_now()
    due_at = now - timedelta(minutes=5)  # past due

    res = await client.post(
        f"/api/v1/conversations/{direct_conversation.id}/reminders",
        json={
            "title": "Old Task Already Completed",
            "due_at": due_at.isoformat(),
            "advance_reminder_minutes": 10,
            "timezone": "Asia/Kolkata",
        },
        headers=auth_headers,
    )
    rem_id = res.json()["id"]

    # Mark completed
    patch_res = await client.patch(
        f"/api/v1/reminders/{rem_id}",
        json={"status": "completed"},
        headers=auth_headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == "completed"

    # Worker skips completed tasks
    delivered = await check_and_dispatch_reminders(db=db_session)
    assert delivered == 0


@pytest.mark.asyncio
async def test_reminder_authorization_checks(
    client: AsyncClient, direct_conversation: Conversation, auth_headers: dict, db_session: AsyncSession
):
    # Create third outsider user Charlie
    charlie = User(
        email="charlie_rem@example.com",
        username="charlie_rem",
        username_normalized="charlie_rem",
        display_name="Charlie Reminder",
        is_active=True,
    )
    db_session.add(charlie)
    await db_session.commit()
    from app.core.security import create_access_token
    charlie_token = create_access_token(user_id=str(charlie.id), username=charlie.username)
    charlie_headers = {"Authorization": f"Bearer {charlie_token}"}

    # Charlie (non-member) attempts extract on direct_conversation -> 403
    res_extract = await client.post(
        f"/api/v1/conversations/{direct_conversation.id}/reminders/extract",
        json={"text": "Tomorrow at 10 AM, submit the code."},
        headers=charlie_headers,
    )
    assert res_extract.status_code == 403

    # Charlie attempts to list reminders on direct_conversation -> 403
    res_list = await client.get(
        f"/api/v1/conversations/{direct_conversation.id}/reminders",
        headers=charlie_headers,
    )
    assert res_list.status_code == 403

    # Alice creates a reminder
    now = utc_now()
    res_create = await client.post(
        f"/api/v1/conversations/{direct_conversation.id}/reminders",
        json={
            "title": "Alice Private Task",
            "due_at": (now + timedelta(hours=3)).isoformat(),
            "advance_reminder_minutes": 15,
        },
        headers=auth_headers,
    )
    rem_id = res_create.json()["id"]

    # Charlie attempts to delete Alice's reminder -> 403
    res_del = await client.delete(
        f"/api/v1/reminders/{rem_id}",
        headers=charlie_headers,
    )
    assert res_del.status_code == 403
