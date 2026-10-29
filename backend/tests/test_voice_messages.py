"""Tests for voice message upload, background transcription, multilingual translation, caching, and consent enforcement."""

import io
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.attachment import MessageAttachment
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.models.voice_transcript import VoiceTranscript
from app.services.conversation_service import ConversationService
from app.services.speech_service import SpeechService


@pytest.fixture
async def direct_conversation(db_session: AsyncSession, test_user: User, test_user_b: User) -> Conversation:
    conv_service = ConversationService(db_session)
    summary = await conv_service.get_or_create_direct_conversation(test_user.id, test_user_b.username)
    await db_session.commit()
    conv = await conv_service.conv_repo.get_by_id(summary.id)
    assert conv is not None
    return conv


@pytest.mark.asyncio
async def test_upload_valid_voice_note(
    client: AsyncClient,
    direct_conversation: Conversation,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """Uploading a valid WebM audio file creates a voice_note Message and initial VoiceTranscript."""
    # WebM magic bytes: 0x1A 0x45 0xDF 0xA3
    webm_bytes = b"\x1a\x45\xdf\xa3" + b"\x00" * 300
    files = {"file": ("recording.webm", webm_bytes, "audio/webm")}
    data = {"duration": "14.5"}

    with patch("app.services.speech_service.SpeechService.run_transcription_background", new_callable=AsyncMock) as mock_bg:
        res = await client.post(
            f"/api/v1/conversations/{direct_conversation.id}/voice",
            files=files,
            data=data,
            headers=auth_headers,
        )

        assert res.status_code == 201
        payload = res.json()
        assert payload["message"]["message_type"] == "voice_note"
        assert payload["message"]["msg_metadata"]["is_voice_note"] is True
        assert payload["message"]["msg_metadata"]["duration_seconds"] == 14.5
        assert payload["transcript"]["transcription_status"] == "uploaded"
        assert payload["transcript"]["duration_seconds"] == 14.5

        # Confirm background transcription was triggered
        assert mock_bg.call_count == 1

    # Verify database persistence
    msg_id = uuid.UUID(payload["message"]["id"])
    t_stmt = select(VoiceTranscript).where(VoiceTranscript.message_id == msg_id)
    t = (await db_session.execute(t_stmt)).scalar_one_or_none()
    assert t is not None
    assert t.transcription_status == "uploaded"


@pytest.mark.asyncio
async def test_voice_note_duration_validation(
    client: AsyncClient,
    direct_conversation: Conversation,
    auth_headers: dict,
):
    """Voice note with zero or negative duration is rejected with 400 Bad Request."""
    webm_bytes = b"\x1a\x45\xdf\xa3" + b"\x00" * 100
    files = {"file": ("recording.webm", webm_bytes, "audio/webm")}
    data = {"duration": "0.0"}

    res = await client.post(
        f"/api/v1/conversations/{direct_conversation.id}/voice",
        files=files,
        data=data,
        headers=auth_headers,
    )
    assert res.status_code == 400
    assert "duration must be greater than zero" in res.json()["message"]


@pytest.mark.asyncio
async def test_voice_note_unauthorized_user(
    client: AsyncClient,
    direct_conversation: Conversation,
    db_session: AsyncSession,
):
    """A user not in the conversation cannot upload voice messages."""
    charlie = User(
        email="charlie_voice@example.com",
        username="charlie_voice",
        username_normalized="charlie_voice",
        display_name="Charlie Voice",
        is_active=True,
    )
    db_session.add(charlie)
    await db_session.commit()
    from app.core.security import create_access_token
    token = create_access_token(user_id=str(charlie.id), username=charlie.username)

    webm_bytes = b"\x1a\x45\xdf\xa3" + b"\x00" * 100
    files = {"file": ("recording.webm", webm_bytes, "audio/webm")}
    data = {"duration": "5.0"}

    res = await client.post(
        f"/api/v1/conversations/{direct_conversation.id}/voice",
        files=files,
        data=data,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_voice_translation_workflow_and_caching(
    client: AsyncClient,
    direct_conversation: Conversation,
    auth_headers: dict,
    db_session: AsyncSession,
    test_user: User,
):
    """Translating a voice note returns translated text and caches it for repeat calls."""
    # Create message and completed VoiceTranscript
    msg = Message(
        conversation_id=direct_conversation.id,
        sender_id=test_user.id,
        content="Voice note",
        message_type="voice_note",
        msg_metadata={"is_voice_note": True},
    )
    db_session.add(msg)
    await db_session.flush()

    transcript = VoiceTranscript(
        message_id=msg.id,
        duration_seconds=10.0,
        source_language="en",
        transcript_text="Hello, thank you for joining the team.",
        transcription_status="completed",
        translations={},
        provider_metadata={},
    )
    db_session.add(transcript)
    await db_session.commit()

    with patch.object(
        SpeechService,
        "translate_text",
        new_callable=AsyncMock,
        return_value=("Hola, gracias por unirte al equipo.", "verified-llm"),
    ) as mock_translate:
        # First translation call
        res1 = await client.post(
            f"/api/v1/conversations/{direct_conversation.id}/messages/{msg.id}/translate",
            json={"target_language": "es"},
            headers=auth_headers,
        )
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["target_language"] == "es"
        assert data1["translated_text"] == "Hola, gracias por unirte al equipo."
        assert data1["cached"] is False
        assert mock_translate.call_count == 1

        # Second translation call with same language should return cached result without hitting provider
        res2 = await client.post(
            f"/api/v1/conversations/{direct_conversation.id}/messages/{msg.id}/translate",
            json={"target_language": "es"},
            headers=auth_headers,
        )
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["cached"] is True
        assert data2["translated_text"] == "Hola, gracias por unirte al equipo."
        # Call count didn't increase
        assert mock_translate.call_count == 1


@pytest.mark.asyncio
async def test_voice_retry_transcription(
    client: AsyncClient,
    direct_conversation: Conversation,
    auth_headers: dict,
    db_session: AsyncSession,
    test_user: User,
):
    """POST /retry-transcription re-queues transcription for a voice note."""
    msg = Message(
        conversation_id=direct_conversation.id,
        sender_id=test_user.id,
        content="Voice note",
        message_type="voice_note",
    )
    db_session.add(msg)
    await db_session.flush()

    att = MessageAttachment(
        message_id=msg.id,
        conversation_id=direct_conversation.id,
        uploader_id=test_user.id,
        original_filename="voice.webm",
        content_type="audio/webm",
        file_size=1024,
        storage_path="mock/path/voice.webm",
    )
    db_session.add(att)
    await db_session.flush()

    transcript = VoiceTranscript(
        message_id=msg.id,
        attachment_id=att.id,
        transcription_status="failed",
        error_message="Network timeout",
    )
    db_session.add(transcript)
    await db_session.commit()

    with patch("app.services.speech_service.SpeechService.run_transcription_background", new_callable=AsyncMock) as mock_bg:
        res = await client.post(
            f"/api/v1/conversations/{direct_conversation.id}/messages/{msg.id}/retry-transcription",
            headers=auth_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["transcription_status"] == "queued"
        assert mock_bg.call_count == 1


@pytest.mark.asyncio
async def test_voice_message_conversation_isolation(
    client: AsyncClient,
    direct_conversation: Conversation,
    db_session: AsyncSession,
    test_user: User,
):
    """A user cannot translate or retry voice notes in conversations they do not belong to."""
    charlie = User(
        email="charlie_iso@example.com",
        username="charlie_iso",
        username_normalized="charlie_iso",
        display_name="Charlie Isolation",
        is_active=True,
    )
    db_session.add(charlie)
    await db_session.commit()
    from app.core.security import create_access_token
    charlie_token = create_access_token(user_id=str(charlie.id), username=charlie.username)

    msg = Message(
        conversation_id=direct_conversation.id,
        sender_id=test_user.id,
        content="Voice note",
        message_type="voice_note",
    )
    db_session.add(msg)
    await db_session.flush()

    res = await client.post(
        f"/api/v1/conversations/{direct_conversation.id}/messages/{msg.id}/translate",
        json={"target_language": "es"},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_voice_note_from_another_conversation_is_not_reachable_via_own_conversation(
    client: AsyncClient,
    direct_conversation: Conversation,
    db_session: AsyncSession,
    test_user: User,
):
    """A member of conversation X cannot translate or re-transcribe a voice note from conversation Y by
    putting Y's message id under X's URL."""
    from app.core.security import create_access_token

    charlie = User(email="charlie_x@example.com", username="charlie_x", username_normalized="charlie_x",
                   display_name="Charlie X", is_active=True)
    db_session.add(charlie)
    await db_session.commit()
    conv_service = ConversationService(db_session)
    own = await conv_service.get_or_create_direct_conversation(charlie.id, test_user.username)
    await db_session.commit()
    charlie_headers = {"Authorization": f"Bearer {create_access_token(user_id=str(charlie.id), username=charlie.username)}"}

    # voice note in alice <-> bob conversation, which charlie is not part of
    msg = Message(conversation_id=direct_conversation.id, sender_id=test_user.id, content="Voice note", message_type="voice_note")
    db_session.add(msg)
    await db_session.flush()
    att = MessageAttachment(message_id=msg.id, conversation_id=direct_conversation.id, uploader_id=test_user.id,
                            original_filename="voice.webm", content_type="audio/webm", file_size=1024,
                            storage_path="mock/path/voice.webm")
    db_session.add(att)
    await db_session.flush()
    db_session.add(VoiceTranscript(message_id=msg.id, attachment_id=att.id, source_language="en",
                                   transcript_text="Private plan details.", transcription_status="completed",
                                   translations={}, provider_metadata={}))
    await db_session.commit()

    with patch.object(SpeechService, "translate_text", new_callable=AsyncMock, return_value=("x", "p")) as mock_translate, \
         patch("app.services.speech_service.SpeechService.run_transcription_background", new_callable=AsyncMock) as mock_bg:
        res = await client.post(f"/api/v1/conversations/{own.id}/messages/{msg.id}/translate",
                                json={"target_language": "es"}, headers=charlie_headers)
        assert res.status_code == 404
        res = await client.post(f"/api/v1/conversations/{own.id}/messages/{msg.id}/retry-transcription",
                                headers=charlie_headers)
        assert res.status_code == 404
        assert mock_translate.call_count == 0
        assert mock_bg.call_count == 0


@pytest.mark.asyncio
async def test_nvidia_canary_asr_transcribe_success(tmp_path: Path, db_session: AsyncSession):
    """Canary-1B ASR parses audio through gRPC NVCF service and returns transcript."""
    dummy_wav = tmp_path / "sample.wav"
    dummy_wav.write_bytes(b"RIFF" + b"\x00" * 100)

    service = SpeechService(db_session)

    class MockAlt:
        transcript = "Canary transcription verified."

    class MockResult:
        alternatives = [MockAlt()]

    class MockResponse:
        results = [MockResult()]

    with patch.object(Settings, "is_provider_configured", return_value=True), \
         patch("riva.client.ASRService") as mock_asr_cls:
        mock_asr_instance = mock_asr_cls.return_value
        mock_asr_instance.offline_recognize.return_value = MockResponse()

        text, lang, provider = await service.transcribe_audio_file(dummy_wav)
        assert text == "Canary transcription verified."
        assert provider == "nvidia-canary-1b-asr"


@pytest.mark.asyncio
async def test_nvidia_canary_asr_failure_fallback(tmp_path: Path, db_session: AsyncSession):
    """When Canary-1B fails or times out, transcription falls back gracefully without crashing."""
    dummy_wav = tmp_path / "sample.wav"
    dummy_wav.write_bytes(b"RIFF" + b"\x00" * 100)

    service = SpeechService(db_session)

    with patch.object(Settings, "is_provider_configured", side_effect=lambda p: p in ("nvidia_asr", "groq")), \
         patch("riva.client.ASRService", side_effect=Exception("NVCF connection timeout")):
        with patch("httpx.AsyncClient.post") as mock_groq_post:
            class MockGroqResp:
                status_code = 200
                def json(self):
                    return {"text": "Whisper fallback transcript", "language": "en"}
            mock_groq_post.return_value = MockGroqResp()

            text, lang, provider = await service.transcribe_audio_file(dummy_wav)
            assert text == "Whisper fallback transcript"
            assert provider == "groq-whisper"


@pytest.mark.asyncio
async def test_nvidia_riva_translate_success(db_session: AsyncSession):
    """Riva Translate 1.6b translates text through gRPC NVCF client."""
    service = SpeechService(db_session)

    class MockTranslation:
        text = "Hola, bienvenido al sistema."

    class MockResponse:
        translations = [MockTranslation()]

    with patch.object(Settings, "is_provider_configured", return_value=True), \
         patch("riva.client.NeuralMachineTranslationClient") as mock_nmt_cls:
        mock_nmt = mock_nmt_cls.return_value
        mock_nmt.translate.return_value = MockResponse()

        translated, provider = await service.translate_text("Hello, welcome to the system.", "en", "es")
        assert translated == "Hola, bienvenido al sistema."
        assert provider == "nvidia-riva-translate-1.6b"


@pytest.mark.asyncio
async def test_nvidia_riva_translate_failure_fallback_to_rest(db_session: AsyncSession):
    """When Riva gRPC fails, it falls back to Riva 4B REST, then Groq, then local dictionary."""
    service = SpeechService(db_session)

    with patch.object(Settings, "is_provider_configured", side_effect=lambda p: p in ("nvidia_translate", "groq")), \
         patch("riva.client.NeuralMachineTranslationClient", side_effect=Exception("gRPC unavailable")):
        with patch("httpx.AsyncClient.post") as mock_http_post:
            class MockRestResp:
                status_code = 200
                def json(self):
                    return {"choices": [{"message": {"content": "Bonjour le monde"}}]}
            mock_http_post.return_value = MockRestResp()

            translated, provider = await service.translate_text("Hello world", "en", "fr")
            assert translated == "Bonjour le monde"
            assert provider == "nvidia-riva-translate-4b-v2"


@pytest.mark.asyncio
async def test_voice_translation_unsupported_language_rejection(
    client: AsyncClient,
    direct_conversation: Conversation,
    auth_headers: dict,
    db_session: AsyncSession,
    test_user: User,
):
    """Unsupported target languages are rejected with 400 Bad Request."""
    msg = Message(
        conversation_id=direct_conversation.id,
        sender_id=test_user.id,
        content="Voice note",
        message_type="voice_note",
    )
    db_session.add(msg)
    await db_session.flush()

    transcript = VoiceTranscript(
        message_id=msg.id,
        duration_seconds=5.0,
        source_language="en",
        transcript_text="Testing unsupported language.",
        transcription_status="completed",
        translations={},
        provider_metadata={},
    )
    db_session.add(transcript)
    await db_session.commit()

    res = await client.post(
        f"/api/v1/conversations/{direct_conversation.id}/messages/{msg.id}/translate",
        json={"target_language": "klingon"},
        headers=auth_headers,
    )
    assert res.status_code == 400
    assert "not supported" in res.json()["message"]


@pytest.mark.asyncio
async def test_voice_note_file_size_exceeded(
    client: AsyncClient,
    direct_conversation: Conversation,
    auth_headers: dict,
):
    """Audio files larger than 10 MB are rejected with 400 Bad Request."""
    # 10 MB + 1 byte
    oversized = b"\x1a\x45\xdf\xa3" + b"\x00" * (10 * 1024 * 1024 + 10)
    files = {"file": ("recording.webm", oversized, "audio/webm")}
    data = {"duration": "10.0"}

    res = await client.post(
        f"/api/v1/conversations/{direct_conversation.id}/voice",
        files=files,
        data=data,
        headers=auth_headers,
    )
    assert res.status_code == 400
    assert "exceeds" in res.json()["message"]


@pytest.mark.asyncio
async def test_voice_audio_is_not_sent_to_cloud_speech_providers_without_sender_consent(
    direct_conversation: Conversation,
    db_session: AsyncSession,
    test_user: User,
):
    """Without the sender's AI consent no transcription provider is called; with consent it is."""
    msg = Message(conversation_id=direct_conversation.id, sender_id=test_user.id, content="Voice note", message_type="voice_note")
    db_session.add(msg)
    await db_session.flush()
    db_session.add(VoiceTranscript(message_id=msg.id, transcription_status="uploaded", translations={}, provider_metadata={}))
    await db_session.commit()

    async def run():
        with patch("app.services.speech_service.AsyncSessionLocal", return_value=db_session), \
             patch("app.services.speech_service.sio.emit", new_callable=AsyncMock), \
             patch.object(SpeechService, "transcribe_audio_file", new_callable=AsyncMock,
                          return_value=("hello team", "en", "mock-asr")) as mock_asr:
            await SpeechService.run_transcription_background(msg.id, direct_conversation.id, "mock/path/voice.webm")
        transcript = (await db_session.execute(select(VoiceTranscript).where(VoiceTranscript.message_id == msg.id))).scalar_one()
        await db_session.refresh(transcript)
        return mock_asr.call_count, transcript.transcription_status

    async def set_consent(value: bool):
        # the service closes the shared session, which detaches test_user, so write the flag explicitly
        await db_session.execute(update(User).where(User.id == test_user.id).values(ai_draft_analysis_consent=value))
        await db_session.commit()

    await set_consent(False)
    assert await run() == (0, "consent_required")

    await set_consent(True)
    assert await run() == (1, "completed")
