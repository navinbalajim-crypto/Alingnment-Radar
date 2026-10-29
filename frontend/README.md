# Alignment Radar — Frontend Application

Alignment Radar is an AI-powered, real-time messaging web application that helps collaborators understand conversations, detect misunderstandings before they derail projects, and discover relevant external knowledge directly in the chat stream without leaving the application.

This frontend is built with React (JavaScript only, no TypeScript), Vite, React Router, Tailwind CSS, React Aria Components, Lucide React, and `socket.io-client`. It connects to the FastAPI and Socket.IO backend in `../backend`.

---

## 1. Architecture & Design Principles

- **Chat-First Experience:** Zero standalone dashboards, metrics widgets, or distracting vanity charts. All AI alignment insights and recommendations live natively inside the ongoing conversation.
- **Apple Design Skill HIG Compliance:** Designed following Apple's Human Interface Guidelines (`dickwu/apple-design-skill`):
  - Clean San Francisco / native system typography hierarchy.
  - Subtle borders (`rgba(0, 0, 0, 0.06)` light / `rgba(255, 255, 255, 0.08)` dark) and micro-shadows.
  - Generative AI presented as neutral perspective divergence and clarification prompts, never accusations against participants.
  - Responsive AppShell with persistent sidebar on desktop and accessible slide-over drawer on mobile devices.
- **Strictly JavaScript & JSX:** Pure ES modules, zero TypeScript.
- **Resilient Real-Time Socket.IO Integration:** Authenticated handshake, reconnection management, room isolation, client-side idempotency keys (`client_id`), and optimistic updates with server acknowledgment.

---

## 2. Directory Structure

```
frontend/
├── .env.example                     # Environment variables template
├── index.html                       # HTML5 entry with metadata and Apple viewport settings
├── package.json                     # Scripts, dependencies, and test commands
├── tailwind.config.js               # Tailwind configuration with Apple system palette
├── vite.config.js                   # Vite configuration with Vitest setup
├── src/
│   ├── main.jsx                     # Application root mounting index.css and App
│   ├── index.css                    # Apple typography smoothing, scrollbars, highlight animations
│   ├── app/
│   │   ├── App.jsx                  # Root App provider wrapper
│   │   └── router.jsx               # React Router routes and protected route guards
│   ├── components/
│   │   ├── ai/
│   │   │   ├── AlignmentFindingCard.jsx   # Inline AI divergence and clarification cards
│   │   │   ├── RecommendationCard.jsx    # YouTube / Spotify / Web cards with "Share in Chat"
│   │   │   └── EvidenceMessageLink.jsx   # Click-to-scroll evidence reference pills
│   │   ├── auth/
│   │   │   ├── LoginPage.jsx             # Passwordless email login flow
│   │   │   ├── RegisterPage.jsx          # Passwordless email registration flow
│   │   │   ├── VerifyEmailCode.jsx       # 6-digit pin code input with countdown timer
│   │   │   └── ChooseUsername.jsx        # Live debounced unique username availability check
│   │   ├── chat/
│   │   │   ├── ConversationItem.jsx      # Sidebar list row with avatars and timestamps
│   │   │   ├── ConversationView.jsx      # Conversation canvas assembling header, messages, composer
│   │   │   ├── MessageBubble.jsx         # User vs other bubbles, link shares, and status icons
│   │   │   ├── MessageComposer.jsx       # Auto-growing textarea, keybindings, offline banner
│   │   │   └── MessageList.jsx           # Infinite scroll history with inline AI items
│   │   ├── groups/
│   │   │   ├── CreateGroupDialog.jsx     # Group creation modal
│   │   │   ├── GroupDetails.jsx          # Member roles and invitation link management
│   │   │   └── JoinGroupPage.jsx         # Public `/invitations/:token` redemption view
│   │   ├── layout/
│   │   │   ├── AppShell.jsx              # Responsive split-view layout and mobile drawer
│   │   │   ├── ConversationHeader.jsx    # Room header with live connection indicator
│   │   │   ├── Sidebar.jsx               # Direct Messages & Groups categorized sidebar
│   │   │   └── UserSearchDialog.jsx      # Registered user search and instant direct chat
│   │   └── ui/
│   │       ├── Avatar.jsx                # Apple avatar with initial letters and group icons
│   │       ├── Badge.jsx                 # Category, role, and confidence pill badges
│   │       ├── Button.jsx                # Accessible button using React Aria Components
│   │       ├── Input.jsx                 # Accessible input with error and helper text
│   │       └── Modal.jsx                 # Backdrop-blurred accessible modal dialog
│   ├── context/
│   │   ├── AuthContext.jsx               # Auth state, session restoration, token rotation
│   │   └── ChatContext.jsx               # Active chat, room subscription, socket message stream
│   ├── services/
│   │   ├── apiClient.js                  # Axios client with JWT Bearer and automatic 401 refresh
│   │   ├── authService.js                # Auth, registration, login, and user search APIs
│   │   ├── conversationService.js        # Direct chat, listing, and message history APIs
│   │   ├── groupService.js               # Group creation, membership, and invitation APIs
│   │   ├── invitationService.js          # Invitation token preview, verification, and join APIs
│   │   ├── aiService.js                  # Persisted AI items and recommendation sharing APIs
│   │   └── socketService.js              # Socket.IO connection singleton manager
│   ├── test/
│   │   ├── setup.js                      # JSDOM matchMedia and Testing Library extensions
│   │   ├── auth.test.jsx                 # Tests for email code and username availability
│   │   ├── chat.test.jsx                 # Tests for message bubbles and composer submission
│   │   ├── ai.test.jsx                   # Tests for alignment cards and recommendation sharing
│   │   ├── groups.test.jsx               # Tests for group creation and invitation page
│   │   └── sidebar.test.jsx              # Tests for sidebar sections and user search
│   └── utils/
│       ├── date.js                       # Message and conversation timestamp formatters
│       └── helpers.js                    # Client ID generator, classnames, and avatar colors
```

