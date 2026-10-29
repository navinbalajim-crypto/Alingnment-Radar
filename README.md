# Alignment Radar

Real-time team messaging that detects communication misalignment as it happens: vague
deadlines, unclear references, missing owners, conflicting expectations. It suggests a
clarifying question before the misunderstanding costs anyone time.

Alignment Radar is chat-first. Every AI result appears inside the conversation it is about,
not on a separate dashboard.

## Features

- **Messaging**: direct messages and group conversations with invitation links, real-time
  delivery over Socket.IO, replies, attachments (10 MB limit), and per-user or for-everyone deletion.
- **Alignment detection**: messages are analysed in the background. Findings appear in the
  thread, and either side can request a clarification, confirm or dismiss it, and mark it resolved.
- **Writing assistance**: an offline spelling engine corrects clear typos while you type and
  offers suggestions for ambiguous ones. Optional cloud draft analysis and autocomplete run
  only after the user opts in.
- **Contextual recommendations**: YouTube, Spotify and Tavily results when a conversation asks for them.
- **Conversation context**: a per-conversation context graph that flags statements contradicting earlier ones.
- **Tasks and reminders** extracted from messages.
- **Voice notes**: recorded in the browser, transcribed and translatable on request. Audio is
  sent to a speech provider only if the sender has enabled AI processing.
- **Google integrations** (optional): Google sign-in, Google Contacts, Gmail new-mail alerts
  (metadata only), and Google Meet links created inside a conversation.

## Architecture

| Layer | Technology |
|---|---|
| Frontend | React 19 + Vite (plain JavaScript), Tailwind CSS, React Aria Components |
| Backend | FastAPI (Python 3.11+, tested on 3.13), async SQLAlchemy 2, Alembic |
| Database | SQLite via `aiosqlite` (default); PostgreSQL via `asyncpg` is supported by the code but was not part of this release's verification |
| Real-time | Socket.IO (`python-socketio` / `socket.io-client`), optional Redis adapter |

Detailed API routes, schemas and Socket.IO contracts: [backend/README.md](backend/README.md).

### AI providers and their roles

| Provider | Model | Used for |
|---|---|---|
| Nebius Token Factory | `NEBIUS_MODEL` (default `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`) | All router text tasks when `AI_ROUTER_STRATEGY=nebius` |
| NVIDIA NIM | `NVIDIA_MODEL` (e.g. `nvidia/nemotron-3-super-120b-a12b`) | Alignment detection, resolution evaluation, recommendation intent, draft analysis |
| Groq | `GROQ_MODEL` (e.g. `openai/gpt-oss-120b`) | Low-latency draft analysis and autocomplete; Whisper fallback for voice |
| NVIDIA Riva (NVCF) | Canary ASR, Riva Translate | Voice-note transcription and translation |
| Local engine | SymSpell-derived dictionary + rules | Offline spelling and clarity fixes; fallback when cloud AI is unavailable |
| Tavily, YouTube, Spotify | — | Contextual recommendations |
| Google APIs | OAuth, People, Gmail metadata, Meet REST v2 | Sign-in, contacts, mail alerts, meeting creation |

Routing lives in `backend/app/services/ai_router.py`. The default `adaptive` strategy picks
between NVIDIA and Groq by health and measured latency, with one bounded fallback and a
circuit breaker per provider. Setting `AI_ROUTER_STRATEGY` to `nvidia`, `groq` or `nebius`
forces a single provider and disables cross-provider fallback (failures fall back to the
local engine where one exists). `local` uses no cloud AI at all.

## Setup

Prerequisites: Python 3.11+ (3.13 recommended), Node.js 22.12+.

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .\.venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in the keys you have
alembic upgrade head        # creates/updates ./alignment_radar.db
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Health: `GET http://127.0.0.1:8000/health` · readiness (database + configured providers):
`GET http://127.0.0.1:8000/api/v1/ready` · API docs (development only): `http://127.0.0.1:8000/docs`

### Frontend

```bash
cd frontend
npm install
cp .env.example .env        # VITE_API_BASE_URL=http://localhost:8000/api/v1
npm run dev                 # http://localhost:5173
```

### Environment variables

All secrets live only in `backend/.env`, which is git-ignored. `backend/.env.example` lists every
variable with placeholders. A provider left as a placeholder is treated as unconfigured
and its features degrade gracefully instead of failing. The frontend never receives provider
keys; it only knows the backend URL.

