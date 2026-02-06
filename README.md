# Alphonse UI

Server-first interface for the Alphonse system.

This UI is an extremity (explicit commands), a sense (signals), and a ritual space (conversation + visibility). It never makes decisions or owns durable state. All cognition, memory, and persistence live in Alphonse.

## Current State

This repo contains the initial server-first UI skeleton:

- Flask + Jinja2 templates
- HTMX as the default interaction model
- Two isolated client-side islands: chat stream and presence stream
- Dark-first, high-legibility placeholder styling

## Run Locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m flask --app server/app.py run --port 5001
```

Open `http://localhost:5001`.

## Structure

```
server/
  app.py                  Flask routes + HTMX endpoints
  templates/              Jinja2 views
    base.html             Shell layout
    *.html                Screen templates
    partials/             HTMX fragments
  static/
    css/app.css           Placeholder visual system
    js/chat_island.js     Chat client island
    js/presence_stream.js Presence stream island
requirements.txt
```

## Interaction Model

- **Commands**: explicit user actions submitted via `/commands/submit`.
- **Signals**: passive inputs via `/signals/submit`.
- **Events / Snapshots**: rendered from `/fragments/*` (server-first placeholders for now).
- **Streams**: EventSource endpoints `/stream/chat` and `/stream/presence` feed isolated islands.

## UI Boundaries

HTMX-only screens: Threshold, Command Console, Signals, Events, Snapshots, System.

Client-side islands:
- `chat_island.js` mounted at `[data-island="chat"]` on `/ritual`.
- `presence_stream.js` mounted at `[data-island="presence"]` on `/presence`.

Each island is self-contained and removable without breaking the server-rendered UI.

## Contract (Draft)

- UI sends **Commands** and **Signals**.
- Alphonse emits **Events** and **Snapshots**.
- UI observes and renders; it does not interpret or persist.

## Next Steps

- Wire HTMX fragments to the real agent transport.
- Formalize the Agent–UI contract versioning.
- Replace placeholder styles with final visual system tokens.
