"""Tests for group display picture (DP) upload, retrieval, removal, isolation, and access
control. Mirrors tests/test_avatars.py (personal avatars) but for the group endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.group import CreateGroupRequest
from app.services.avatar_service import AVATAR_DIR, GROUP_AVATAR_DIR
from app.services.group_service import GroupService

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
JPEG_BYTES = b"\xff\xd8\xff" + b"\x00" * 200


@pytest.fixture(autouse=True)
def _clean_avatar_dirs():
    yield
    for d in (AVATAR_DIR, GROUP_AVATAR_DIR):
        if d.exists():
            for f in d.iterdir():
                f.unlink(missing_ok=True)


@pytest.fixture
async def group_with_members(db_session: AsyncSession, test_user: User, test_user_b: User):
    """test_user is the creator (admin); test_user_b is a regular member."""
    group_service = GroupService(db_session)
    group_detail = await group_service.create_group(
        creator_id=test_user.id,
        group_in=CreateGroupRequest(title="Radar Core Team", initial_member_usernames=[test_user_b.username]),
    )
    await db_session.commit()
    return group_detail


@pytest.mark.asyncio
async def test_admin_uploads_group_avatar_and_it_appears_in_group_detail(
    client: AsyncClient, group_with_members, auth_headers: dict
):
    group_id = group_with_members.id
    files = {"file": ("group.png", PNG_BYTES, "image/png")}
    res = await client.post(f"/api/v1/groups/{group_id}/avatar", files=files, headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["avatar_url"].startswith(f"/api/v1/groups/{group_id}/avatar?v=")

    detail = await client.get(f"/api/v1/groups/{group_id}", headers=auth_headers)
    assert detail.json()["avatar_url"] == body["avatar_url"]


@pytest.mark.asyncio
async def test_member_can_fetch_group_avatar_image(client: AsyncClient, group_with_members, auth_headers: dict, auth_headers_b: dict):
    group_id = group_with_members.id
    files = {"file": ("group.png", PNG_BYTES, "image/png")}
    await client.post(f"/api/v1/groups/{group_id}/avatar", files=files, headers=auth_headers)

    # test_user_b is a regular (non-admin) member -- can still view it.
    res = await client.get(f"/api/v1/groups/{group_id}/avatar", headers=auth_headers_b)
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content == PNG_BYTES


@pytest.mark.asyncio
async def test_non_member_cannot_fetch_group_avatar(client: AsyncClient, group_with_members, auth_headers: dict, db_session: AsyncSession):
    from app.models.user import User as UserModel

    group_id = group_with_members.id
    files = {"file": ("group.png", PNG_BYTES, "image/png")}
    await client.post(f"/api/v1/groups/{group_id}/avatar", files=files, headers=auth_headers)

    outsider = UserModel(email="outsider_grp@example.com", username="outsider_grp", username_normalized="outsider_grp", display_name="Outsider", is_active=True)
    db_session.add(outsider)
    await db_session.commit()
    from app.core.security import create_access_token
    outsider_headers = {"Authorization": f"Bearer {create_access_token(user_id=str(outsider.id), username=outsider.username)}"}

    res = await client.get(f"/api/v1/groups/{group_id}/avatar", headers=outsider_headers)
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_regular_member_cannot_change_group_avatar(client: AsyncClient, group_with_members, auth_headers_b: dict):
    """test_user_b is a non-admin member; only admins may change the group photo."""
    group_id = group_with_members.id
    files = {"file": ("group.png", PNG_BYTES, "image/png")}
    res = await client.post(f"/api/v1/groups/{group_id}/avatar", files=files, headers=auth_headers_b)
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_non_member_cannot_change_group_avatar(client: AsyncClient, group_with_members, db_session: AsyncSession):
    from app.models.user import User as UserModel
    from app.core.security import create_access_token

    group_id = group_with_members.id
    outsider = UserModel(email="outsider2_grp@example.com", username="outsider2_grp", username_normalized="outsider2_grp", display_name="Outsider2", is_active=True)
    db_session.add(outsider)
    await db_session.commit()
    outsider_headers = {"Authorization": f"Bearer {create_access_token(user_id=str(outsider.id), username=outsider.username)}"}

    files = {"file": ("group.png", PNG_BYTES, "image/png")}
    res = await client.post(f"/api/v1/groups/{group_id}/avatar", files=files, headers=outsider_headers)
    assert res.status_code in (403, 404)


@pytest.mark.asyncio
async def test_updating_one_groups_avatar_does_not_affect_another_group(
    client: AsyncClient, db_session: AsyncSession, test_user: User, test_user_b: User, auth_headers: dict
):
    group_service = GroupService(db_session)
    group_a = await group_service.create_group(test_user.id, CreateGroupRequest(title="Group A"))
    group_b = await group_service.create_group(test_user.id, CreateGroupRequest(title="Group B"))
    await db_session.commit()

    files_a = {"file": ("a.png", PNG_BYTES, "image/png")}
    res_a = await client.post(f"/api/v1/groups/{group_a.id}/avatar", files=files_a, headers=auth_headers)
    assert res_a.status_code == 200

    # Group B must still have no custom avatar.
    detail_b = await client.get(f"/api/v1/groups/{group_b.id}", headers=auth_headers)
    assert detail_b.json()["avatar_url"] is None

    files_b = {"file": ("b.jpg", JPEG_BYTES, "image/jpeg")}
    res_b = await client.post(f"/api/v1/groups/{group_b.id}/avatar", files=files_b, headers=auth_headers)
    assert res_b.status_code == 200

    # Each group serves its own distinct image.
    fetched_a = await client.get(f"/api/v1/groups/{group_a.id}/avatar", headers=auth_headers)
    fetched_b = await client.get(f"/api/v1/groups/{group_b.id}/avatar", headers=auth_headers)
    assert fetched_a.content == PNG_BYTES
    assert fetched_b.content == JPEG_BYTES
    assert res_a.json()["avatar_url"] != res_b.json()["avatar_url"]


@pytest.mark.asyncio
async def test_setting_group_avatar_does_not_change_the_admins_personal_avatar(
    client: AsyncClient, group_with_members, auth_headers: dict
):
    group_id = group_with_members.id

    me_before = await client.get("/api/v1/users/me", headers=auth_headers)
    assert me_before.json()["avatar_url"] is None

    files = {"file": ("group.png", PNG_BYTES, "image/png")}
    await client.post(f"/api/v1/groups/{group_id}/avatar", files=files, headers=auth_headers)

    me_after = await client.get("/api/v1/users/me", headers=auth_headers)
    assert me_after.json()["avatar_url"] is None  # still untouched


@pytest.mark.asyncio
async def test_setting_personal_avatar_does_not_change_group_avatar(
    client: AsyncClient, group_with_members, auth_headers: dict
):
    group_id = group_with_members.id
    files = {"file": ("group.png", PNG_BYTES, "image/png")}
    group_res = await client.post(f"/api/v1/groups/{group_id}/avatar", files=files, headers=auth_headers)
    group_avatar_url = group_res.json()["avatar_url"]

    personal_files = {"file": ("me.jpg", JPEG_BYTES, "image/jpeg")}
    await client.post("/api/v1/users/me/avatar", files=personal_files, headers=auth_headers)

    detail = await client.get(f"/api/v1/groups/{group_id}", headers=auth_headers)
    assert detail.json()["avatar_url"] == group_avatar_url


@pytest.mark.asyncio
async def test_admin_removes_group_avatar_restoring_default(client: AsyncClient, group_with_members, auth_headers: dict):
    group_id = group_with_members.id
    files = {"file": ("group.png", PNG_BYTES, "image/png")}
    await client.post(f"/api/v1/groups/{group_id}/avatar", files=files, headers=auth_headers)

    res = await client.delete(f"/api/v1/groups/{group_id}/avatar", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["avatar_url"] is None

    fetch = await client.get(f"/api/v1/groups/{group_id}/avatar", headers=auth_headers)
    assert fetch.status_code == 404


@pytest.mark.asyncio
async def test_removing_group_avatar_is_a_no_op_when_no_custom_avatar_exists(client: AsyncClient, group_with_members, auth_headers: dict):
    group_id = group_with_members.id
    res = await client.delete(f"/api/v1/groups/{group_id}/avatar", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["avatar_url"] is None


@pytest.mark.asyncio
async def test_regular_member_cannot_remove_group_avatar(client: AsyncClient, group_with_members, auth_headers: dict, auth_headers_b: dict):
    group_id = group_with_members.id
    files = {"file": ("group.png", PNG_BYTES, "image/png")}
    await client.post(f"/api/v1/groups/{group_id}/avatar", files=files, headers=auth_headers)

    res = await client.delete(f"/api/v1/groups/{group_id}/avatar", headers=auth_headers_b)
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_invalid_file_type_rejected_and_existing_group_avatar_preserved(client: AsyncClient, group_with_members, auth_headers: dict):
    group_id = group_with_members.id
    files = {"file": ("group.png", PNG_BYTES, "image/png")}
    await client.post(f"/api/v1/groups/{group_id}/avatar", files=files, headers=auth_headers)

    bad_files = {"file": ("evil.exe", b"MZ" + b"\x00" * 50, "application/octet-stream")}
    res = await client.post(f"/api/v1/groups/{group_id}/avatar", files=bad_files, headers=auth_headers)
    assert res.status_code == 400

    fetch = await client.get(f"/api/v1/groups/{group_id}/avatar", headers=auth_headers)
    assert fetch.content == PNG_BYTES  # original preserved


@pytest.mark.asyncio
async def test_oversized_group_avatar_rejected(client: AsyncClient, group_with_members, auth_headers: dict):
    from app.services.avatar_service import MAX_AVATAR_SIZE

    big = b"\x89PNG\r\n\x1a\n" + (b"\x00" * (MAX_AVATAR_SIZE + 1))
    files = {"file": ("big.png", big, "image/png")}
    res = await client.post(f"/api/v1/groups/{group_with_members.id}/avatar", files=files, headers=auth_headers)
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_direct_conversation_has_no_group_avatar_field_populated(
    client: AsyncClient, test_user: User, test_user_b: User, auth_headers: dict
):
    """Direct chats use the other participant's personal avatar; conversation.avatar_url must
    stay null for them even if somehow set at the model level."""
    res = await client.post(
        f"/api/v1/conversations/direct/{test_user_b.username}",
        headers=auth_headers,
    )
    assert res.status_code in (200, 201)
    assert res.json()["avatar_url"] is None


@pytest.mark.asyncio
async def test_existing_group_endpoints_still_work_after_avatar_changes(client: AsyncClient, group_with_members, test_user_b: User, auth_headers: dict):
    """Regression: the new avatar fields/endpoints must not break existing group management."""
    group_id = group_with_members.id
    members = await client.get(f"/api/v1/groups/{group_id}/members", headers=auth_headers)
    assert members.status_code == 200
    assert len(members.json()) == 2

    promote = await client.post(f"/api/v1/groups/{group_id}/members/{test_user_b.id}/promote", headers=auth_headers)
    assert promote.status_code == 200
