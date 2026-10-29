"""Tests for profile picture (avatar) upload, retrieval, fallback, and access control."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.user import User
from app.services.avatar_service import AVATAR_DIR, MAX_AVATAR_SIZE

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200


@pytest.fixture(autouse=True)
def _clean_avatar_dir():
    yield
    if AVATAR_DIR.exists():
        for f in AVATAR_DIR.iterdir():
            f.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_user_with_avatar_sees_it_in_profile(client: AsyncClient, auth_headers: dict):
    files = {"file": ("me.png", PNG_BYTES, "image/png")}
    res = await client.post("/api/v1/users/me/avatar", files=files, headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["avatar_url"].startswith(f"/api/v1/users/{body['id']}/avatar?v=")

    me = await client.get("/api/v1/users/me", headers=auth_headers)
    assert me.json()["avatar_url"] == body["avatar_url"]


@pytest.mark.asyncio
async def test_authorized_participant_can_fetch_another_users_avatar(client: AsyncClient, test_user: User, auth_headers: dict, auth_headers_b: dict):
    files = {"file": ("me.png", PNG_BYTES, "image/png")}
    await client.post("/api/v1/users/me/avatar", files=files, headers=auth_headers)

    res = await client.get(f"/api/v1/users/{test_user.id}/avatar", headers=auth_headers_b)
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content == PNG_BYTES


@pytest.mark.asyncio
async def test_user_without_avatar_has_no_avatar_url_and_fetch_404s(client: AsyncClient, test_user: User, auth_headers: dict):
    me = await client.get("/api/v1/users/me", headers=auth_headers)
    assert me.json()["avatar_url"] is None

    res = await client.get(f"/api/v1/users/{test_user.id}/avatar", headers=auth_headers)
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_updating_avatar_replaces_the_previous_image(client: AsyncClient, auth_headers: dict):
    files1 = {"file": ("me.png", PNG_BYTES, "image/png")}
    await client.post("/api/v1/users/me/avatar", files=files1, headers=auth_headers)

    jpeg_bytes = b"\xff\xd8\xff" + b"\x00" * 200
    files2 = {"file": ("me2.jpg", jpeg_bytes, "image/jpeg")}
    res2 = await client.post("/api/v1/users/me/avatar", files=files2, headers=auth_headers)
    assert res2.status_code == 200

    me = await client.get("/api/v1/users/me", headers=auth_headers)
    user_id = me.json()["id"]
    fetched = await client.get(f"/api/v1/users/{user_id}/avatar", headers=auth_headers)
    assert fetched.headers["content-type"] == "image/jpeg"
    assert fetched.content == jpeg_bytes
    # Only one file remains on disk for this user (the old PNG was removed).
    assert len(list(AVATAR_DIR.glob(f"{user_id.replace('-', '')}.*"))) == 1


@pytest.mark.asyncio
async def test_invalid_file_type_is_rejected_and_existing_avatar_preserved(client: AsyncClient, auth_headers: dict):
    files1 = {"file": ("me.png", PNG_BYTES, "image/png")}
    await client.post("/api/v1/users/me/avatar", files=files1, headers=auth_headers)

    bad_files = {"file": ("evil.exe", b"MZ" + b"\x00" * 50, "application/octet-stream")}
    res = await client.post("/api/v1/users/me/avatar", files=bad_files, headers=auth_headers)
    assert res.status_code == 400

    me = await client.get("/api/v1/users/me", headers=auth_headers)
    user_id = me.json()["id"]
    assert me.json()["avatar_url"].startswith(f"/api/v1/users/{user_id}/avatar?v=")
    fetched = await client.get(f"/api/v1/users/{user_id}/avatar", headers=auth_headers)
    assert fetched.content == PNG_BYTES  # Original avatar still intact


@pytest.mark.asyncio
async def test_mismatched_signature_is_rejected(client: AsyncClient, auth_headers: dict):
    fake_png = {"file": ("fake.png", b"not a real png" + b"\x00" * 50, "image/png")}
    res = await client.post("/api/v1/users/me/avatar", files=fake_png, headers=auth_headers)
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_oversized_avatar_is_rejected(client: AsyncClient, auth_headers: dict):
    big = b"\x89PNG\r\n\x1a\n" + (b"\x00" * (MAX_AVATAR_SIZE + 1))
    files = {"file": ("big.png", big, "image/png")}
    res = await client.post("/api/v1/users/me/avatar", files=files, headers=auth_headers)
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_unauthenticated_request_cannot_upload_or_fetch_avatar(client: AsyncClient, test_user: User):
    files = {"file": ("me.png", PNG_BYTES, "image/png")}
    res = await client.post("/api/v1/users/me/avatar", files=files)
    assert res.status_code in (401, 403)

    res2 = await client.get(f"/api/v1/users/{test_user.id}/avatar")
    assert res2.status_code in (401, 403)


@pytest.mark.asyncio
async def test_reupload_changes_the_avatar_url_so_clients_never_see_a_stale_cached_image(
    client: AsyncClient, auth_headers: dict
):
    """Regression: avatar_url must change on every re-upload. Otherwise browsers that already
    cached the old image at this exact URL keep showing it after a replace."""
    import asyncio

    files1 = {"file": ("me.png", PNG_BYTES, "image/png")}
    res1 = await client.post("/api/v1/users/me/avatar", files=files1, headers=auth_headers)
    url1 = res1.json()["avatar_url"]

    await asyncio.sleep(1.05)  # version is second-resolution; ensure a distinct timestamp

    files2 = {"file": ("me.png", PNG_BYTES, "image/png")}
    res2 = await client.post("/api/v1/users/me/avatar", files=files2, headers=auth_headers)
    url2 = res2.json()["avatar_url"]

    assert url1 != url2


@pytest.mark.asyncio
async def test_user_cannot_set_another_users_avatar_via_their_own_token(client: AsyncClient, test_user: User, test_user_b: User, auth_headers_b: dict):
    """The upload endpoint always targets the authenticated caller; there is no way for user B's
    token to modify user A's avatar."""
    files = {"file": ("me.png", PNG_BYTES, "image/png")}
    res = await client.post("/api/v1/users/me/avatar", files=files, headers=auth_headers_b)
    assert res.status_code == 200
    assert res.json()["id"] == str(test_user_b.id)
    assert res.json()["id"] != str(test_user.id)
