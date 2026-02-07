# Agent Integration Plan

## Context and Non-Negotiable Constraints

- `atrium-server` is the correct backend project for Alphonse runtime and APIs.
- The previous web UI inside `atrium-server` is a legacy implementation and is being retired/refactored out.
- `alphonse-ui` is the new standalone UI and must remain an independent interface organ.
- UI must not import backend internals directly; integration is HTTP API only.

## API Surfaces Found in `atrium-server`

This is not a single API surface.

1. Alphonse Agent API (primary integration target)
- File: `/Users/alex/Code Projects/atrium-server/alphonse/infrastructure/api.py`
- Base behavior: FastAPI app started from agent runtime (`alphonse.agent.main`), default port `8001`.
- Endpoints currently present:
  - `GET /agent/status`
  - `POST /agent/message`
  - `GET /agent/timed-signals`
  - `LAN` router under `/lan/*` (pairing, devices, command/status relay, websocket)

2. Legacy mixed UI/API app (to be decoupled)
- File: `/Users/alex/Code Projects/atrium-server/interfaces/http/main.py`
- Contains old HTMX UI plus helper functions that call Alphonse API.
- Not a target for new UI coupling.

3. Domain API routes under old interfaces app
- File: `/Users/alex/Code Projects/atrium-server/interfaces/http/routes/api.py`
- Exposes additional `/api/*` endpoints (family events/worker routes).
- Useful for eventual migration map, but should be versioned and exposed from backend API boundary, not consumed via old UI app internals.

## Recommended Integration Strategy for `alphonse-ui`

1. Use only HTTP calls from `alphonse-ui` to Alphonse Agent API.
- Configure via env vars:
  - `ALPHONSE_API_BASE_URL` (default `http://127.0.0.1:8001`)
  - `ALPHONSE_API_TOKEN` (optional, sent as `x-alphonse-api-token`)

2. Keep a strict adapter layer in UI.
- Implement all backend calls inside `AlphonseClient`.
- UI routes call adapter methods only.
- No direct imports from `atrium-server` packages.

3. Map current UI contract to backend responses.
- Preserve UI contract headers on every UI response:
  - `X-UI-Ok`
  - `X-UI-Correlation-Id`
  - `X-UI-Timestamp`
  - `X-UI-Event-Type` where applicable
- Always generate/pass `correlation_id` from UI to backend for command calls.

4. Treat backend outages as first-class UI states.
- Timeout/connection errors -> `ui.command.failed` or `ui.event.presence.idle` as appropriate.
- Render explicit degraded-state placeholders; do not infer meaning.

## Endpoint Mapping (Initial)

- UI `GET /ui/presence`
  - Backend call: `GET /agent/status`
  - Render minimal runtime snapshot in presence partial.

- UI `POST /chat/messages`
  - Backend call: `POST /agent/message`
  - Outbound payload:
    - `text`
    - `channel` = `webui`
    - `timestamp`
    - `correlation_id`
    - optional metadata block
  - UI timeline appends user message immediately and shows backend acknowledgment/failure state.
  - Default delivery remains HTMX-only; optional stream mode uses `GET /stream/chat?correlation_id=...` as a UI-local island until backend streaming API is defined.

- UI `GET /chat/timeline`
  - Remains UI-local view composition; do not query DB directly.
  - Timeline is now mixed-entry (message + delegation card) and must remain server-rendered.
  - For now uses in-memory timeline store until richer event API is exposed.

- UI `GET /delegates`
  - Backend target (to define): delegates list endpoint that returns fields:
    - `id`, `name`, `capabilities`, `contract_version`, `pricing_model`, `status`, `last_seen`
  - Until available, UI keeps temporary in-memory delegate registry.

- UI `GET /delegates/<id>`
  - Backend target (to define): delegate detail endpoint with the same contract fields.

- UI `POST /delegates/<id>/assign`
  - Backend target (to define): delegation assignment command endpoint.
  - Must carry `correlation_id` from UI command through resulting backend events.
  - UI emits/reflects `ui.event.delegation.assigned` and renders inline delegation card in chat timeline.

## Risks and Gaps

1. Correlation echo consistency
- Current backend response from `/agent/message` may not always return `correlation_id` in response body.
- UI should treat its own generated `correlation_id` as source-of-truth for traceability.

2. Streaming support
- No dedicated SSE endpoint for agent events in primary API surface yet.
- Presence/chat islands should remain optional mounts until backend streaming contract is added.

3. API versioning consistency
- Existing endpoints are not under `/api/v1` in the primary agent API.
- Migration should standardize versioned routes without forcing UI to consume old mixed interfaces app.

4. Delegates API gap
- Current UI delegates routes are backed by in-memory data in the UI service.
- Backend needs authoritative delegates APIs and delegation command handling.

5. Correlation chain for delegation
- Delegation must preserve one `correlation_id` across:
  - command submission (`POST /delegates/<id>/assign`)
  - backend command acknowledgment
  - emitted delegation event(s)
  - rendered delegation card in timeline

## Practical Rollout Plan

1. Replace stubbed `AlphonseClient` in `alphonse-ui` with real HTTP adapter calls.
2. Add env-driven base URL/token support and hard timeouts.
3. Keep UI contract headers/events unchanged, including delegation event typing.
4. Define delegates backend API contract and map UI routes to it.
5. Add fallback rendering for backend unavailability.
6. Validate with local runtime:
- Start backend: `python -m alphonse.agent.main` in `atrium-server`.
- Start UI: Flask app in `alphonse-ui`.
- Verify `/chat` send + `/ui/presence` status.
- Verify `/delegates` list, details, and assignment flow with correlation trace continuity.

## Boundary Reminder

- `alphonse-ui` is the long-term UI home.
- Any web concerns remaining in `atrium-server/interfaces/http/*` are transitional and should continue moving out.
