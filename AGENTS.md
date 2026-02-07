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

## Versioning

- The UI and Alphonse exchange a `contract_version` string.
- Backward compatibility is required for one minor version.
- On incompatibility, the UI enters read-only safe mode (events + snapshots only).
