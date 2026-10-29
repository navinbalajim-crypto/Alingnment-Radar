# Alignment Radar: Backend Architecture & Production Guide

Alignment Radar is an AI-powered, real-time messaging application backend designed for mission-critical conversations. It features passwordless email-based authentication, unique username discovery, private direct chats, group channels with cryptographically secure invitations, real-time Socket.IO communication, AI-driven misalignment/misunderstanding detection powered by NVIDIA NIM (Nemotron), and contextual recommendations (Tamil songs, music, cricket, web news) from verified external providers (YouTube Data API v3, Spotify Web API, Tavily Search API).

---

## 1. Technology Stack

- **Runtime**: Python 3.11+ (Validated on Python 3.13)
- **REST Framework**: [FastAPI](https://fastapi.tiangolo.com/) (v0.115+)
- **Real-Time Communication**: [python-socketio](https://python-socketio.readthedocs.io/) (`AsyncServer` in ASGI mode)
- **ASGI Server**: [Uvicorn](https://www.uvicorn.org/)
- **Database**: [SQLAlchemy 2.x](https://www.sqlalchemy.org/) Async ORM. The default configuration in `.env.example` is SQLite (`aiosqlite`), which is what the test suite and migration checks cover. PostgreSQL (`asyncpg`) is supported by the code but has not been re-verified for this release.
- **Database Migrations**: [Alembic](https://alembic.sqlalchemy.org/)
- **Configuration & Validation**: [Pydantic v2](https://docs.pydantic.dev/) and `pydantic-settings`
- **Security & Cryptography**: PyJWT (HMAC-SHA256), cryptographic salt/HMAC for OTPs, SHA-256 token hashing
- **HTTP Client**: [HTTPX](https://www.python-httpx.org/) (Async)
- **Email Delivery**: Resend API
- **AI Inference**: NVIDIA NIM with configured Nemotron model
- **Contextual Search**: YouTube Data API v3, Spotify Web API (Client-Credentials flow), Tavily Search API
- **Automated Testing**: Pytest, pytest-asyncio, pytest-cov

---

## 2. Directory Structure

```text
backend/
├── alembic/
│   ├── env.py                             # Async migration environment
│   ├── script.py.mako                     # Migration revision template
│   └── versions/
│       └── 20261017_0001_initial_schema.py # Initial database migration (all 9 tables)
├── app/
│   ├── api/
│   │   ├── deps.py                        # FastAPI dependencies (auth, db)
│   │   └── v1/
│   │       ├── ai.py                      # AI findings & link share routes
│   │       ├── auth.py                    # Passwordless login & registration
│   │       ├── conversations.py           # 1-to-1 chats & message history
│   │       ├── groups.py                  # Group creation & admin controls
│   │       ├── health.py                  # Liveness & readiness probes
│   │       ├── invitations.py             # Public invitation previews & verified joins
│   │       └── users.py                   # Discovery, search, and availability
│   ├── core/
│   │   ├── config.py                      # Pydantic Settings with startup verification
│   │   ├── errors.py                      # Standardized application exception hierarchy
│   │   ├── logging.py                     # Redacting logger for sensitive data (tokens/OTPs)
│   │   └── security.py                    # Token issuance, OTP generation, HMAC hashing, rate limiter
│   ├── db/
│   │   ├── base.py                        # SQLAlchemy DeclarativeBase & UTC utilities
│   │   └── session.py                     # Async engine & session factory
│   ├── models/
│   │   ├── alignment.py                   # AlignmentFinding entity
│   │   ├── conversation.py                # Conversation & ConversationMember entities
│   │   ├── invitation.py                  # GroupInvitation entity
│   │   ├── message.py                     # Message entity with client_id idempotency
│   │   ├── recommendation.py              # RecommendationItem entity
│   │   ├── session.py                     # RefreshSession entity
│   │   ├── user.py                        # User entity with normalized username index
│   │   └── verification.py                # VerificationChallenge entity
│   ├── providers/
│   │   ├── email_provider.py              # Resend API integration
│   │   ├── nvidia_provider.py             # NVIDIA NIM Nemotron inference & intent extractor
│   │   ├── spotify_provider.py            # Spotify Client Credentials track search
│   │   ├── tavily_provider.py             # Tavily real-time search & cricket context
│   │   └── youtube_provider.py            # YouTube Data API v3 video search
│   ├── repositories/
│   │   ├── ai_repo.py                     # AI findings & recommendation queries
│   │   ├── conversation_repo.py           # Conversation pair & channel queries
│   │   ├── invitation_repo.py             # Invitation token lookup & counter tracking
│   │   ├── message_repo.py                # Message history & pagination queries
│   │   ├── session_repo.py                # Refresh token session management
│   │   ├── user_repo.py                   # User lookups & username search queries
│   │   └── verification_repo.py           # OTP challenge persistence
│   ├── schemas/
│   │   ├── ai.py                          # Structured alignment & recommendation schemas
│   │   ├── auth.py                        # OTP request, ticket, and token schemas
│   │   ├── conversation.py                # Conversation summary & message feeds
│   │   ├── events.py                      # Socket.IO client/server event contracts
│   │   ├── group.py                       # Group channel & member schemas
│   │   ├── invitation.py                  # Invitation preview & join contracts
│   │   ├── message.py                     # Message create & read models
│   │   └── user.py                        # Public profile & availability models
│   ├── services/
│   │   ├── alignment_service.py           # Misunderstanding detection & cooldown orchestration
│   │   ├── auth_service.py                # Passwordless OTP & registration ticket flows
│   │   ├── conversation_service.py        # Direct chat pairing & message persistence
│   │   ├── email_service.py               # Email delivery orchestration
│   │   ├── group_service.py               # Group channels & role-based permissions
│   │   ├── invitation_service.py          # Secure invitation token generation & onboarding
│   │   ├── recommendation_service.py      # Multi-provider recommendation & link sharing
│   │   └── user_service.py                # Discovery & profile management
│   ├── sockets/
│   │   ├── connection_manager.py          # In-memory session & connection registry
│   │   ├── events.py                      # Socket.IO connect, join, and send handlers
│   │   └── server.py                      # Socket.IO AsyncServer & ASGI app wrapper
│   ├── tasks/
│   │   └── ai_pipeline.py                 # Asynchronous background AI runner
│   └── main.py                            # ASGI root integrating FastAPI & Socket.IO
├── tests/
│   ├── conftest.py                        # In-memory async SQLite fixtures & clients
│   ├── test_alignment.py                  # Alignment detection & grounding tests
│   ├── test_auth.py                       # OTP, tickets, tokens, rate limits tests
│   ├── test_conversations.py              # 1-to-1 messaging & duplicate prevention tests
│   ├── test_groups.py                     # Group creation & verified joining tests
│   ├── test_health_and_providers.py       # Health probes & provider timeout tests
│   ├── test_recommendations.py            # YouTube/Spotify/Tavily search & share tests
│   ├── test_sockets.py                    # Handshake auth & room routing tests
│   └── test_users.py                      # Discovery, search, and availability tests
├── .env.example                           # Configuration template with placeholder credentials
├── .gitignore                             # Git ignore rules
├── alembic.ini                            # Alembic migration configuration
├── pyproject.toml                         # Project metadata, dependencies & pytest config
└── requirements.txt                       # Locked dependencies
```

---

## 3. Environment Configuration & API Credentials Guide

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

### Required Configuration Variables

| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `APP_NAME` | Display name of the application | `Alignment Radar API` |
| `APP_ENV` | Application environment (`development`, `testing`, `production`) | `development` |
| `API_V1_PREFIX` | Base prefix for version 1 REST routes | `/api/v1` |
| `FRONTEND_ORIGINS` | JSON array or comma-separated list of allowed frontend origins | `["http://localhost:5173"]` |
| `DATABASE_URL` | PostgreSQL async connection URI | `postgresql+asyncpg://postgres@localhost:5432/alignment_radar` |
| `JWT_SECRET_KEY` | High-entropy secret key for access and registration tokens | Replace with 32+ random characters |
| `JWT_ALGORITHM` | Algorithm for signing JWTs | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifespan in minutes | `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token lifespan in days | `7` |
| `OTP_HMAC_SECRET` | Cryptographic secret for hashing verification OTPs | Replace with a dedicated random string |
| `OTP_EXPIRE_SECONDS` | Verification code expiration in seconds | `600` (10 minutes) |
| `OTP_MAX_ATTEMPTS` | Maximum failed attempts allowed before code invalidation | `5` |
| `OTP_RESEND_COOLDOWN_SECONDS`| Cooldown period between resend attempts | `60` (1 minute) |
| `REDIS_URL` | Optional Redis URL for multi-worker Socket.IO client manager | *(empty for single-instance in-memory)* |
| `AI_ANALYSIS_ENABLED` | Feature flag to enable/disable AI misalignment scans | `true` |
| `RECOMMENDATIONS_ENABLED` | Feature flag to enable/disable contextual recommendations | `true` |
| `MAX_CONVERSATION_CONTEXT_MESSAGES` | Context window size for AI inference | `30` |
| `AI_COOLDOWN_SECONDS` | Conversation cooldown window to avoid repetitive AI alerts | `30` |
| `LOG_LEVEL` | Application logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |

### Where to Obtain External API Credentials

Replace `xxx` placeholders in `.env` with actual keys when enabling external providers:

1. **Resend (`RESEND_API_KEY`, `RESEND_FROM_EMAIL`)**:
   - Obtain at: [https://resend.com/api-keys](https://resend.com/api-keys)
   - Verified sender: In development, you can use `onboarding@resend.dev` to send test emails to your registered address. For production, configure a verified custom domain.
   - *Behavior if unconfigured*: In `development` or `testing` environments, OTP delivery is safely mocked and logged to the console without crashing.

2. **NVIDIA NIM (`NVIDIA_API_KEY`, `NVIDIA_BASE_URL`, `NVIDIA_MODEL`)**:
   - Obtain at: [https://build.nvidia.com/](https://build.nvidia.com/)
   - Base URL: `https://integrate.api.nvidia.com/v1`
   - Model: e.g., `nvidia/nemotron-4-340b-instruct` or any compatible Nemotron/Llama model.
   - *Behavior if unconfigured*: Background alignment detection and search intent extraction are cleanly skipped without generating false warnings or fabricated data.

3. **YouTube Data API v3 (`YOUTUBE_DATA_API_KEY`)**:
   - Obtain at: [Google Cloud Console](https://console.cloud.google.com/) -> Enable **YouTube Data API v3** -> Create API Key.
   - *Behavior if unconfigured*: Video recommendations are excluded; other configured providers continue to function.

4. **Spotify Web API (`SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`)**:
   - Obtain at: [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) -> Create an App -> Copy Client ID and Secret.
   - Flow: Uses public Client Credentials; user account login is never required.
   - *Behavior if unconfigured*: Spotify track recommendations are excluded gracefully.

5. **Tavily Search API (`TAVILY_API_KEY`)**:
   - Obtain at: [https://tavily.com/](https://tavily.com/)
   - *Behavior if unconfigured*: Real-time web and cricket search context is skipped gracefully.

---

## 4. Installation & Database Setup

### 1. Python Environment

Ensure Python 3.11+ is installed. Create and activate a virtual environment:

**Windows (PowerShell):**
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Database Setup

The default `DATABASE_URL=sqlite+aiosqlite:///./alignment_radar.db` needs no setup: `alembic upgrade head` creates the file. To use PostgreSQL instead (not re-verified for this release), create the database (e.g. using `psql`):
```sql
CREATE DATABASE alignment_radar;
```

Update `DATABASE_URL` in `.env`:
```env
DATABASE_URL=postgresql+asyncpg://postgres:your_password@localhost:5432/alignment_radar
```

### 3. Run Alembic Migrations

Execute the migration to build all tables and indexes:
```bash
alembic upgrade head
```

---

## 5. Running the Application

Start the integrated ASGI server (FastAPI + Socket.IO) using Uvicorn:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- **Interactive API Documentation (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Alternative Documentation (ReDoc)**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Liveness Health Check**: [http://localhost:8000/health](http://localhost:8000/health)
- **Readiness Health Check**: [http://localhost:8000/ready](http://localhost:8000/ready)

---

## 6. REST API Endpoints Specification

All endpoints are versioned under `/api/v1`.

### Authentication
- `POST /api/v1/auth/register/request-code`: Send OTP code for new user registration.
- `POST /api/v1/auth/register/verify-code`: Verify OTP and obtain short-lived `registration_ticket`.
- `POST /api/v1/auth/register/complete`: Submit `registration_ticket` and unique username; returns JWT tokens.
- `POST /api/v1/auth/login/request-code`: Send OTP code for existing user sign-in.
- `POST /api/v1/auth/login/verify-code`: Verify OTP; returns access and refresh tokens.
- `POST /api/v1/auth/refresh`: Rotate refresh token and obtain fresh access token.
- `POST /api/v1/auth/logout`: Revoke active refresh token session.

### Users & Discovery
- `GET /api/v1/users/me`: Return authenticated user's private profile.
- `GET /api/v1/users/search?username={query}`: Search users by username (excludes self, returns public fields only).
- `GET /api/v1/users/username-availability?username={query}`: Check availability and format validity of a username.

### Conversations & Messages
- `GET /api/v1/conversations`: List all active conversations (direct chats and groups) for sidebar display.
- `POST /api/v1/conversations/direct/{username}`: Create or idempotently retrieve 1-to-1 direct chat.
- `GET /api/v1/conversations/{conversation_id}/messages`: Load cursor-paginated chat history (requires membership).

### Groups & Invitations
- `POST /api/v1/groups`: Create group chat. Creator is assigned `admin` role.
- `GET /api/v1/groups`: List groups where current user is a member.
- `GET /api/v1/groups/{group_id}`: Get group metadata.
- `GET /api/v1/groups/{group_id}/members`: List members and roles.
- `POST /api/v1/groups/{group_id}/invitations`: Create secure invitation link (admin only).
- `DELETE /api/v1/groups/{group_id}/invitations/{invitation_id}`: Revoke invitation (admin only).

### Invitation Joining Flow
- `GET /api/v1/invitations/{token}`: Safe preview of invitation (title, inviter, validity).
- `POST /api/v1/invitations/{token}/request-code`: Request email verification code to join group.
- `POST /api/v1/invitations/{token}/verify-code`: Verify code. If existing user, joins group and returns session; if new user, returns ticket.
- `POST /api/v1/invitations/{token}/complete-registration`: Complete onboarding with unique username, joins group, and issues session.

### AI & Recommendations
- `GET /api/v1/conversations/{conversation_id}/ai-items`: Retrieve persisted alignment findings and recommendations.
- `POST /api/v1/conversations/{conversation_id}/recommendations/{recommendation_id}/share`: Explicitly share a recommendation as a normal chat message (persists to DB and broadcasts to room).

---

## 7. Socket.IO Real-Time Architecture & Event Contracts

Real-time communication is powered by `python-socketio` mounted directly on the ASGI application. Native WebSocket endpoints are avoided in favor of consistent Socket.IO contracts.

### Handshake Authentication
When connecting, the client must supply the JWT access token in the `auth` payload:

```javascript
import { io } from "socket.io-client";

const socket = io("http://localhost:8000", {
  auth: {
    token: "YOUR_JWT_ACCESS_TOKEN",
  },
  transports: ["websocket", "polling"],
});
```

### Event Contracts

#### 1. Client-to-Server Events

- **`conversation:join`**: Subscribe to a conversation room. Server strictly verifies user membership in PostgreSQL before allowing the socket into `conversation:{conversation_id}`.
  ```json
  {
    "conversation_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
  }
  ```

- **`message:send`**: Post a chat message. Sender ID is extracted from the verified server-side session, never trusted from client payload.
  ```json
  {
    "conversation_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "content": "Shall we review the pull request today?",
    "message_type": "text",
    "msg_metadata": {},
    "client_id": "client-generated-uuid-for-idempotency"
  }
  ```

#### 2. Server-to-Client Events

- **`message:ack`**: Dispatched to sender upon successful PostgreSQL persistence.
  ```json
  {
    "status": "ok",
    "message_id": "uuid",
    "conversation_id": "uuid",
    "client_id": "client-generated-uuid",
    "created_at": "2026-10-17T11:00:00Z"
  }
  ```

- **`message:new`**: Broadcast to all members of `conversation:{conversation_id}`.
  ```json
  {
    "message": {
      "id": "uuid",
      "conversation_id": "uuid",
      "sender_id": "uuid",
      "sender_username": "alice",
      "content": "Shall we review the pull request today?",
      "message_type": "text",
      "msg_metadata": {},
      "client_id": "client-generated-uuid",
      "created_at": "2026-10-17T11:00:00Z"
    }
  }
  ```

- **`message:error`**: Dispatched to client if an action fails or validation errors occur.
  ```json
  {
    "code": "FORBIDDEN",
    "message": "You are not a member of this conversation.",
    "client_id": null
  }
  ```

- **`ai:alignment`**: Broadcast to the conversation room when a misalignment is detected.
  ```json
  {
    "finding": {
      "id": "uuid",
      "conversation_id": "uuid",
      "triggered_by_message_id": "uuid",
      "mismatch_detected": true,
      "category": "deadlines",
      "explanation": "Alice references shipping by end of week while Bob is operating on a next-month timeline.",
      "confidence": 0.89,
      "supporting_message_ids": ["uuid-1", "uuid-2"],
      "clarification_question": "Could you clarify the targeted release date?",
      "created_at": "2026-10-17T11:00:05Z"
    }
  }
  ```

- **`ai:recommendation`**: Broadcast to the conversation room when contextual items are found.
  ```json
  {
    "recommendation": {
      "id": "uuid",
      "conversation_id": "uuid",
      "source": "youtube",
      "title": "Anirudh New Song Live Performance",
      "url": "https://www.youtube.com/watch?v=example",
      "snippet": "Official performance video",
      "category": "music",
      "published_date": "2026-10-10",
      "extra_data": { "video_id": "example" },
      "is_shared_in_chat": false,
      "created_at": "2026-10-17T11:00:06Z"
    }
  }
  ```

---

## 8. AI Pipeline & External Integrations

### Asynchronous Concurrency
All AI operations execute strictly outside the HTTP request/response and Socket.IO send path. When a message is saved:
1. The message is immediately committed to PostgreSQL and broadcast via `message:new`.
2. A background task `schedule_ai_pipeline` is dispatched using `asyncio.create_task` regulated by a concurrency semaphore.
3. If an alignment warning or recommendation is generated, it is broadcast to the room asynchronously. Slow provider inference or network issues never degrade message delivery throughput.

### Evidence Grounding & Anti-Hallucination
- Nemotron is instructed with strict JSON schema constraints.
- Any returned `supporting_message_ids` are checked against the actual IDs present in the conversation context. Any fabricated or non-existent IDs are stripped.
- If fewer than 2 messages exist, or confidence is below 0.4, or no mismatch exists, findings are suppressed to prevent false alarms.

---

## 9. Security & Threat Mitigations

1. **Strict CORS**: Origins are validated from `FRONTEND_ORIGINS`. Wildcards (`*`) are disallowed in production.
2. **Passwordless Security**: Single-use OTP codes expire in 10 minutes and are hashed with HMAC-SHA256 (`OTP_HMAC_SECRET`). Raw codes are never stored in the database.
3. **Attempt Counters & Cooldowns**: Maximum 5 attempts per OTP code before revocation; 60-second cooldown between resends.
4. **Registration Tickets**: Short-lived signed tokens ensure users cannot register without completing email verification.
5. **Unique Usernames**: Case-insensitive uniqueness is enforced at the database level (`ix_users_username_lower`) and validated in application logic.
6. **Unique Direct Conversations**: Strict database constraint on `(direct_user_low_id, direct_user_high_id)` guarantees mathematical uniqueness without race conditions.
7. **Role-Based Group Invitations**: Unpredictable URL tokens are hashed with SHA-256 in the database. Only group admins can generate or revoke invitations.
8. **Sensitive Data Redaction**: The custom logging filter redacts emails, Bearer tokens, OTPs, and API credentials from application logs.
9. **URL Scheme Validation**: Contextual recommendations strictly permit `http://` and `https://` schemes, rejecting `javascript:` or arbitrary protocols.

---

## 10. Automated Tests & Results

The test suite contains 28 automated tests covering authentication, messaging, group management, invitations, AI alignment, external recommendations, health checks, and Socket.IO routing.

### Running the Tests

Execute pytest with verbose output:
```bash
pytest -v
```

Run test suite with test coverage metrics:
```bash
pytest --cov=app --cov-report=term-missing tests/
```

### Actual Test Results

```text
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-9.1.1, pluggy-1.7.0
rootdir: backend
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.15.1, asyncio-1.4.0, cov-7.1.0
asyncio: mode=Mode.AUTO

tests/test_alignment.py::test_alignment_analysis_grounded_evidence_and_persistence PASSED [  3%]
tests/test_alignment.py::test_alignment_suppresses_low_confidence_or_aligned_conversations PASSED [  7%]
tests/test_auth.py::test_request_registration_code_success PASSED        [ 10%]
tests/test_auth.py::test_request_registration_code_duplicate_email PASSED [ 14%]
tests/test_auth.py::test_verify_registration_code_and_reuse_prevention PASSED [ 17%]
tests/test_auth.py::test_verify_code_expired PASSED                      [ 21%]
tests/test_auth.py::test_complete_registration_and_case_insensitive_username PASSED [ 25%]
tests/test_auth.py::test_login_flow_and_token_refresh_rotation PASSED    [ 28%]
tests/test_auth.py::test_logout_session_invalidation PASSED              [ 32%]
tests/test_conversations.py::test_direct_conversation_creation_and_duplicate_prevention PASSED [ 35%]
tests/test_conversations.py::test_direct_conversation_self_chat_forbidden PASSED [ 39%]
tests/test_conversations.py::test_conversation_history_access_control PASSED [ 42%]
tests/test_groups.py::test_group_creation_and_admin_assignment PASSED    [ 46%]
tests/test_groups.py::test_group_invitation_creation_and_admin_auth PASSED [ 50%]
tests/test_groups.py::test_invitation_join_existing_user PASSED          [ 53%]
tests/test_groups.py::test_invitation_join_new_user_registration PASSED  [ 57%]
tests/test_health_and_providers.py::test_health_and_readiness_endpoints PASSED [ 60%]
tests/test_health_and_providers.py::test_ai_items_endpoint PASSED        [ 64%]
tests/test_health_and_providers.py::test_unconfigured_providers_raise_clear_errors PASSED [ 67%]
tests/test_health_and_providers.py::test_provider_network_and_timeout_errors PASSED [ 71%]
tests/test_recommendations.py::test_recommendations_retrieval_and_url_validation PASSED [ 75%]
tests/test_recommendations.py::test_share_recommendation_as_normal_chat_message PASSED [ 78%]
tests/test_sockets.py::test_socket_connect_authentication_success_and_failure PASSED [ 82%]
tests/test_sockets.py::test_socket_conversation_join_authorization PASSED [ 85%]
tests/test_sockets.py::test_socket_message_send_and_broadcast PASSED     [ 89%]
tests/test_users.py::test_get_current_user_profile PASSED                [ 92%]
tests/test_users.py::test_user_search_excludes_self_and_hides_private_data PASSED [ 96%]
tests/test_users.py::test_username_availability PASSED                   [100%]

============================= 28 passed in 2.10s ==============================
```

---

## 11. Troubleshooting

- **`greenlet` / SQLAlchemy AsyncIO Error**: If installing manually, ensure `greenlet` is installed (`pip install greenlet`), which is required by SQLAlchemy's async engine under Python 3.11+.
- **Database Connection Refused**: Verify that PostgreSQL is running and credentials in `DATABASE_URL` match your local cluster. Use the `/ready` endpoint to inspect database connectivity status.
- **Provider API Quotas & Timeouts**: If external APIs return 429 or 5xx, the providers automatically log the occurrence and return empty results without breaking the chat application.
