# Deploying Alignment Radar

No deployment target is configured in this repository. This guide lists what any host needs and the
steps that have been verified locally. Nothing here has been deployed publicly.

## Shape of the deployment

| Part | What it is | Host requirements |
|---|---|---|
| Backend | One ASGI process: `uvicorn app.main:app` from `backend/` serves the REST API, Socket.IO (`/socket.io`) and health checks | Python 3.11+, WebSocket support, persistent disk |
| Frontend | Static files from `cd frontend && npm run build` (`frontend/dist/`) | Any static host with HTTPS and single-page-app fallback (unknown paths serve `index.html`) |
| Database | SQLite file (`DATABASE_URL=sqlite+aiosqlite:///./alignment_radar.db`) | Persistent disk; backups |
| Uploads | `backend/data/uploads/` (attachments and voice notes) | Persistent disk, private to the backend |

### Run a single backend process

Socket.IO room membership and the reminder and AI-recovery workers live inside the process. Run exactly
one Uvicorn worker. Several processes would deliver messages only to clients on the same process and would
run the reminder worker more than once. Scaling out needs `REDIS_URL` (Socket.IO Redis adapter), PostgreSQL
and a single designated worker process; that set-up has not been tested.

### Persistent storage

SQLite and uploads are files on local disk. Hosts with ephemeral filesystems lose them on every restart or
redeploy unless a persistent volume is mounted at `backend/` (or at least for the database file and
`backend/data/uploads/`).

## Backend configuration

Start from `backend/.env.example` and set these in the host's secret store, never in the repository:

| Variable | Production value |
|---|---|
| `APP_ENV` | `production` (startup fails if the secrets below are placeholders or shorter than 32 characters, or if CORS is `*`; API docs are disabled) |
| `JWT_SECRET_KEY`, `OTP_HMAC_SECRET` | Two different random values of at least 32 characters |
| `ENCRYPTION_SECRET_KEY` | Optional random value; keep it stable once Google accounts are connected |
| `FRONTEND_ORIGINS` | JSON list of the deployed frontend origin(s), e.g. `["https://app.example.com"]` |
| `DATABASE_URL` | Path on the persistent volume, e.g. `sqlite+aiosqlite:////data/alignment_radar.db` |
| `GOOGLE_REDIRECT_URI` | `https://<frontend-host>/auth/google/callback`, also registered in Google Cloud Console |
| Provider keys | Only those you use: `NEBIUS_API_KEY` (+ `AI_ROUTER_STRATEGY=nebius`), `NVIDIA_API_KEY`, `GROQ_API_KEY`, `BREVO_API_KEY` + `BREVO_FROM_EMAIL`, `TAVILY_API_KEY`, `YOUTUBE_DATA_API_KEY`, `SPOTIFY_CLIENT_ID`/`SECRET`, `GOOGLE_CLIENT_ID`/`SECRET` |

Start command, from `backend/`:

```bash
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers
```

Back up the database file before running migrations against existing data.

## Frontend configuration

`VITE_*` values are compiled into the bundle, so set them before building:

```bash
cd frontend
VITE_API_BASE_URL=https://<backend-host>/api/v1 VITE_SOCKET_URL=https://<backend-host> npm run build
```

Serve `frontend/dist/` over HTTPS with a rewrite of all unknown paths to `/index.html` (routes such as
`/chat` and `/auth/google/callback` are handled in the browser).

## Health checks and logs

- Liveness: `GET /health` returns `{"status": "ok"}`.
- Readiness: `GET /api/v1/ready` returns 503 when the database is unreachable and lists which providers are
  configured (booleans only, no keys).
- Logs go to standard output; set `LOG_LEVEL` (default `INFO`). Errors from the AI router's text providers are
  logged without response bodies; speech-provider failures log up to 200 characters of the provider's error
  response.

## Verified locally for this release

- `alembic upgrade head` on an empty SQLite database, plus downgrade and re-upgrade, with existing rows preserved
  (`backend/tests/verify_disposable_migrations.py`).
- Backend started against a freshly migrated database: `/health`, `/api/v1/ready`, 401 for unauthenticated
  API calls, CORS allowed only for configured origins, Socket.IO connections refused without a valid token.
- Two users exchanging a direct message in real time over Socket.IO, with idempotent resend by `client_id`.
- Production frontend build (`npm run build`).

## Remaining steps for a public deployment

1. Choose a host for the backend (persistent volume, WebSockets, single process) and one for the static frontend.
2. Set the production environment variables above in the host's secret store.
3. Register the production `GOOGLE_REDIRECT_URI` and JavaScript origin in Google Cloud Console, if Google
   features are used.
4. Build the frontend with the production backend URL and deploy it.
5. Run `alembic upgrade head`, start the backend, and check `/api/v1/ready`.
6. Sign up through the deployed UI and exchange a message between two accounts.
