"""Automated tests for user discovery, search, and profile operations."""

import pytest
from httpx import AsyncClient
from app.models.user import User


@pytest.mark.asyncio
async def test_get_current_user_profile(client: AsyncClient, test_user: User, auth_headers: dict[str, str]):
    resp = await client.get("/api/v1/users/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == test_user.email
    assert data["username"] == test_user.username
    assert data["display_name"] == test_user.display_name


@pytest.mark.asyncio
async def test_user_search_excludes_self_and_hides_private_data(
    client: AsyncClient, test_user: User, test_user_b: User, auth_headers: dict[str, str]
):
    # Searching for 'bob' as Alice
    resp = await client.get("/api/v1/users/search", params={"username": "bob"}, headers=auth_headers)
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    bob_public = results[0]
    assert bob_public["username"] == "bob"
    assert "email" not in bob_public  # Strict privacy: email never exposed

    # Searching for 'alice' as Alice -> must exclude self
    resp_self = await client.get("/api/v1/users/search", params={"username": "alice"}, headers=auth_headers)
    assert resp_self.status_code == 200
    self_results = resp_self.json()
    assert len(self_results) == 0


@pytest.mark.asyncio
async def test_username_availability(client: AsyncClient, test_user: User):
    # Taken username
    resp_taken = await client.get("/api/v1/users/username-availability", params={"username": "alice"})
    assert resp_taken.status_code == 200
    assert not resp_taken.json()["available"]

    # Available username
    resp_avail = await client.get("/api/v1/users/username-availability", params={"username": "brandnewuser"})
    assert resp_avail.status_code == 200
    assert resp_avail.json()["available"]

    # Invalid username format
    resp_invalid = await client.get("/api/v1/users/username-availability", params={"username": "a!"})
    assert resp_invalid.status_code == 200
    assert not resp_invalid.json()["available"]
