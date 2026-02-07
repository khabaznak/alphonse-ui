# Agent–UI Contract (Draft)

## Roles

- **Extremity**: explicit user actions transmitted as commands.
- **Sense**: passive inputs transmitted as signals.
- **Ritual Space**: conversation and visibility; the UI renders events and snapshots.

## Communication Primitives

- **command**: explicit, intentional action from the user.
- **signal**: passive or ambiguous input, never interpreted by the UI.
- **event**: emitted by Alphonse to describe outcomes or changes.
- **state_snapshot**: authoritative state view from Alphonse.

### Examples (JSON)

Command
```json
{
  "type": "command",
  "name": "send_message",
  "payload": {
    "message": "Send status report to Alex"
  },
  "correlation_id": "ui-1707243250123",
  "timestamp": "2026-02-07T09:14:10-05:00"
}
```

Signal
```json
{
  "type": "signal",
  "name": "ambient_note",
  "payload": {
    "text": "Office door opened"
  },
  "correlation_id": "ui-1707243250456",
  "timestamp": "2026-02-07T09:14:12-05:00"
}
```

Event
```json
{
  "type": "event",
  "name": "ui.event.presence.update",
  "payload": {
    "status": "idle",
    "note": "Awaiting agent transport"
  },
  "correlation_id": "ui-1707243250789",
  "timestamp": "2026-02-07T09:14:15-05:00"
}
```

State Snapshot
```json
{
  "type": "state_snapshot",
  "name": "agent.runtime",
  "payload": {
    "mode": "observer",
    "transport": "disconnected"
  },
  "correlation_id": "ui-1707243250999",
  "timestamp": "2026-02-07T09:14:17-05:00"
}
```

Delegation Command
```json
{
  "type": "command",
  "name": "delegate.assign",
  "payload": {
    "delegate_id": "ops-runner",
    "capability": "incident_triage",
    "command": "Triage overnight alert spikes and summarize impact"
  },
  "correlation_id": "ui-1707243251333",
  "timestamp": "2026-02-07T09:14:20-05:00"
}
```

Delegation Event
```json
{
  "type": "event",
  "name": "ui.event.delegation.assigned",
  "payload": {
    "delegate_id": "ops-runner",
    "status": "assigned"
  },
  "correlation_id": "ui-1707243251333",
  "timestamp": "2026-02-07T09:14:21-05:00"
}
```

## Responsibility Rules

- The UI never decides, classifies intent, or resolves ambiguity.
- The UI never owns durable state or memory.
- Alphonse owns all cognition, memory, planning, and persistence.
- The UI only renders state snapshots and events received from Alphonse.

## Failure Semantics

- **Command failure**: UI shows the error alongside the originating command and its `correlation_id`.
- **Signal failure**: UI shows the error without reclassifying the signal.
- **Event stream failure**: UI shows a paused indicator and last-received timestamp.
- **Snapshot failure**: UI continues showing the last known snapshot with a stale indicator.
- **Audit**: UI must retain the `correlation_id` and display it for operator tracing.

## API Contract Headers

Every response from the UI API returns contract metadata in headers:

- `X-UI-Ok`: `"true"` or `"false"`.
- `X-UI-Correlation-Id`: correlation identifier for tracing.
- `X-UI-Timestamp`: ISO8601 timestamp.

For command-related responses, `X-UI-Event-Type` is included and set to `ui.command.*` or `ui.event.*`.

Correlation trace rule:
- A single `correlation_id` starts on the command and must be preserved across all resulting events and UI cards.
- Delegation flow example: `delegate.assign` command -> `ui.command.received` -> `ui.event.delegation.assigned` (all with same `correlation_id`).

## Versioning

- The UI and Alphonse exchange a `contract_version` string.
- Backward compatibility is required for one minor version.
- On incompatibility, the UI enters read-only safe mode (events + snapshots only).

## Minimal Event Types

Presence
- `ui.event.presence.update`
- `ui.event.presence.idle`

Commands
- `ui.command.received`
- `ui.command.failed`

Delegation
- `ui.event.delegation.assigned`