---

## 3. Integrated Backend Endpoints & Socket.IO Events

### REST API Endpoints (`/api/v1`)
| Domain | Method & Path | Description |
|---|---|---|
| **Auth** | `POST /auth/register/request-code` | Request single-use 6-digit code for new registration |
| **Auth** | `POST /auth/register/verify-code` | Verify 6-digit code and receive `registration_ticket` |
| **Auth** | `POST /auth/register/complete` | Submit unique username and display name with ticket |
| **Auth** | `POST /auth/login/request-code` | Request single-use 6-digit login code |
| **Auth** | `POST /auth/login/verify-code` | Verify login code and receive JWT access/refresh tokens |
| **Auth** | `POST /auth/refresh` | Rotate expired access token using active refresh token |
| **Auth** | `POST /auth/logout` | Revoke session and invalidate tokens on backend |
| **Users** | `GET /users/me` | Fetch authenticated user's private profile |
| **Users** | `GET /users/search?username=...` | Search registered users by username substring |
| **Users** | `GET /users/username-availability?username=...` | Check if username is untaken during registration |
| **Conversations** | `GET /conversations` | List user's direct messages and group conversations |
| **Conversations** | `POST /conversations/direct/{username}` | Idempotently open or create 1-to-1 conversation |
| **Conversations** | `GET /conversations/{id}/messages` | Paginated message history with cursor-based retrieval |
| **Groups** | `POST /groups` | Create group conversation with title and initial members |
| **Groups** | `GET /groups` | List user's group conversations |
| **Groups** | `GET /groups/{id}` | Retrieve group metadata |
| **Groups** | `GET /groups/{id}/members` | Retrieve member list with roles (admin / member) |
| **Groups** | `POST /groups/{id}/invitations` | Generate invitation token with expiry and max uses |
| **Groups** | `DELETE /groups/{id}/invitations/{id}` | Revoke active invitation link |
| **Invitations** | `GET /invitations/{token}` | Public preview for group title and validity |
| **Invitations** | `POST /invitations/{token}/request-code` | Request email join code for invitation |
| **Invitations** | `POST /invitations/{token}/verify-code` | Verify code; returns session or new-user ticket |
| **Invitations** | `POST /invitations/{token}/complete-registration` | Onboard new user directly into group room |
| **AI** | `GET /conversations/{id}/ai-items` | Fetch persisted alignment findings and recommendations |
| **AI** | `POST /conversations/{id}/recommendations/{id}/share` | Share recommendation as a `link_share` message |

