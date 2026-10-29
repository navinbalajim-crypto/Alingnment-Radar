"""Automated tests for passwordless authentication flows and security controls."""

from datetime import timedelta
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.security import hash_otp_code, rate_limiter
from app.db.base import utc_now
from app.models.verification import VerificationChallenge
from app.models.user import User


@pytest.mark.asyncio
async def test_request_registration_code_success(client: AsyncClient, db_session: AsyncSession):
    rate_limiter._records.clear()
    resp = await client.post("/api/v1/auth/register/request-code", json={"email": "newuser@example.com"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "newuser@example.com"
    assert "Verification code sent" in data["message"]

    # Verify challenge persisted in DB
    stmt = select(VerificationChallenge).where(VerificationChallenge.email == "newuser@example.com")
    challenge = (await db_session.execute(stmt)).scalar_one_or_none()
    assert challenge is not None
    assert challenge.purpose == "registration"
    assert not challenge.is_consumed


@pytest.mark.asyncio
async def test_request_registration_code_duplicate_email(client: AsyncClient, test_user: User):
    rate_limiter._records.clear()
    resp = await client.post("/api/v1/auth/register/request-code", json={"email": test_user.email})
    assert resp.status_code == 409
    assert resp.json()["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_verify_registration_code_and_reuse_prevention(client: AsyncClient, db_session: AsyncSession):
    rate_limiter._records.clear()
    email = "signup@example.com"
    code = "123456"
    hashed = hash_otp_code(code)
    challenge = VerificationChallenge(
        email=email,
        hashed_code=hashed,
        purpose="registration",
        expires_at=utc_now() + timedelta(minutes=10),
        max_attempts=5,
        attempts=0,
    )
    db_session.add(challenge)
    await db_session.commit()

    # 1. Invalid code attempt
    resp_bad = await client.post("/api/v1/auth/register/verify-code", json={"email": email, "code": "999999"})
    assert resp_bad.status_code == 400
    assert "Invalid verification code" in resp_bad.json()["message"]

    # 2. Correct code
    resp_ok = await client.post("/api/v1/auth/register/verify-code", json={"email": email, "code": code})
    assert resp_ok.status_code == 200
    ticket = resp_ok.json()["registration_ticket"]
    assert ticket

    # 3. Reuse prevention - second attempt with same code must fail
    resp_reuse = await client.post("/api/v1/auth/register/verify-code", json={"email": email, "code": code})
    assert resp_reuse.status_code == 400


@pytest.mark.asyncio
async def test_verify_code_expired(client: AsyncClient, db_session: AsyncSession):
    rate_limiter._records.clear()
    email = "expired@example.com"
    code = "123456"
    hashed = hash_otp_code(code)
    challenge = VerificationChallenge(
        email=email,
        hashed_code=hashed,
        purpose="registration",
        expires_at=utc_now() - timedelta(minutes=1),  # Expired
        max_attempts=5,
        attempts=0,
    )
    db_session.add(challenge)
    await db_session.commit()

    resp = await client.post("/api/v1/auth/register/verify-code", json={"email": email, "code": code})
    assert resp.status_code == 400
    assert "expired" in resp.json()["message"]


@pytest.mark.asyncio
async def test_complete_registration_and_case_insensitive_username(client: AsyncClient, db_session: AsyncSession):
    rate_limiter._records.clear()
    email = "finishreg@example.com"
    code = "654321"
    db_session.add(
        VerificationChallenge(
            email=email,
            hashed_code=hash_otp_code(code),
            purpose="registration",
            expires_at=utc_now() + timedelta(minutes=10),
        )
    )
    await db_session.commit()

    verify_resp = await client.post("/api/v1/auth/register/verify-code", json={"email": email, "code": code})
    ticket = verify_resp.json()["registration_ticket"]

    # Complete registration with mixed-case username
    resp = await client.post(
        "/api/v1/auth/register/complete",
        json={
            "registration_ticket": ticket,
            "username": "CharlieBrown",
            "display_name": "Charlie B",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["user"]["username"] == "CharlieBrown"

    # Attempt to register another account with username differing ONLY in case ("charliebrown")
    email_diff = "diff@example.com"
    db_session.add(
        VerificationChallenge(
            email=email_diff,
            hashed_code=hash_otp_code(code),
            purpose="registration",
            expires_at=utc_now() + timedelta(minutes=10),
        )
    )
    await db_session.commit()
    v_resp2 = await client.post("/api/v1/auth/register/verify-code", json={"email": email_diff, "code": code})
    ticket2 = v_resp2.json()["registration_ticket"]

    resp_duplicate = await client.post(
        "/api/v1/auth/register/complete",
        json={
            "registration_ticket": ticket2,
            "username": "charliebrown",  # Lowercase version of CharlieBrown
        },
    )
    assert resp_duplicate.status_code == 409
    assert resp_duplicate.json()["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_login_flow_and_token_refresh_rotation(client: AsyncClient, test_user: User, db_session: AsyncSession):
    rate_limiter._records.clear()
    code = "112233"
    db_session.add(
        VerificationChallenge(
            email=test_user.email,
            hashed_code=hash_otp_code(code),
            purpose="login",
            expires_at=utc_now() + timedelta(minutes=10),
        )
    )
    await db_session.commit()

    # Login verify
    login_resp = await client.post("/api/v1/auth/login/verify-code", json={"email": test_user.email, "code": code})
    assert login_resp.status_code == 200
    tokens = login_resp.json()
    old_refresh = tokens["refresh_token"]
    assert old_refresh

    # Rotate refresh token
    refresh_resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert refresh_resp.status_code == 200
    new_tokens = refresh_resp.json()
    new_refresh = new_tokens["refresh_token"]
    assert new_refresh != old_refresh

    # Old refresh token is revoked and cannot be reused
    reuse_resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert reuse_resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_session_invalidation(client: AsyncClient, test_user: User, db_session: AsyncSession):
    rate_limiter._records.clear()
    code = "445566"
    db_session.add(
        VerificationChallenge(
            email=test_user.email,
            hashed_code=hash_otp_code(code),
            purpose="login",
            expires_at=utc_now() + timedelta(minutes=10),
        )
    )
    await db_session.commit()

    login_resp = await client.post("/api/v1/auth/login/verify-code", json={"email": test_user.email, "code": code})
    refresh_token = login_resp.json()["refresh_token"]

    logout_resp = await client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    assert logout_resp.status_code == 200

    # Token cannot be used after logout
    refresh_resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_resp.status_code == 401


@pytest.mark.asyncio
async def test_login_flow_unregistered_email_fails(client: AsyncClient):
    """An unregistered email cannot authenticate through the login flow."""
    rate_limiter._records.clear()
    resp = await client.post("/api/v1/auth/login/request-code", json={"email": "nonexistent_user@example.com"})
    assert resp.status_code == 404
    data = resp.json()
    assert data["code"] == "NOT_FOUND"
    assert "No account found" in data["message"]
    assert "Please register first" in data["message"]


@pytest.mark.asyncio
async def test_email_sender_separate_from_recipient_and_payload_formatting():
    """Verify sender identity is isolated from recipient and handles public webmail via reply-to for Resend."""
    from unittest.mock import AsyncMock
    from app.core.errors import BadRequestError
    from app.providers.email_provider import EmailProvider

    mock_client = AsyncMock()
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "msg_12345"}
    mock_client.post.return_value = mock_resp

    provider = EmailProvider(client=mock_client, provider_type="resend")
    recipient = "newuser_recipient@company.com"
    success = await provider.send_verification_email(recipient, "123456", "registration")
    assert success is True

    # Verify call payload
    mock_client.post.assert_called_once()
    call_kwargs = mock_client.post.call_args.kwargs
    payload = call_kwargs["json"]

    assert payload["to"] == [recipient]
    assert "onboarding@resend.dev" in payload["from"]
    assert payload["reply_to"] == settings.RESEND_FROM_EMAIL or "@" in payload.get("reply_to", "")


@pytest.mark.asyncio
async def test_resend_delivery_failure_surfaced_accurately():
    """Verify Resend delivery failures are surfaced as clear BadRequestError exceptions."""
    from unittest.mock import AsyncMock
    from app.core.errors import BadRequestError
    from app.providers.email_provider import EmailProvider

    mock_client = AsyncMock()
    mock_resp = AsyncMock()
    mock_resp.status_code = 403
    mock_resp.json.return_value = {
        "message": "You can only send testing emails to your own email address."
    }
    mock_client.post.return_value = mock_resp

    provider = EmailProvider(client=mock_client, provider_type="resend")
    with pytest.raises(BadRequestError) as exc_info:
        await provider.send_verification_email("unverified@external.com", "654321", "registration")

    assert "Email sending failed (Resend)" in str(exc_info.value)
    assert "You can only send testing emails to your own email address" in str(exc_info.value)


@pytest.mark.asyncio
async def test_brevo_successful_delivery_mocked():
    """Verify Brevo transactional email delivery format, endpoint, headers, and payload."""
    from unittest.mock import AsyncMock
    from app.providers.email_provider import EmailProvider

    mock_client = AsyncMock()
    mock_resp = AsyncMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"messageId": "<brevo_test_12345@smtp-relay.mailin.fr>"}
    mock_client.post.return_value = mock_resp

    provider = EmailProvider(client=mock_client, provider_type="brevo")
    recipient = "brevo_recipient@company.com"
    success = await provider.send_verification_email(recipient, "789012", "account registration")
    assert success is True

    # Verify Brevo HTTPS endpoint
    mock_client.post.assert_called_once()
    call_args, call_kwargs = mock_client.post.call_args
    assert call_args[0] == "https://api.brevo.com/v3/smtp/email"

    # Verify Brevo headers
    headers = call_kwargs["headers"]
    assert "api-key" in headers
    assert headers["Content-Type"] == "application/json"
    assert headers["Accept"] == "application/json"

    # Verify Brevo payload structure
    payload = call_kwargs["json"]
    assert payload["sender"]["email"] == settings.BREVO_FROM_EMAIL
    assert payload["sender"]["name"] == (settings.BREVO_FROM_NAME or settings.APP_NAME)
    assert payload["to"] == [{"email": recipient}]
    assert "Verification Code" in payload["subject"]
    assert "789012" in payload["htmlContent"]
    assert "789012" in payload["textContent"]


@pytest.mark.asyncio
async def test_brevo_delivery_error_surfaced_accurately():
    """Verify Brevo API errors are captured and raised as BadRequestError."""
    from unittest.mock import AsyncMock
    from app.core.errors import BadRequestError
    from app.providers.email_provider import EmailProvider

    mock_client = AsyncMock()
    mock_resp = AsyncMock()
    mock_resp.status_code = 401
    mock_resp.json.return_value = {
        "code": "unauthorized",
        "message": "Key not found",
    }
    mock_client.post.return_value = mock_resp

    provider = EmailProvider(client=mock_client, provider_type="brevo")
    with pytest.raises(BadRequestError) as exc_info:
        await provider.send_verification_email("someone@external.com", "123456", "login")

    assert "Email sending failed (Brevo)" in str(exc_info.value)
    assert "Key not found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_brevo_unverified_sender_error():
    """Verify Brevo unverified sender error is reported with provider details."""
    from unittest.mock import AsyncMock
    from app.core.errors import BadRequestError
    from app.providers.email_provider import EmailProvider

    mock_client = AsyncMock()
    mock_resp = AsyncMock()
    mock_resp.status_code = 400
    mock_resp.json.return_value = {
        "code": "invalid_parameter",
        "message": "Sender is not valid or domain is unverified",
    }
    mock_client.post.return_value = mock_resp

    provider = EmailProvider(client=mock_client, provider_type="brevo")
    with pytest.raises(BadRequestError) as exc_info:
        await provider.send_verification_email("someone@external.com", "123456", "login")

    assert "Email sending failed (Brevo)" in str(exc_info.value)
    assert "Sender is not valid" in str(exc_info.value)


@pytest.mark.asyncio
async def test_brevo_timeout_error_handling():
    """Verify Brevo timeouts are caught and converted to friendly BadRequestError."""
    from unittest.mock import AsyncMock, patch
    import httpx
    from app.core.errors import BadRequestError
    from app.providers.email_provider import EmailProvider

    mock_client = AsyncMock()
    mock_client.post.side_effect = httpx.TimeoutException("Connection timed out after 10s")

    provider = EmailProvider(client=mock_client, provider_type="brevo")
    with pytest.raises(BadRequestError) as exc_info:
        await provider.send_verification_email("user@example.com", "112233", "login")

    assert "timeout" in str(exc_info.value).lower()
    assert "Brevo" in str(exc_info.value)


@pytest.mark.asyncio
async def test_brevo_missing_configuration_raises_error():
    """Verify unconfigured Brevo raises clear configuration error."""
    from unittest.mock import patch
    from app.core.config import Settings
    from app.core.errors import BadRequestError
    from app.providers.email_provider import EmailProvider

    provider = EmailProvider(provider_type="brevo")
    with patch.object(Settings, "is_provider_configured", return_value=False):
        with pytest.raises(BadRequestError) as exc_info:
            await provider.send_verification_email("user@somewhere.com", "112233", "login")

    assert "Brevo email service is not configured" in str(exc_info.value)


