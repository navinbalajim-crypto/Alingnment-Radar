"""Tests for group administration and role management."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.group import CreateGroupRequest
from app.services.group_service import GroupService


@pytest.fixture
async def group_with_members(db_session: AsyncSession, test_user: User, test_user_b: User):
    group_service = GroupService(db_session)
    group_detail = await group_service.create_group(
        creator_id=test_user.id,
        group_in=CreateGroupRequest(title="Radar Core Team", initial_member_usernames=[test_user_b.username]),
    )
    await db_session.commit()
    return group_detail


@pytest.mark.asyncio
async def test_admin_promotes_member_to_admin(
    client: AsyncClient, group_with_members, test_user_b: User, auth_headers: dict
):
    group_id = group_with_members.id

    # Alice (admin) promotes Bob
    res = await client.post(
        f"/api/v1/groups/{group_id}/members/{test_user_b.id}/promote",
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["role"] == "admin"

    # Verify membership list reflects admin role
    members_res = await client.get(f"/api/v1/groups/{group_id}/members", headers=auth_headers)
    assert members_res.status_code == 200
    bob_record = next(m for m in members_res.json() if m["user_id"] == str(test_user_b.id))
    assert bob_record["role"] == "admin"


@pytest.mark.asyncio
async def test_regular_member_cannot_promote_or_remove(
    client: AsyncClient, group_with_members, test_user: User, auth_headers_b: dict
):
    group_id = group_with_members.id

    # Bob is currently regular member; attempts to promote Alice -> 403 Forbidden
    res = await client.post(
        f"/api/v1/groups/{group_id}/members/{test_user.id}/promote",
        headers=auth_headers_b,
    )
    assert res.status_code == 403

    # Bob attempts to remove Alice -> 403 Forbidden
    res_rem = await client.delete(
        f"/api/v1/groups/{group_id}/members/{test_user.id}",
        headers=auth_headers_b,
    )
    assert res_rem.status_code == 403


@pytest.mark.asyncio
async def test_admin_removes_member_and_revokes_access(
    client: AsyncClient, group_with_members, test_user_b: User, auth_headers: dict, auth_headers_b: dict
):
    group_id = group_with_members.id

    # Alice removes Bob
    res = await client.delete(
        f"/api/v1/groups/{group_id}/members/{test_user_b.id}",
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert "Member removed" in res.json()["message"]

    # Bob can no longer access group messages -> 403 Forbidden
    bob_hist = await client.get(f"/api/v1/conversations/{group_id}/messages", headers=auth_headers_b)
    assert bob_hist.status_code == 403


@pytest.mark.asyncio
async def test_last_admin_protection(
    client: AsyncClient, group_with_members, test_user: User, auth_headers: dict
):
    group_id = group_with_members.id

    # Attempting to remove Alice (the only admin) -> 400 Bad Request
    res = await client.delete(
        f"/api/v1/groups/{group_id}/members/{test_user.id}",
        headers=auth_headers,
    )
    assert res.status_code == 400

    # Attempting to leave as the last admin -> 400 Bad Request
    res_leave = await client.post(
        f"/api/v1/groups/{group_id}/leave",
        headers=auth_headers,
    )
    assert res_leave.status_code == 400
    assert "last group admin" in res_leave.json()["message"]
