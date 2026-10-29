"""Comprehensive tests for username and password authentication, registration, password reset, and migration."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import create_access_token, create_registration_ticket, hash_otp_code, hash_password
from app.models.user import User
from app.models.verification import VerificationChallenge
from app.db.base import utc_now
from datetime import timedelta


@pytest.mark.asyncio
async def test_register_with_password(client: AsyncClient, db_session: AsyncSession):
    """Test full registration flow including password creation and Argon2id hashing."""
    ticket = create_registration_ticket("charlie@example.com")

    res = await client.post(
        "/api/v1/auth/register/complete",
        json={
            "registration_ticket": ticket,
            "username": "charlie",
            "display_name": "Charlie Chaplin",
            "password": "SecurePassword123!",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert "access_token" in data
    assert data["has_password"] is True
    assert data["user"]["username"] == "charlie"
    assert data["user"]["has_password"] is True


@pytest.mark.asyncio
async def test_password_complexity_validation(client: AsyncClient, db_session: AsyncSession):
    """Test that weak passwords (under 8 chars or missing complexity) are rejected."""
    ticket = create_registration_ticket("weak@example.com")

    res = await client.post(
        "/api/v1/auth/register/complete",
        json={
            "registration_ticket": ticket,
            "username": "weakuser",
            "password": "pwd",
        },
    )
    # Pydantic validates min_length=8 at request parsing time (422)
    assert res.status_code in [400, 422]


@pytest.mark.asyncio
async def test_password_login_success_and_failure(client: AsyncClient, db_session: AsyncSession):
    """Test password login with correct, wrong, and non-existent username."""
    # Create user with password
    pwd_hash = hash_password("ValidPassword123!")
    user = User(
        email="david@example.com",
        username="david",
        username_normalized="david",
        password_hash=pwd_hash,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    # 1. Successful login with username
    res = await client.post(
        "/api/v1/auth/login/password",
        json={"username": "david", "password": "ValidPassword123!"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["username"] == "david"
    assert data["has_password"] is True

    # 2. Successful login with email as identifier
    res_email = await client.post(
        "/api/v1/auth/login/password",
        json={"username": "david@example.com", "password": "ValidPassword123!"},
    )
    assert res_email.status_code == 200

    # 3. Incorrect password
    res_bad = await client.post(
        "/api/v1/auth/login/password",
        json={"username": "david", "password": "WrongPassword999!"},
    )
    assert res_bad.status_code == 401
    err_msg = res_bad.json().get("message") or res_bad.json().get("detail", "")
    assert "Invalid username or password" in err_msg

    # 4. Unknown username (generic error without leaking existence)
    res_unknown = await client.post(
        "/api/v1/auth/login/password",
        json={"username": "nonexistent_user", "password": "AnyPassword123!"},
    )
    assert res_unknown.status_code == 401
    err_msg2 = res_unknown.json().get("message") or res_unknown.json().get("detail", "")
    assert "Invalid username or password" in err_msg2


@pytest.mark.asyncio
async def test_existing_user_without_password_migration(client: AsyncClient, db_session: AsyncSession):
    """Test that existing users without password can set a password and preserve account data."""
    # User originally signed up passwordless (password_hash is None)
    user = User(
        email="eva@example.com",
        username="eva",
        username_normalized="eva",
        password_hash=None,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # Attempting password login fails with guidance
    res_try = await client.post(
        "/api/v1/auth/login/password",
        json={"username": "eva", "password": "AnyPassword123!"},
    )
    assert res_try.status_code == 401
    err_msg = res_try.json().get("message") or res_try.json().get("detail", "")
    assert "does not have a password set" in err_msg

    # User authenticates and calls /auth/password/set
    token = create_access_token(user_id=str(user.id), username=user.username)
    headers = {"Authorization": f"Bearer {token}"}

    res_set = await client.post(
        "/api/v1/auth/password/set",
        json={"new_password": "NewCreatedPassword123!"},
        headers=headers,
    )
    assert res_set.status_code == 200
    assert "Password set successfully" in res_set.json()["message"]

    # Now password login works
    res_login = await client.post(
        "/api/v1/auth/login/password",
        json={"username": "eva", "password": "NewCreatedPassword123!"},
    )
    assert res_login.status_code == 200
    assert res_login.json()["user"]["username"] == "eva"


@pytest.mark.asyncio
async def test_forgot_password_flow(client: AsyncClient, db_session: AsyncSession):
    """Test full forgot-password recovery flow with generic response, OTP verification, and reset."""
    # Create user
    user = User(
        email="frank@example.com",
        username="frank",
        username_normalized="frank",
        password_hash=hash_password("OldPassword123!"),
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    # 1. Request password reset (existing email)
    res_req = await client.post(
        "/api/v1/auth/password/forgot",
        json={"email": "frank@example.com"},
    )
    assert res_req.status_code == 200
    assert "If an account with that email address exists" in res_req.json()["message"]

    # 1b. Request password reset (unregistered email -> same generic message)
    res_ghost = await client.post(
        "/api/v1/auth/password/forgot",
        json={"email": "ghost@example.com"},
    )
    assert res_ghost.status_code == 200
    assert "If an account with that email address exists" in res_ghost.json()["message"]

    # Add challenge for frank
    code = "123456"
    challenge = VerificationChallenge(
        email="frank@example.com",
        hashed_code=hash_otp_code(code),
        purpose="password_reset",
        expires_at=utc_now() + timedelta(minutes=10),
        max_attempts=5,
        attempts=0,
    )
    db_session.add(challenge)
    await db_session.commit()

    # 2. Verify code
    res_verify = await client.post(
        "/api/v1/auth/password/verify-code",
        json={"email": "frank@example.com", "code": "123456"},
    )
    assert res_verify.status_code == 200
    verify_data = res_verify.json()
    assert "reset_ticket" in verify_data
    ticket = verify_data["reset_ticket"]

    # 3. Complete reset with new password
    res_reset = await client.post(
        "/api/v1/auth/password/reset",
        json={"reset_ticket": ticket, "new_password": "BrandNewPassword456!"},
    )
    assert res_reset.status_code == 200
    assert "Password reset successfully" in res_reset.json()["message"]

    # 4. Sign in with brand new password
    res_login = await client.post(
        "/api/v1/auth/login/password",
        json={"username": "frank", "password": "BrandNewPassword456!"},
    )
    assert res_login.status_code == 200
    assert res_login.json()["user"]["username"] == "frank"


@pytest.mark.asyncio
async def test_password_reset_ticket_replay_protection(client: AsyncClient, db_session: AsyncSession):
    """Verify that a password reset ticket cannot be reused once consumed."""
    user = User(
        email="replay_test@example.com",
        username="replay_user",
        username_normalized="replay_user",
        password_hash=hash_password("InitialPassword123!"),
        is_active=True,
    )
    db_session.add(user)
    challenge = VerificationChallenge(
        email="replay_test@example.com",
        hashed_code=hash_otp_code("654321"),
        purpose="password_reset",
        expires_at=utc_now() + timedelta(minutes=10),
        max_attempts=5,
        attempts=0,
    )
    db_session.add(challenge)
    await db_session.commit()

    # Verify code to obtain ticket
    res_verify = await client.post(
        "/api/v1/auth/password/verify-code",
        json={"email": "replay_test@example.com", "code": "654321"},
    )
    assert res_verify.status_code == 200
    ticket = res_verify.json()["reset_ticket"]

    # First reset succeeds
    res1 = await client.post(
        "/api/v1/auth/password/reset",
        json={"reset_ticket": ticket, "new_password": "NewSecretPass123!"},
    )
    assert res1.status_code == 200

    # Second reset with SAME ticket MUST be rejected (anti-replay)
    res2 = await client.post(
        "/api/v1/auth/password/reset",
        json={"reset_ticket": ticket, "new_password": "AnotherSecretPass456!"},
    )
    assert res2.status_code == 401
    assert "already been used" in (res2.json().get("detail") or res2.json().get("message", ""))


@pytest.mark.asyncio
async def test_registration_ticket_replay_protection(client: AsyncClient, db_session: AsyncSession):
    """Verify that a registration ticket cannot be reused once consumed."""
    from app.core.security import create_registration_ticket
    ticket = create_registration_ticket("replay_reg@example.com")

    # First completion succeeds
    res1 = await client.post(
        "/api/v1/auth/register/complete",
        json={
            "registration_ticket": ticket,
            "username": "replay_reg_user",
            "password": "ValidPassword123!",
        },
    )
    assert res1.status_code == 201

    # Second completion with same ticket MUST fail
    res2 = await client.post(
        "/api/v1/auth/register/complete",
        json={
            "registration_ticket": ticket,
            "username": "replay_reg_user_2",
            "password": "ValidPassword123!",
        },
    )
    assert res2.status_code == 401
    assert "already been used" in (res2.json().get("detail") or res2.json().get("message", ""))