Generate `JWT_SECRET_KEY` and `OTP_HMAC_SECRET` as separate random values, for example
`python -c "import secrets; print(secrets.token_urlsafe(48))"`.

Email verification codes are sent through Brevo (or Resend). Without an email provider, use
password sign-in or Google sign-in.

### Google sign-in, Contacts, Gmail and Meet

Create an OAuth client in Google Cloud Console, register `GOOGLE_REDIRECT_URI`
(default `http://localhost:5173/auth/google/callback`), and enable the People API, Gmail API
and Google Meet REST API for the features you want. Browse the app from the same host you
registered (`localhost` and `127.0.0.1` are different origins for browser storage).

### Voice notes

Recording works in any browser with microphone access. Transcription needs `NVIDIA_ASR_API_KEY`
(or `NVIDIA_API_KEY`) or `GROQ_API_KEY`; translation needs `NVIDIA_TRANSLATION_API_KEY`
(or `NVIDIA_API_KEY`) or `GROQ_API_KEY`. Transcription runs only for senders who have enabled
AI processing; otherwise the note shows "AI consent required" and can be retried after opting in.

### Using Nebius Token Factory

```env
NEBIUS_API_KEY=your_nebius_api_key_here
NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1
NEBIUS_MODEL=nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B
AI_ROUTER_STRATEGY=nebius
```

Confirm the model ID is available to your account with
`GET https://api.tokenfactory.nebius.com/v1/models` before relying on it.

Cost notes: Token Factory bills per token against your account balance; promotional
credit is finite. Every alignment scan, draft analysis and recommendation check is a billed
request. To limit spend, use a smaller Nemotron tier as `NEBIUS_MODEL`, keep
`AI_RACING_ENABLED=false` (racing sends each request to two providers), raise
`AI_COOLDOWN_SECONDS` to space out automatic scans, and set spending limits in the Nebius
console. When the balance runs out, requests fail, the circuit breaker opens, and the app
continues with local-only features.

## Privacy and security

- Cloud draft analysis, autocomplete, draft recommendations and voice transcription are off
  until each user opts in. The offline spelling engine never makes network calls.
- Endpoints that read or change conversation data (messages, attachments, voice notes,
  meetings, alignment findings) check conversation membership. Socket connections require a
  valid access token.
- Access tokens are short-lived JWTs with rotating refresh sessions. Verification codes are
  stored as HMACs with attempt limits and resend cooldowns.
- Google refresh tokens are stored encrypted (`ENCRYPTION_SECRET_KEY`, defaulting to `JWT_SECRET_KEY`).
- Gmail integration reads message metadata only, never message bodies.
- Uploads are stored under `backend/data/uploads/` and served only to conversation members.
- `APP_ENV=production` refuses to start with placeholder secrets or a wildcard CORS origin,
  and turns off the interactive API docs.

Never commit `backend/.env`, `*.db` files, `backend/data/uploads/` or `scripts/*_session.json`;
all are git-ignored.

## Tests

```bash
cd backend && pytest -q                       # mocked providers; no external API calls
cd backend && python tests/verify_disposable_migrations.py   # migrations on a throwaway SQLite file
cd frontend && npm test
cd frontend && npm run build
node scripts/evaluate_spelling.mjs            # spelling engine evaluation report
```

Automated tests mock every external provider. They verify request shape, error handling
and routing, not live inference.

## Deployment

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). In short: one backend process (Socket.IO state is
in memory unless `REDIS_URL` is set), persistent storage for the database and
`backend/data/uploads/`, HTTPS, `APP_ENV=production`, and `FRONTEND_ORIGINS` and
`GOOGLE_REDIRECT_URI` set to the deployed frontend URL.

## Known limitations

- SQLite is the verified database. It suits a single server instance; scale-out needs
  PostgreSQL and the Redis Socket.IO adapter, which this release has not tested.
- The SQLAlchemy models declare some indexes and foreign keys that the Alembic migrations do
  not create on SQLite (reported by `alembic check`). Behaviour is unaffected; a follow-up
  migration should align them.
- The spelling engine is English-only.
- The production frontend bundle includes a 1.6 MB (470 kB gzipped) spelling dictionary chunk,
  loaded on demand.

## Licence and third-party material

The original code in this repository is released under the [MIT License](LICENSE).
Third-party components keep their own licences; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Where the spelling data comes from, and which development datasets are deliberately not
included, is documented in [docs/DATA_PROVENANCE.md](docs/DATA_PROVENANCE.md).
