"""Automated tests for group creation, administration, and secure invitation onboarding."""

from datetime import timedelta
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import hash_otp_code, rate_limiter
from app.db.base import utc_now
from app.models.user import User
from app.models.verification import VerificationChallenge


@pytest.mark.asyncio
async def test_group_creation_and_admin_assignment(
    client: AsyncClient, test_user: User, test_user_b: User, auth_headers: dict[str, str]
):
    # Alice creates a group with initial member Bob
    resp = await client.post(
        "/api/v1/groups",
        json={
            "title": "Backend Architecture Team",
            "initial_member_usernames": [test_user_b.username],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    group_data = resp.json()
    assert group_data["title"] == "Backend Architecture Team"
    assert len(group_data["members"]) == 2

    # Verify Alice is admin
    alice_member = next(m for m in group_data["members"] if m["username"] == test_user.username)
    assert alice_member["role"] == "admin"

    # Verify Bob is member
    bob_member = next(m for m in group_data["members"] if m["username"] == test_user_b.username)
    assert bob_member["role"] == "member"


@pytest.mark.asyncio
async def test_group_invitation_creation_and_admin_auth(
    client: AsyncClient, test_user: User, test_user_b: User, auth_headers: dict[str, str], auth_headers_b: dict[str, str]
):
    # 1. Create group with Alice as admin, Bob as member
    create_resp = await client.post(
        "/api/v1/groups",
        json={"title": "Security Taskforce", "initial_member_usernames": [test_user_b.username]},
        headers=auth_headers,
    )
    group_id = create_resp.json()["id"]

    # 2. Alice (admin) creates invitation
    invite_resp = await client.post(
        f"/api/v1/groups/{group_id}/invitations",
        json={"max_uses": 5, "expires_in_days": 3},
        headers=auth_headers,
    )
    assert invite_resp.status_code == 201
    invitation = invite_resp.json()
    assert invitation["token"]
    assert "invitations/" in invitation["invitation_url"]
    token = invitation["token"]

    # 3. Bob (regular member, not admin) attempts to create invitation -> 403 Forbidden
    resp_forbidden = await client.post(
        f"/api/v1/groups/{group_id}/invitations",
        json={"max_uses": 1},
        headers=auth_headers_b,
    )
    assert resp_forbidden.status_code == 403

    # 4. Preview invitation anonymously
    preview_resp = await client.get(f"/api/v1/invitations/{token}")
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    assert preview["group_title"] == "Security Taskforce"
    assert preview["is_valid"]


@pytest.mark.asyncio
async def test_invitation_join_existing_user(
    client: AsyncClient, test_user: User, test_user_b: User, auth_headers: dict[str, str], db_session: AsyncSession
):
    rate_limiter._records.clear()
    # Alice creates group
    group_resp = await client.post("/api/v1/groups", json={"title": "DevOps Channel"}, headers=auth_headers)
    group_id = group_resp.json()["id"]

    # Alice creates invitation
    inv_resp = await client.post(f"/api/v1/groups/{group_id}/invitations", json={}, headers=auth_headers)
    token = inv_resp.json()["token"]

    # Bob requests code to join via invitation
    req_resp = await client.post(f"/api/v1/invitations/{token}/request-code", json={"email": test_user_b.email})
    assert req_resp.status_code == 200

    # Update challenge with known code for verification
    code = "778899"
    stmt = select(VerificationChallenge).where(
        VerificationChallenge.email == test_user_b.email,
        VerificationChallenge.purpose == "invitation",
    )
    challenge = (await db_session.execute(stmt)).scalars().first()
    challenge.hashed_code = hash_otp_code(code)
    await db_session.commit()

    # Bob verifies code
    verify_resp = await client.post(
        f"/api/v1/invitations/{token}/verify-code",
        json={"email": test_user_b.email, "code": code},
    )
    assert verify_resp.status_code == 200
    join_data = verify_resp.json()
    assert join_data["is_existing_user"]
    assert join_data["tokens"]["access_token"]

    # Check that Bob is now in members list
    members_resp = await client.get(f"/api/v1/groups/{group_id}/members", headers=auth_headers)
    member_usernames = [m["username"] for m in members_resp.json()]
    assert test_user_b.username in member_usernames


@pytest.mark.asyncio
async def test_invitation_join_new_user_registration(
    client: AsyncClient, test_user: User, auth_headers: dict[str, str], db_session: AsyncSession
):
    rate_limiter._records.clear()
    # Alice creates group & invitation
    g_resp = await client.post("/api/v1/groups", json={"title": "Design Team"}, headers=auth_headers)
    group_id = g_resp.json()["id"]
    inv_resp = await client.post(f"/api/v1/groups/{group_id}/invitations", json={}, headers=auth_headers)
    token = inv_resp.json()["token"]

    new_email = "brandnewinvitee@example.com"
    req_resp = await client.post(f"/api/v1/invitations/{token}/request-code", json={"email": new_email})
    assert req_resp.status_code == 200

    code = "889900"
    stmt = select(VerificationChallenge).where(
        VerificationChallenge.email == new_email,
        VerificationChallenge.purpose == "invitation",
    )
    challenge = (await db_session.execute(stmt)).scalars().first()
    challenge.hashed_code = hash_otp_code(code)
    await db_session.commit()

    # Verify code as new user -> returns registration ticket
    v_resp = await client.post(f"/api/v1/invitations/{token}/verify-code", json={"email": new_email, "code": code})
    assert v_resp.status_code == 200
    v_data = v_resp.json()
    assert not v_data["is_existing_user"]
    reg_ticket = v_data["registration_ticket"]
    assert reg_ticket

    # Complete onboarding
    complete_resp = await client.post(
        f"/api/v1/invitations/{token}/complete-registration",
        json={
            "registration_ticket": reg_ticket,
            "username": "diana_prince",
            "display_name": "Diana",
        },
    )
    assert complete_resp.status_code == 201
    tokens = complete_resp.json()
    assert tokens["access_token"]
    assert tokens["user"]["username"] == "diana_prince"

    # Verify membership
    m_resp = await client.get(f"/api/v1/groups/{group_id}/members", headers=auth_headers)
    usernames = [m["username"] for m in m_resp.json()]
    assert "diana_prince" in usernames
