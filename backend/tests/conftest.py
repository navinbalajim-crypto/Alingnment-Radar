"""Pytest fixtures and configuration for automated test suite."""

import asyncio
from typing import AsyncGenerator
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import create_access_token, hash_otp_code
from app.db.base import Base
from app.db.session import get_db
from app.main import fastapi_app
from app.models.user import User

# Use in-memory SQLite database for test execution
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Ensure test suite runs deterministically with mocked providers without leaking to live third-party APIs
settings.GROQ_API_KEY = "xxx"
settings.AI_ROUTER_STRATEGY = "nvidia"

# Fake "configured" credentials so the suite behaves the same with or without a developer's backend/.env, and real
# keys from that file are never used. Every test mocks the HTTP calls these providers would make.
for _name, _value in {
    "NVIDIA_API_KEY": "test-nvidia-key",
    "NEBIUS_API_KEY": "test-nebius-key",
    "BREVO_API_KEY": "test-brevo-key",
    "BREVO_FROM_EMAIL": "sender@example.test",
    "EMAIL_PROVIDER": "brevo",
    "RESEND_API_KEY": "xxx",
    "YOUTUBE_DATA_API_KEY": "test-youtube-key",
    "SPOTIFY_CLIENT_ID": "test-spotify-id",
    "SPOTIFY_CLIENT_SECRET": "test-spotify-secret",
    "TAVILY_API_KEY": "test-tavily-key",
    "GOOGLE_CLIENT_ID": "test-client-id.apps.googleusercontent.com",
    "GOOGLE_CLIENT_SECRET": "test-google-secret",
    "NVIDIA_ASR_API_KEY": None,
    "NVIDIA_TRANSLATION_API_KEY": None,
}.items():
    setattr(settings, _name, _value)

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

TestAsyncSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create fresh schema for each test function and yield async session."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with TestAsyncSessionLocal() as session:
        yield session
        await session.rollback()

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Test HTTP client with overridden database dependency."""
    async def override_get_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    fastapi_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a verified test user."""
    user = User(
        email="alice@example.com",
        username="alice",
        username_normalized="alice",
        display_name="Alice Wonderland",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_user_b(db_session: AsyncSession) -> User:
    """Create a second verified test user."""
    user = User(
        email="bob@example.com",
        username="bob",
        username_normalized="bob",
        display_name="Bob Builder",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
def auth_headers(test_user: User) -> dict[str, str]:
    """Generate HTTP Authorization headers with valid JWT token for Alice."""
    token = create_access_token(user_id=str(test_user.id), username=test_user.username)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
def auth_headers_b(test_user_b: User) -> dict[str, str]:
    """Generate HTTP Authorization headers with valid JWT token for Bob."""
    token = create_access_token(user_id=str(test_user_b.id), username=test_user_b.username)
    return {"Authorization": f"Bearer {token}"}
