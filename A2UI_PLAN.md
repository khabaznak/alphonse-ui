# A2UI Integration Plan (Alphonse UI)

## Goal
Enable Alphonse to deliver UI surfaces using the A2UI protocol, starting with a minimal, non-disruptive integration that fits the current Flask + HTMX stack.

## Assumptions
- Current UI is server-rendered (Flask + Jinja) with HTMX for partial swaps.
- Alphonse API remains the source of truth and is accessed via `/agent/*` endpoints.
- We will keep `X-Alphonse-API-Token` header handling consistent with existing API calls.

## Phased Approach

### Phase 0: Discovery and Compatibility
1. Confirm which A2UI version to target (v0.8 public preview vs v0.9 draft).
2. Validate rendering options:
   - Lit Web Components renderer (best fit for non-SPA).
   - Angular renderer (not a fit for this repo).
   - React support is not yet available.
3. Identify the minimal transport for first integration:
   - REST polling for MVP.
   - SSE upgrade for progressive UI updates.

### Phase 1: MVP Surface (Dedicated Page)
1. Add a new route and template in this repo:
   - `GET /a2ui` -> `a2ui.html`
2. Embed A2UI renderer container:
   - Static script include for the Lit renderer bundle.
   - Placeholder surface root (e.g., `<a2ui-surface>` or renderer-specific root element).
3. Implement a lightweight JS bridge:
   - Poll `GET /agent/a2ui/surfaces/{id}` or equivalent.
   - Feed the returned A2UI message(s) to the renderer.
4. Add a minimal toggle in the left nav:
   - "A2UI" entry under Integrations or Dev Mode.

### Phase 2: Server-Side Adapter Option (HTMX-Compatible)
If a pure HTMX integration is desired:
1. Create a server-side A2UI-to-HTML renderer:
   - Translate A2UI JSON payloads into HTML fragments.
   - Define a mapping for A2UI component types to HTML + Tailwind.
2. Serve rendered fragments via standard Flask endpoints:
   - `GET /a2ui/fragment/{surface_id}`
3. Swap with HTMX:
   - `hx-get="/a2ui/fragment/{surface_id}"` and `hx-swap="innerHTML"`
4. Limit initial scope to a small component subset:
   - Text, buttons, lists, simple forms.

### Phase 3: Streaming + Multi-Surface
1. Upgrade transport to SSE:
   - `GET /agent/a2ui/stream/{surface_id}`
2. Handle incremental A2UI messages:
   - Append or patch into the renderer.
3. Support multiple surfaces:
   - Page-level routing for specific surface IDs.

## Proposed Endpoint Contract (Draft)
- `GET /agent/a2ui/surfaces/{surface_id}` -> A2UI JSON payload(s)
- `GET /agent/a2ui/stream/{surface_id}` -> SSE stream (optional)
- Authentication via `X-Alphonse-API-Token`

## Risks and Open Questions
- A2UI message schema stability between v0.8 and v0.9.
- Whether Alphonse will emit full A2UI surfaces or incremental diffs.
- Any custom components that require bespoke HTML mappings.

## Deliverables for Phase 1
- New `a2ui.html` template and route.
- Renderer bootstrapping JS.
- Polling loop to fetch A2UI payloads.
- Nav entry and simple styling.

