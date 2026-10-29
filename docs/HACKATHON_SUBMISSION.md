# Hackathon submission pack (draft)

Prepared for the Nebius x NVIDIA Global AI Hackathon 2026. The requirements below come from a third-party listing
(startupgrantsindia.com), not from the official Devpost rules page, which was not available during preparation.
Check them against the official rules before submitting. The listing gives the deadline as
**30 October 2026, 10:00 AM PDT**.

## Requirement checklist

| Requirement (as listed) | Status |
|---|---|
| Runs on Nebius Token Factory or Nebius AI Cloud | Done locally: `AI_ROUTER_STRATEGY=nebius` routes all text AI tasks to Token Factory. Verified with a live request on 2026-10-28. |
| Uses at least one NVIDIA open model | Done: `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` via Nebius; Nemotron via NVIDIA NIM; Canary ASR and Riva Translate for voice |
| Track selected | **Your choice.** "Best Apps and Agents" fits a chat app best; confirm against the official track descriptions. |
| Detailed project description | Draft below |
| Working demo URL | **Not done.** No public deployment exists. See [DEPLOYMENT.md](DEPLOYMENT.md). |
| Public YouTube demo video under 3 minutes | **Not done.** Script below. |
| Public repository with MIT / Apache 2.0 / MPL 2.0 licence and README | **Prepared locally, not published.** MIT `LICENSE` (copyright holder needs your confirmation), README, notices. No remote is configured and nothing has been pushed. |
| Feedback on Nebius / NVIDIA tools | **Yours to write.** Observations from development are listed below as raw material. |
| Explanation of updates if the project pre-existed | **Needs your input** (see below). |

## Project description (draft)

Alignment Radar is a real-time team chat that catches misunderstandings while they are still cheap to fix. As
people talk, it reads the conversation in the background and flags vague deadlines, unclear references, missing
owners and contradicting statements. Each finding appears in the thread itself, with a suggested clarifying question
that either person can send, confirm or dismiss. The composer corrects clear typos offline as you type and, if you
opt in, offers AI autocomplete and draft analysis. Voice notes are transcribed and translatable, Google Meet links
can be created from a conversation, and recommendations from YouTube, Spotify and Tavily appear when a chat asks
for them.

The text AI runs on NVIDIA Nemotron served through Nebius Token Factory, behind a router with per-provider circuit
breakers and an offline fallback, so the chat keeps working when a provider is slow or out of credit. Cloud AI
features are opt-in per user.

## Architecture summary

- React 19 + Vite frontend (plain JavaScript), Socket.IO client.
- FastAPI backend with async SQLAlchemy and Alembic on SQLite; Socket.IO for real-time delivery.
- AI router (`backend/app/services/ai_router.py`): Nebius Token Factory (Nemotron), NVIDIA NIM and Groq behind one
  interface with latency tracking, circuit breakers and a local fallback.
- Background analysis queue persists a job per message so analysis survives restarts.
- Offline spelling engine shared by browser and server (identical results, checked by a parity test).
- Voice: NVIDIA Canary ASR and Riva Translate via NVCF, with Groq fallbacks.

## Demo video script (about 2 min 45 s)

| Time | Scene | What to show and say |
|---|---|---|
| 0:00–0:15 | Title, then two browser windows side by side (two users) | "Teams lose hours to messages that each side reads differently. Alignment Radar catches that in the chat." |
| 0:15–0:45 | User A types a vague message, e.g. "can you send the report by end of week" | Typos corrected while typing; the message arrives instantly for user B. |
| 0:45–1:20 | Alignment finding appears in the thread | Show the finding and the suggested clarifying question; user B sends the clarification request; user A answers; the finding is marked resolved. |
| 1:20–1:40 | Composer autocomplete (after opting in) | Mention the opt-in switch and that suggestions come from Nemotron on Nebius Token Factory. |
| 1:40–2:05 | Voice note | Record a short note; transcript appears; translate it. |
| 2:05–2:20 | Google Meet button or a recommendation card | One integration, briefly. |
| 2:20–2:45 | Architecture slide | Nebius Token Factory + Nemotron, router with circuit breakers and offline fallback, opt-in privacy. Close with the repository URL. |

Before recording, enable AI processing for both demo accounts (voice transcription and autocomplete are off until a
user opts in), set `AI_ROUTER_STRATEGY=nebius`, and use demo accounts with no real personal data.

### Screens to capture

1. Login page.
2. Two-window real-time chat.
3. Alignment finding card with the clarification flow.
4. Composer correcting typos, and autocomplete suggestions.
5. Voice note with transcript and translation.
6. Meet invitation card or a recommendation card.
7. Architecture diagram.

## Changes to a pre-existing project (needs your input)

The repository has no commit history, so this cannot be reconstructed from version control. What the files show:

- Database migrations are dated from 2026-10-17 (initial schema) to 2026-10-27 (Google Meet invitations and voice
  transcripts).
- The Nebius provider (`backend/app/providers/nebius_provider.py`), Google Meet and voice-message features, password
  sign-in, replies and the context graph were not yet tracked by git when this pack was prepared, which suggests
  they are recent.
- During release preparation on 2026-10-28: the spelling engine's error model was replaced with project-authored
  values; voice-note access between conversations and the cloud-transcription consent check were fixed; production
  secret checks were added; timestamps are now sent with a UTC offset; licence and provenance documentation was added.

State which parts existed before the hackathon start date and which were built during it.

## Raw notes for Nebius / NVIDIA feedback

These are observations from development, not opinions. Write the feedback in your own words.

- Token Factory's OpenAI-compatible `/v1/models` and `/v1/chat/completions` worked with the existing OpenAI-style
  client code, needing only a base URL and model change.
- Nemotron's reasoning output consumed the whole `max_tokens` budget on short autocomplete requests until
  `chat_template_kwargs: {"enable_thinking": false}` was passed (see `backend/app/providers/base_ai_provider.py`).
- A live autocomplete request through Token Factory took about 1.7 s end to end on 2026-10-28 (single sample).
