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
- Left internal navigation with collapsible sections.
- Right contextual panel for external world (hidden by default).
- HTMX endpoints for chat timeline and presence placeholder.
- Optional presence island using SSE with HTMX polling fallback.
- Chat remains HTMX-first with optional isolated streaming island.
- In-memory chat messages for local development only.

## How To Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ALPHONSE_API_BASE_URL=http://127.0.0.1:8001
# optional if backend enforces token:
# export ALPHONSE_API_TOKEN=your-token
python -m flask --app server/app.py run --port 5001
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
    partials/
      chat_timeline.html  Timeline HTMX fragment
      chat_message.html   Message fragment
      presence.html       Presence fragment
  static/
    css/app.css           Legacy stylesheet (no longer required for Tailwind layout)
    js/chat_stream_island.js Optional SSE island scoped to #chat-stream-island
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

- Default mode is HTMX-only:
  - `POST /chat/messages` appends message server-side and returns the full `chat_timeline` partial.
  - Composer uses HTMX target swap to replace `#chat-timeline`.
- Optional stream mode:
  - Enable in `#chat-stream-island` (isolated JS module).
  - Form includes `stream=1`, and `POST /chat/messages` returns `X-UI-Stream-Url`.
  - Island subscribes to `GET /stream/chat?correlation_id=...` and renders stream output locally.
- Fallback behavior:
  - If SSE is unavailable or errors, UI remains fully functional in HTMX-only mode.
