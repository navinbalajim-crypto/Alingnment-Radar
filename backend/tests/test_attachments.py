"""Tests for file and image attachment sharing up to 10 MB with strict validation."""

import io
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.user import User
from app.services.conversation_service import ConversationService
from app.services.attachment_service import MAX_FILE_SIZE


@pytest.fixture
async def direct_conversation(db_session: AsyncSession, test_user: User, test_user_b: User) -> Conversation:
    conv_service = ConversationService(db_session)
    summary = await conv_service.get_or_create_direct_conversation(test_user.id, test_user_b.username)
    await db_session.commit()
    conv = await conv_service.conv_repo.get_by_id(summary.id)
    assert conv is not None
    return conv


@pytest.mark.asyncio
async def test_upload_valid_image(client: AsyncClient, direct_conversation: Conversation, auth_headers: dict):
    # Valid PNG image bytes (PNG signature)
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
    files = {"file": ("screenshot.png", png_bytes, "image/png")}
    data = {"caption": "Here is the UI mockup"}

    res = await client.post(
        f"/api/v1/conversations/{direct_conversation.id}/attachments",
        files=files,
        data=data,
        headers=auth_headers,
    )
    assert res.status_code == 201
    payload = res.json()
    assert payload["message_type"] == "attachment"
    assert payload["content"] == "Here is the UI mockup"
    assert len(payload["attachments"]) == 1
    att = payload["attachments"][0]
    assert att["original_filename"] == "screenshot.png"
    assert att["content_type"] == "image/png"
    assert att["file_size"] == len(png_bytes)


@pytest.mark.asyncio
async def test_upload_valid_document(client: AsyncClient, direct_conversation: Conversation, auth_headers: dict):
    # Valid PDF document bytes (PDF signature)
    pdf_bytes = b"%PDF-1.4\n%EOF" + b"12345"
    files = {"file": ("project_spec.pdf", pdf_bytes, "application/pdf")}

    res = await client.post(
        f"/api/v1/conversations/{direct_conversation.id}/attachments",
        files=files,
        headers=auth_headers,
    )
    assert res.status_code == 201
    payload = res.json()
    assert payload["message_type"] == "attachment"
    assert len(payload["attachments"]) == 1
    assert payload["attachments"][0]["content_type"] == "application/pdf"


@pytest.mark.asyncio
async def test_upload_valid_text_file(client: AsyncClient, direct_conversation: Conversation, auth_headers: dict):
    txt_bytes = b"Hello world, this is a plain text file for testing."
    files = {"file": ("notes.txt", txt_bytes, "text/plain")}

    res = await client.post(
        f"/api/v1/conversations/{direct_conversation.id}/attachments",
        files=files,
        headers=auth_headers,
    )
    assert res.status_code == 201
    payload = res.json()
    assert len(payload["attachments"]) == 1
    assert payload["attachments"][0]["content_type"] == "text/plain"


@pytest.mark.asyncio
async def test_upload_oversized_file_rejected(client: AsyncClient, direct_conversation: Conversation, auth_headers: dict):
    # File larger than 10 MB (10 MB + 1024 bytes)
    oversized_bytes = b"%PDF-1.4\n" + (b"0" * (MAX_FILE_SIZE + 1024))
    files = {"file": ("huge_file.pdf", io.BytesIO(oversized_bytes), "application/pdf")}

    res = await client.post(
        f"/api/v1/conversations/{direct_conversation.id}/attachments",
        files=files,
        headers=auth_headers,
    )
    assert res.status_code == 400
    assert "exceeds 10 MB limit" in res.json()["message"]


@pytest.mark.asyncio
async def test_upload_disallowed_extension_rejected(client: AsyncClient, direct_conversation: Conversation, auth_headers: dict):
    exe_bytes = b"MZ\x90\x00\x03\x00\x00\x00"
    files = {"file": ("payload.exe", exe_bytes, "application/octet-stream")}

    res = await client.post(
        f"/api/v1/conversations/{direct_conversation.id}/attachments",
        files=files,
        headers=auth_headers,
    )
    assert res.status_code == 400
    assert "not supported" in res.json()["message"]


@pytest.mark.asyncio
async def test_upload_spoofed_signature_rejected(client: AsyncClient, direct_conversation: Conversation, auth_headers: dict):
    # Extension is .png but file header is not PNG
    fake_png = b"THIS IS NOT A PNG IMAGE AT ALL"
    files = {"file": ("fake.png", fake_png, "image/png")}

    res = await client.post(
        f"/api/v1/conversations/{direct_conversation.id}/attachments",
        files=files,
        headers=auth_headers,
    )
    assert res.status_code == 400
    assert "signature does not match" in res.json()["message"]


@pytest.mark.asyncio
async def test_download_attachment_authorized(
    client: AsyncClient, direct_conversation: Conversation, auth_headers: dict, auth_headers_b: dict
):
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    upload_res = await client.post(
        f"/api/v1/conversations/{direct_conversation.id}/attachments",
        files={"file": ("test.png", png_bytes, "image/png")},
        headers=auth_headers,
    )
    assert upload_res.status_code == 201
    att_id = upload_res.json()["attachments"][0]["id"]

    # Bob (participant) can download
    res_b = await client.get(
        f"/api/v1/conversations/{direct_conversation.id}/attachments/{att_id}",
        headers=auth_headers_b,
    )
    assert res_b.status_code == 200
    assert res_b.content == png_bytes
    assert res_b.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.asyncio
async def test_download_attachment_unauthorized_non_member(
    client: AsyncClient, direct_conversation: Conversation, db_session: AsyncSession, auth_headers: dict
):
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    upload_res = await client.post(
        f"/api/v1/conversations/{direct_conversation.id}/attachments",
        files={"file": ("test.png", png_bytes, "image/png")},
        headers=auth_headers,
    )
    att_id = upload_res.json()["attachments"][0]["id"]

    # Create third outsider user Charlie
    charlie = User(
        email="charlie@example.com",
        username="charlie",
        username_normalized="charlie",
        display_name="Charlie Chaplin",
        is_active=True,
    )
    db_session.add(charlie)
    await db_session.commit()
    from app.core.security import create_access_token
    charlie_token = create_access_token(user_id=str(charlie.id), username=charlie.username)
    charlie_headers = {"Authorization": f"Bearer {charlie_token}"}

    # Charlie is not in direct_conversation -> 403 Forbidden
    res = await client.get(
        f"/api/v1/conversations/{direct_conversation.id}/attachments/{att_id}",
        headers=charlie_headers,
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_download_attachment_revoked_when_message_unsent(
    client: AsyncClient, direct_conversation: Conversation, auth_headers: dict
):
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    upload_res = await client.post(
        f"/api/v1/conversations/{direct_conversation.id}/attachments",
        files={"file": ("confidential.png", png_bytes, "image/png")},
        headers=auth_headers,
    )
    msg_id = upload_res.json()["id"]
    att_id = upload_res.json()["attachments"][0]["id"]

    # Author unsends message for everyone
    del_res = await client.delete(
        f"/api/v1/conversations/{direct_conversation.id}/messages/{msg_id}",
        params={"delete_type": "everyone"},
        headers=auth_headers,
    )
    assert del_res.status_code == 200

    # Attachment download is now revoked
    res = await client.get(
        f"/api/v1/conversations/{direct_conversation.id}/attachments/{att_id}",
        headers=auth_headers,
    )
    assert res.status_code == 404
    assert "no longer available" in res.json()["message"]
