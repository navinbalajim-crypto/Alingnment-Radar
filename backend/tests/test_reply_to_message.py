"""Tests for WhatsApp-style reply to message feature."""

import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import create_access_token
from app.models.conversation import Conversation, ConversationMember
from app.models.message import Message
from app.models.user import User


@pytest.mark.asyncio
async def test_reply_to_message_in_same_conversation(
    client: AsyncClient, db_session: AsyncSession, test_user: User, test_user_b: User
):
    """Test sending a reply referencing a message in the same conversation."""
    # Create conversation
    conv = Conversation(is_group=False)
    db_session.add(conv)
    await db_session.flush()

    m1 = ConversationMember(conversation_id=conv.id, user_id=test_user.id)
    m2 = ConversationMember(conversation_id=conv.id, user_id=test_user_b.id)
    db_session.add_all([m1, m2])

    # Original message from user A
    orig_msg = Message(
        conversation_id=conv.id,
        sender_id=test_user.id,
        content="Are we still meeting at 3pm?",
    )
    db_session.add(orig_msg)
    await db_session.commit()
    await db_session.refresh(orig_msg)

    # User B replies to orig_msg
    token_b = create_access_token(user_id=str(test_user_b.id), username=test_user_b.username)
    headers_b = {"Authorization": f"Bearer {token_b}"}

    res = await client.post(
        f"/api/v1/conversations/{conv.id}/messages",
        json={
            "content": "Yes, see you in the main lobby.",
            "message_type": "text",
            "reply_to_message_id": str(orig_msg.id),
        },
        headers=headers_b,
    )
    assert res.status_code == 201
    reply_data = res.json()
    assert reply_data["content"] == "Yes, see you in the main lobby."
    assert reply_data["reply_to_message_id"] == str(orig_msg.id)
    assert reply_data["reply_to"] is not None
    assert reply_data["reply_to"]["content"] == "Are we still meeting at 3pm?"
    assert reply_data["reply_to"]["sender_username"] == test_user.username
    assert reply_data["reply_to"]["is_deleted_for_everyone"] is False


@pytest.mark.asyncio
async def test_cross_conversation_reply_rejection(
    client: AsyncClient, db_session: AsyncSession, test_user: User, test_user_b: User
):
    """Test that referencing a message from a different conversation is rejected with 400 Bad Request."""
    # Conversation 1
    conv1 = Conversation(is_group=False)
    # Conversation 2
    conv2 = Conversation(is_group=False)
    db_session.add_all([conv1, conv2])
    await db_session.flush()

    db_session.add_all([
        ConversationMember(conversation_id=conv1.id, user_id=test_user.id),
        ConversationMember(conversation_id=conv1.id, user_id=test_user_b.id),
        ConversationMember(conversation_id=conv2.id, user_id=test_user.id),
        ConversationMember(conversation_id=conv2.id, user_id=test_user_b.id),
    ])

    # Message in conv1
    msg_conv1 = Message(
        conversation_id=conv1.id,
        sender_id=test_user.id,
        content="Secret message in conv 1",
    )
    db_session.add(msg_conv1)
    await db_session.commit()
    await db_session.refresh(msg_conv1)

    # Attempt to reply to msg_conv1 from conv2
    token = create_access_token(user_id=str(test_user_b.id), username=test_user_b.username)
    headers = {"Authorization": f"Bearer {token}"}

    res = await client.post(
        f"/api/v1/conversations/{conv2.id}/messages",
        json={
            "content": "Trying to quote from another chat",
            "reply_to_message_id": str(msg_conv1.id),
        },
        headers=headers,
    )
    assert res.status_code == 400
    err_msg = res.json().get("message") or res.json().get("detail", "")
    assert "belongs to another conversation" in err_msg


@pytest.mark.asyncio
async def test_reply_to_deleted_original_message(
    client: AsyncClient, db_session: AsyncSession, test_user: User, test_user_b: User
):
    """Test that when original message is deleted for everyone, reply preview masks content and hides attachments."""
    conv = Conversation(is_group=False)
    db_session.add(conv)
    await db_session.flush()

    db_session.add_all([
        ConversationMember(conversation_id=conv.id, user_id=test_user.id),
        ConversationMember(conversation_id=conv.id, user_id=test_user_b.id),
    ])

    orig_msg = Message(
        conversation_id=conv.id,
        sender_id=test_user.id,
        content="Sensitive password to delete: P@ss123",
        is_deleted_for_everyone=False,
    )
    db_session.add(orig_msg)
    await db_session.flush()

    # Reply sent before deletion
    reply_msg = Message(
        conversation_id=conv.id,
        sender_id=test_user_b.id,
        content="Got it, will save it.",
        reply_to_message_id=orig_msg.id,
    )
    db_session.add(reply_msg)
    await db_session.commit()

    # Now original message is unsent for everyone
    token_a = create_access_token(user_id=str(test_user.id), username=test_user.username)
    headers_a = {"Authorization": f"Bearer {token_a}"}

    del_res = await client.delete(
        f"/api/v1/conversations/{conv.id}/messages/{orig_msg.id}",
        params={"delete_type": "everyone"},
        headers=headers_a,
    )
    assert del_res.status_code == 200

    # Fetch conversation messages history
    hist_res = await client.get(
        f"/api/v1/conversations/{conv.id}/messages",
        headers=headers_a,
    )
    assert hist_res.status_code == 200
    messages = hist_res.json()["messages"]

    # Find the reply message
    reply_in_hist = next(m for m in messages if m["id"] == str(reply_msg.id))
    assert reply_in_hist["reply_to"] is not None
    # Crucial security check: sensitive original content is NOT leaked
    assert reply_in_hist["reply_to"]["content"] == "This message was deleted."
    assert "P@ss123" not in reply_in_hist["reply_to"]["content"]
    assert reply_in_hist["reply_to"]["is_deleted_for_everyone"] is True


