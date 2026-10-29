"""Automated tests for direct messaging, conversation listing, and history access controls."""

import uuid
import pytest
from httpx import AsyncClient
from app.models.user import User


@pytest.mark.asyncio
async def test_direct_conversation_creation_and_duplicate_prevention(
    client: AsyncClient, test_user: User, test_user_b: User, auth_headers: dict[str, str], auth_headers_b: dict[str, str]
):
    # 1. Alice creates direct chat with Bob
    resp1 = await client.post(f"/api/v1/conversations/direct/{test_user_b.username}", headers=auth_headers)
    assert resp1.status_code == 200
    conv1 = resp1.json()
    conv_id = conv1["id"]
    assert not conv1["is_group"]
    assert conv1["member_count"] == 2
    assert conv1["other_participant"]["username"] == test_user_b.username

    # 2. Alice calls it again -> MUST return same conversation ID (no duplicate)
    resp2 = await client.post(f"/api/v1/conversations/direct/{test_user_b.username}", headers=auth_headers)
    assert resp2.status_code == 200
    assert resp2.json()["id"] == conv_id

    # 3. Bob calls it with Alice -> MUST return same conversation ID
    resp3 = await client.post(f"/api/v1/conversations/direct/{test_user.username}", headers=auth_headers_b)
    assert resp3.status_code == 200
    assert resp3.json()["id"] == conv_id


@pytest.mark.asyncio
async def test_direct_conversation_self_chat_forbidden(
    client: AsyncClient, test_user: User, auth_headers: dict[str, str]
):
    resp = await client.post(f"/api/v1/conversations/direct/{test_user.username}", headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json()["code"] == "BAD_REQUEST"


@pytest.mark.asyncio
async def test_conversation_history_access_control(
    client: AsyncClient, test_user: User, test_user_b: User, auth_headers: dict[str, str]
):
    # Create conversation between Alice and Bob
    conv_resp = await client.post(f"/api/v1/conversations/direct/{test_user_b.username}", headers=auth_headers)
    conv_id = conv_resp.json()["id"]

    # Authorized member (Alice) reads messages
    resp_ok = await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=auth_headers)
    assert resp_ok.status_code == 200
    assert "messages" in resp_ok.json()

    # Unauthorized third user attempts to access history
    third_user_headers = {"Authorization": "Bearer invalid_or_unrelated"}
    resp_unauth = await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=third_user_headers)
    assert resp_unauth.status_code == 401

    # Random non-existent conversation ID
    random_id = uuid.uuid4()
    resp_nonexistent = await client.get(f"/api/v1/conversations/{random_id}/messages", headers=auth_headers)
    assert resp_nonexistent.status_code == 403


@pytest.mark.asyncio
async def test_timestamps_loaded_from_sqlite_are_serialised_as_utc(
    client: AsyncClient, db_session, test_user: User, test_user_b: User, auth_headers: dict[str, str]
):
    """SQLite drops tzinfo; the API must still send an explicit UTC offset or browsers show local-time-shifted
    timestamps (e.g. 'Yesterday' for a message sent minutes ago)."""
    from datetime import datetime

    conv_id = (await client.post(f"/api/v1/conversations/direct/{test_user_b.username}", headers=auth_headers)).json()["id"]
    sent = await client.post(f"/api/v1/conversations/{conv_id}/messages", headers=auth_headers, json={"content": "hello"})
    assert sent.status_code == 201
    db_session.expire_all()  # force the next read to come from the database, not the identity map

    history = (await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=auth_headers)).json()["messages"]
    listing = (await client.get("/api/v1/conversations", headers=auth_headers)).json()
    for stamp in (history[0]["created_at"], listing[0]["updated_at"]):
        assert datetime.fromisoformat(stamp.replace("Z", "+00:00")).utcoffset() is not None, stamp
