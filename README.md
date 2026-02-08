# Alphonse UI

Alphonse UI is an interface organ: an extremity (explicit commands), a sense (signals), and a ritual space (conversation + visibility). It is not the brain. It never decides, classifies intent, or owns durable state. All cognition, memory, planning, and persistence belong to Alphonse.

## Principles

- Server-first UI (HTMX is the default interaction model).
- Tailwind CSS utility classes for presentation.
- Minimal JavaScript, no SPA, no global routing/state.
- Client-side code only as isolated islands for time-based phenomena (chat/presence/voice/video).
- The UI observes state; it does not interpret or persist.

## Current Scope

This repo provides the initial scaffolding and HTMX skeleton:

- Main Chat screen as the central plaza.
- Abilities CRUD screen (list/create/patch/delete with enabled-only filtering).
- Gap Proposals review screen (coalesce, approve/reject, dispatch).
- Gap Tasks tracking screen (open/done workflow for skill creation tasks).
- Left internal navigation with collapsible sections.
- Right contextual panel for external world (hidden by default).
- HTMX endpoints for chat timeline and presence placeholder.
- Optional presence island using SSE with HTMX polling fallback.
- Chat is synchronous request/response (no streaming dependency).
- In-memory chat messages for local development only.

## How To Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ALPHONSE_API_BASE_URL=http://localhost:8001
# optional if backend enforces token:
# export ALPHONSE_API_TOKEN=your-token
# optional message timeout in seconds; unset/0/none means wait indefinitely:
# export ALPHONSE_API_MESSAGE_TIMEOUT_SECONDS=90
# optional UI display name for metadata.user_name:
# export ALPHONSE_UI_USER_NAME="Alphonse UI"
python -m flask --app server/app.py run --port 5001 --debug
```

Open `http://localhost:5001`.

## Structure

```
server/
  app.py                  Flask routes + HTMX endpoints
  clients/
    alphonse_api.py       Alphonse HTTP adapter + response validation
  templates/
    base.html             Shell layout
    chat.html             Main plaza
    admin.html            Placeholder
    integrations.html     Placeholder
    abilities.html        Ability CRUD surface
    gap_proposals.html    Proposal review and dispatch surface
    gap_tasks.html        Skill-creation task tracking surface
    partials/
      chat_timeline.html  Timeline HTMX fragment
      chat_message.html   Message fragment
      presence.html       Presence fragment
  static/
    css/app.css           Legacy stylesheet (no longer required for Tailwind layout)
    js/presence_island.js Optional SSE island scoped to #presence-island
requirements.txt
AGENTS.md                 Agent–UI contract
```

## Notes

- `AlphonseClient` in `server/clients/alphonse_api.py` calls Alphonse API over HTTP.
- Adapter logic lives in `server/clients/alphonse_api.py` and validates response shape before routes consume data.
- Templates use Tailwind via CDN and server-rendered Jinja partials.
- Chat command dispatch uses `POST /agent/message`.
- Presence snapshots use `GET /agent/status`.
- Delegate routes attempt backend APIs first (`/api/v1/delegates*`, then transitional `/delegates*`), with local fallback while backend contract is finalized.
- Messages are stored in-memory for dev only and will reset on restart.
- If Alphonse API is unreachable, chat remains usable and UI shows degraded-state status/events.

## Presence Island

- SSE endpoint: `GET /stream/presence` (`text/event-stream`).
- The client module mounts only to `#presence-island` in `chat.html`.
- No global state, routing, or framework usage.
- Fallback behavior:
  - If `EventSource` is unavailable, `#presence-island` switches to HTMX polling.
  - Polling uses `GET /ui/presence` every 20 seconds.
  - If SSE disconnects/errors, the same HTMX polling fallback is activated.

## Chat Delivery Modes

- Chat mode is HTMX-only in this MVP:
  - `POST /chat/messages` appends the user message and a temporary assistant placeholder, then returns immediately.
  - A background worker sends `POST /agent/message` and updates the pending assistant message when a response arrives.
  - Composer uses HTMX target swap to replace `#chat-timeline`.
  - Timeline refreshes via HTMX polling (`every 2s`) to pick up async updates.
  - API/network/response errors resolve to assistant fallback text: `Alphonse is unavailable.`