@pytest.mark.asyncio
async def test_reply_to_per_user_deleted_message_masking(
    client: AsyncClient, db_session: AsyncSession, test_user: User, test_user_b: User
):
    """Verify that when a user deletes a message 'for me', the quote preview is masked for that user without leaking to them."""
    conv = Conversation(is_group=False)
    db_session.add(conv)
    await db_session.flush()

    db_session.add_all([
        ConversationMember(conversation_id=conv.id, user_id=test_user.id),
        ConversationMember(conversation_id=conv.id, user_id=test_user_b.id),
    ])

    orig_msg = Message(
        conversation_id=conv.id,
        sender_id=test_user.id,
        content="Personal confidential note 9876",
    )
    db_session.add(orig_msg)
    await db_session.flush()

    reply_msg = Message(
        conversation_id=conv.id,
        sender_id=test_user_b.id,
        content="Understood.",
        reply_to_message_id=orig_msg.id,
    )
    db_session.add(reply_msg)
    await db_session.commit()

    token_a = create_access_token(user_id=str(test_user.id), username=test_user.username)
    headers_a = {"Authorization": f"Bearer {token_a}"}
    token_b = create_access_token(user_id=str(test_user_b.id), username=test_user_b.username)
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User A deletes orig_msg 'for me'
    del_res = await client.delete(
        f"/api/v1/conversations/{conv.id}/messages/{orig_msg.id}",
        params={"delete_type": "me"},
        headers=headers_a,
    )
    assert del_res.status_code == 200

    # User A views messages: parent content MUST be masked
    res_a = await client.get(f"/api/v1/conversations/{conv.id}/messages", headers=headers_a)
    assert res_a.status_code == 200
    msgs_a = res_a.json()["messages"]
    reply_a = next(m for m in msgs_a if m["id"] == str(reply_msg.id))
    assert reply_a["reply_to"] is not None
    assert reply_a["reply_to"]["content"] == "This message was deleted."
    assert "9876" not in reply_a["reply_to"]["content"]

    # User B views messages: parent content remains visible because User B did NOT delete it
    res_b = await client.get(f"/api/v1/conversations/{conv.id}/messages", headers=headers_b)
    assert res_b.status_code == 200
    msgs_b = res_b.json()["messages"]
    reply_b = next(m for m in msgs_b if m["id"] == str(reply_msg.id))
    assert reply_b["reply_to"] is not None
    assert "Personal confidential note 9876" in reply_b["reply_to"]["content"]


@pytest.mark.asyncio
async def test_attachment_upload_with_reply(
    client: AsyncClient, db_session: AsyncSession, test_user: User, test_user_b: User
):
    """Verify that uploading an attachment referencing a parent message preserves reply_to_message_id and preview."""
    import io
    conv = Conversation(is_group=False)
    db_session.add(conv)
    await db_session.flush()

    db_session.add_all([
        ConversationMember(conversation_id=conv.id, user_id=test_user.id),
        ConversationMember(conversation_id=conv.id, user_id=test_user_b.id),
    ])

    orig_msg = Message(
        conversation_id=conv.id,
        sender_id=test_user.id,
        content="Please send the project specification document.",
    )
    db_session.add(orig_msg)
    await db_session.commit()

    token_b = create_access_token(user_id=str(test_user_b.id), username=test_user_b.username)
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Valid PNG bytes header
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
    files = {"file": ("spec.png", io.BytesIO(png_bytes), "image/png")}
    data = {
        "caption": "Here is the diagram requested.",
        "reply_to_message_id": str(orig_msg.id),
    }

    res = await client.post(
        f"/api/v1/conversations/{conv.id}/attachments",
        files=files,
        data=data,
        headers=headers_b,
    )
    assert res.status_code == 201
    res_data = res.json()
    assert res_data["message_type"] == "attachment"
    assert res_data["reply_to_message_id"] == str(orig_msg.id)
    assert res_data["reply_to"] is not None
    assert "specification document" in res_data["reply_to"]["content"]