### Socket.IO Event Contracts
| Event Name | Direction | Payload Contract |
|---|---|---|
| `connect` | Client ➔ Server | Handshake with `auth: { token: "Bearer <access_token>" }` |
| `conversation:join` | Client ➔ Server | `{ "conversation_id": "<uuid>" }` |
| `message:send` | Client ➔ Server | `{ "conversation_id": "<uuid>", "content": "...", "message_type": "text" \| "link_share", "msg_metadata": {}, "client_id": "<uuid>" }` |
| `message:ack` | Server ➔ Client | `{ "status": "ok", "message_id": "<uuid>", "conversation_id": "<uuid>", "client_id": "<uuid>", "created_at": "<iso>" }` |
| `message:new` | Server ➔ Client | `{ "message": { "id": "<uuid>", "conversation_id": "<uuid>", "sender_username": "...", "content": "...", "created_at": "..." } }` |
| `message:error` | Server ➔ Client | `{ "code": "VALIDATION_ERROR" \| "FORBIDDEN", "message": "...", "client_id": "..." }` |
| `ai:alignment` | Server ➔ Client | `{ "finding": { "id": "<uuid>", "category": "deadlines", "explanation": "...", "confidence": 0.95, "supporting_message_ids": [...], "clarification_question": "..." } }` |
| `ai:recommendation` | Server ➔ Client | `{ "recommendation": { "id": "<uuid>", "source": "Spotify" \| "YouTube" \| "Tavily", "title": "...", "url": "...", "extra_data": {...} } }` |

---

## 4. Getting Started

### Prerequisites
- Node.js 18+ (tested on Node.js 20+)
- Running Python backend service (`http://localhost:8000`)

### Installation
```bash
cd frontend
npm install
```

### Environment Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Default `.env` contents:
```ini
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_SOCKET_URL=http://localhost:8000
```

### Development Server
Start the local Vite development server:
```bash
npm run dev
```
The application will be accessible at: `http://localhost:5173`

### Production Build
```bash
npm run build
npm run preview
```

### Automated Tests
Run the comprehensive Vitest test suite:
```bash
npm run test
```
All 12 unit and integration tests across 5 test suites validate:
1. Passwordless registration, 6-digit verification code, and debounced username availability validation.
2. Login code delivery and token receipt.
3. Message bubbles (self vs other participants), `link_share` cards, and message composer Enter key submission.
4. Inline AI alignment finding cards with clickable evidence links and copyable clarification questions.
5. Contextual recommendation rendering (YouTube, Spotify, Web) and "Share in Chat" persistence.
6. Group creation with initial usernames, member listings with admin badges, and public invitation links.
7. Sidebar navigation, DM/Group separation, and user search discovery.

---

## 5. Troubleshooting & FAQ

- **Socket fails to connect (`Socket connection error`):** Verify that the backend ASGI server is running on port 8000 (`http://localhost:8000`) and that you have completed email login or registration to obtain a valid JWT token.
- **Invitations show expired:** Invitation links have a configurable expiration window (`expires_in_days`, default 7) or usage limit. The group administrator can generate a new link in the Group Info modal.
- **Backend CORS:** The backend `FRONTEND_ORIGINS` setting defaults to `["http://localhost:5173", "http://127.0.0.1:5173"]`. If running Vite on a different port, update `FRONTEND_ORIGINS` in `backend/.env`.
