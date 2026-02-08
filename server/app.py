from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

from flask import Flask, Response, redirect, render_template, request, url_for
from server.clients.alphonse_api import AlphonseClient

app = Flask(__name__, static_folder="static", template_folder="templates")


@dataclass
class ChatMessage:
    role: str
    content: str
    timestamp: str
    correlation_id: str


@dataclass
class Delegate:
    id: str
    name: str
    capabilities: List[str]
    contract_version: str
    pricing_model: Optional[str]
    status: str
    last_seen: str


@dataclass
class DelegationCard:
    delegate_id: str
    delegate_name: str
    capability: str
    command: str
    status: str
    timestamp: str
    correlation_id: str


ALPHONSE = AlphonseClient()
CHAT_TIMELINE: List[Dict[str, object]] = []
CHAT_TIMELINE_LOCK = threading.Lock()
LOCAL_DELEGATES: Dict[str, Delegate] = {
    "ops-runner": Delegate(
        id="ops-runner",
        name="Ops Runner",
        capabilities=["incident_triage", "deploy_checks", "status_digest"],
        contract_version="delegate.v1",
        pricing_model="per-task",
        status="available",
        last_seen=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    ),
    "home-sentinel": Delegate(
        id="home-sentinel",
        name="Home Sentinel",
        capabilities=["presence_watch", "device_health", "quiet_hours_guard"],
        contract_version="delegate.v1",
        pricing_model=None,
        status="busy",
        last_seen=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    ),
    "memory-steward": Delegate(
        id="memory-steward",
        name="Memory Steward",
        capabilities=["summary_pack", "habit_snapshot", "timeline_review"],
        contract_version="delegate.v1",
        pricing_model="monthly",
        status="available",
        last_seen=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    ),
}
UI_EVENT_TYPES = {
    "presence_update": "ui.event.presence.update",
    "presence_idle": "ui.event.presence.idle",
    "delegation_assigned": "ui.event.delegation.assigned",
    "command_received": "ui.command.received",
    "command_failed": "ui.command.failed",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def ensure_correlation_id(value: Optional[str] = None) -> str:
    if value and value.strip():
        return value.strip()
    return f"ui-{int(datetime.now().timestamp() * 1000)}"


def _resolve_async_assistant_reply(content: str, correlation_id: str) -> None:
    dispatch = ALPHONSE.send_message(content, correlation_id)
    reply_text = "Alphonse is unavailable."
    if dispatch.get("ok"):
        response_data = dispatch.get("data")
        if isinstance(response_data, dict):
            maybe_message = response_data.get("message")
            if isinstance(maybe_message, str) and maybe_message.strip():
                reply_text = maybe_message
    with CHAT_TIMELINE_LOCK:
        for entry in reversed(CHAT_TIMELINE):
            if entry.get("type") != "message":
                continue
            candidate = entry.get("message")
            if not isinstance(candidate, ChatMessage):
                continue
            if candidate.correlation_id != correlation_id or candidate.role != "assistant":
                continue
            candidate.content = reply_text
            candidate.timestamp = now_iso()
            return
        CHAT_TIMELINE.append(
            {
                "type": "message",
                "message": ChatMessage(
                    role="assistant",
                    content=reply_text,
                    timestamp=now_iso(),
                    correlation_id=correlation_id,
                ),
            }
        )


def with_contract_headers(response: Response, correlation_id: str, ok: bool = True) -> Response:
    response.headers["X-UI-Ok"] = "true" if ok else "false"
    response.headers["X-UI-Correlation-Id"] = correlation_id
    response.headers["X-UI-Timestamp"] = now_iso()
    return response


def nav_sections() -> List[Dict[str, object]]:
    return [
        {
            "title": "Senses",
            "items": [
                {"label": "Signals", "path": "/chat"},
                {"label": "Presence", "path": "/chat"},
            ],
        },
        {
            "title": "Extremities",
            "items": [
                {"label": "Commands", "path": "/chat"},
                {"label": "Ritual Space", "path": "/chat"},
            ],
        },
        {
            "title": "Tools",
            "items": [
                {"label": "Tooling", "path": "/chat"},
            ],
        },
        {
            "title": "Skills",
            "items": [
                {"label": "Gap Proposals", "path": "/skills/gap-proposals"},
                {"label": "Gap Tasks", "path": "/skills/gap-tasks"},
            ],
        },
        {
            "title": "Integrations",
            "items": [
                {"label": "Integrations", "path": "/integrations"},
                {"label": "Delegates", "path": "/delegates"},
            ],
        },
        {
            "title": "Security",
            "items": [
                {"label": "Access", "path": "/chat"},
            ],
        },
        {
            "title": "Memory / Habits",
            "items": [
                {"label": "Memory", "path": "/chat"},
            ],
        },
        {
            "title": "Admin Mode",
            "items": [
                {"label": "Admin", "path": "/admin"},
            ],
        },
        {
            "title": "Dev Mode",
            "items": [
                {"label": "Dev Tools", "path": "/chat"},
            ],
        },
        {
            "title": "Prompts",
            "items": [
                {"label": "Prompt Library", "path": "/chat"},
            ],
        },
    ]


def external_sections() -> List[Dict[str, object]]:
    delegates = get_delegate_registry()
    delegate_items = [
        f"{delegate.name} ({delegate.status})" for delegate in delegates.values()
    ]
    return [
        {
            "title": "Family",
            "items": ["No context linked"],
        },
        {
            "title": "Friends",
            "items": ["No context linked"],
        },
        {
            "title": "Home",
            "items": ["No context linked"],
        },
        {
            "title": "Devices",
            "items": ["No context linked"],
        },
        {
            "title": "Services",
            "items": ["No context linked"],
        },
        {
            "title": "Other Agents",
            "items": ["No context linked"],
        },
        {
            "title": "Delegates",
            "items": delegate_items or ["No delegates linked"],
        },
        {
            "title": "Contexts",
            "items": ["No context linked"],
        },
        {
            "title": "Jobs / Responsibilities",
            "items": ["No context linked"],
        },
    ]


def page_context(title: str, show_context: bool = False) -> Dict[str, object]:
    return {
        "title": title,
        "now": now_iso(),
        "show_context": show_context,
        "nav_sections": nav_sections(),
        "external_sections": external_sections(),
        "path": request.path,
    }


def _query_int(raw: Optional[str], *, default: int, min_value: int, max_value: int) -> int:
    if raw is None or not raw.strip():
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return max(min_value, min(max_value, parsed))


def _parse_delegate(raw: Dict[str, object]) -> Optional[Delegate]:
    delegate_id = str(raw.get("id") or "").strip()
    name = str(raw.get("name") or "").strip()
    if not delegate_id or not name:
        return None
    capabilities_raw = raw.get("capabilities")
    capabilities: List[str] = []
    if isinstance(capabilities_raw, list):
        capabilities = [str(item).strip() for item in capabilities_raw if str(item).strip()]
    contract_version = str(raw.get("contract_version") or "delegate.v1")
    pricing_model = raw.get("pricing_model")
    pricing_model_str = str(pricing_model) if pricing_model is not None else None
    status = str(raw.get("status") or "unknown")
    last_seen = str(raw.get("last_seen") or now_iso())
    return Delegate(
        id=delegate_id,
        name=name,
        capabilities=capabilities,
        contract_version=contract_version,
        pricing_model=pricing_model_str,
        status=status,
        last_seen=last_seen,
    )


def get_delegate_registry() -> Dict[str, Delegate]:
    remote = ALPHONSE.list_delegates()
    if remote:
        parsed = {
            delegate.id: delegate
            for item in remote
            for delegate in [_parse_delegate(item)]
            if delegate is not None
        }
        if parsed:
            return parsed
    return LOCAL_DELEGATES


@app.get("/")
def root() -> Response:
    return redirect(url_for("chat"))


@app.get("/chat")
def chat() -> str:
    show_context = request.args.get("context") == "1"
    return render_template("chat.html", **page_context("Chat", show_context))


@app.get("/admin")
def admin() -> str:
    return render_template("admin.html", **page_context("Admin"))


@app.get("/integrations")
def integrations() -> str:
    return render_template("integrations.html", **page_context("Integrations"))


@app.get("/delegates")
def delegates_list() -> str:
    delegates = list(get_delegate_registry().values())
    return render_template("delegates.html", delegates=delegates, **page_context("Delegates"))


@app.get("/skills/gap-proposals")
def gap_proposals() -> str:
    status = (request.args.get("status") or "pending").strip() or "pending"
    if status not in {"pending", "approved", "rejected", "dispatched", "all"}:
        status = "pending"
    limit = _query_int(request.args.get("limit"), default=50, min_value=1, max_value=500)
    backend_status = None if status == "all" else status
    proposals = ALPHONSE.list_gap_proposals(status=backend_status, limit=limit) or []
    return render_template(
        "gap_proposals.html",
        proposals=proposals,
        selected_status=status,
        selected_limit=limit,
        notice=(request.args.get("notice") or "").strip(),
        error=(request.args.get("error") or "").strip(),
        **page_context("Gap Proposals"),
    )


@app.post("/skills/gap-proposals/coalesce")
def gap_proposals_coalesce() -> Response:
    limit = _query_int(request.form.get("limit"), default=300, min_value=1, max_value=5000)
    min_cluster_size = _query_int(request.form.get("min_cluster_size"), default=2, min_value=1, max_value=50)
    result = ALPHONSE.coalesce_gap_proposals(limit=limit, min_cluster_size=min_cluster_size)
    if not result.get("ok"):
        return redirect(url_for("gap_proposals", status="pending", notice="", error="Coalesce failed"))
    created = int(result.get("created_count") or 0)
    return redirect(
        url_for(
            "gap_proposals",
            status="pending",
            notice=f"Coalesced proposals. Created {created}.",
            error="",
        )
    )


@app.post("/skills/gap-proposals/<proposal_id>/review")
def gap_proposal_review(proposal_id: str) -> Response:
    status = (request.form.get("status") or "").strip().lower()
    if status not in {"approved", "rejected", "pending", "dispatched"}:
        return redirect(url_for("gap_proposals", status="pending", notice="", error="Invalid proposal status"))
    reviewer = (request.form.get("reviewer") or "").strip() or None
    notes = (request.form.get("notes") or "").strip() or None
    result = ALPHONSE.update_gap_proposal(
        proposal_id,
        status=status,
        reviewer=reviewer,
        notes=notes,
    )
    if not result.get("ok"):
        return redirect(
            url_for(
                "gap_proposals",
                status="pending",
                notice="",
                error=f"Failed to update proposal {proposal_id}.",
            )
        )
    return redirect(
        url_for(
            "gap_proposals",
            status=status if status in {"pending", "approved", "rejected", "dispatched"} else "pending",
            notice=f"Proposal {proposal_id} set to {status}.",
            error="",
        )
    )


@app.post("/skills/gap-proposals/<proposal_id>/dispatch")
def gap_proposal_dispatch(proposal_id: str) -> Response:
    task_type = (request.form.get("task_type") or "").strip() or None
    actor = (request.form.get("actor") or "").strip() or None
    result = ALPHONSE.dispatch_gap_proposal(proposal_id, task_type=task_type, actor=actor)
    if not result.get("ok"):
        return redirect(
            url_for(
                "gap_proposals",
                status="approved",
                notice="",
                error=f"Failed to dispatch proposal {proposal_id}.",
            )
        )
    task_id = str(result.get("task_id") or "")
    return redirect(
        url_for(
            "gap_tasks",
            status="open",
            notice=f"Dispatched proposal {proposal_id} to task {task_id}.",
            error="",
        )
    )


@app.get("/skills/gap-tasks")
def gap_tasks() -> str:
    status = (request.args.get("status") or "open").strip() or "open"
    if status not in {"open", "done", "all"}:
        status = "open"
    limit = _query_int(request.args.get("limit"), default=50, min_value=1, max_value=500)
    backend_status = None if status == "all" else status
    tasks = ALPHONSE.list_gap_tasks(status=backend_status, limit=limit) or []
    return render_template(
        "gap_tasks.html",
        tasks=tasks,
        selected_status=status,
        selected_limit=limit,
        notice=(request.args.get("notice") or "").strip(),
        error=(request.args.get("error") or "").strip(),
        **page_context("Gap Tasks"),
    )


@app.post("/skills/gap-tasks/<task_id>/status")
def gap_task_update_status(task_id: str) -> Response:
    status = (request.form.get("status") or "").strip().lower()
    if status not in {"open", "done"}:
        return redirect(url_for("gap_tasks", status="open", notice="", error="Invalid task status"))
    result = ALPHONSE.update_gap_task(task_id, status=status)
    if not result.get("ok"):
        return redirect(
            url_for(
                "gap_tasks",
                status="open",
                notice="",
                error=f"Failed to update task {task_id}.",
            )
        )
    return redirect(
        url_for(
            "gap_tasks",
            status=status,
            notice=f"Task {task_id} set to {status}.",
            error="",
        )
    )


@app.get("/delegates/<delegate_id>")
def delegate_details(delegate_id: str) -> str:
    delegates = get_delegate_registry()
    delegate = delegates.get(delegate_id)
    if not delegate:
        remote = ALPHONSE.get_delegate(delegate_id)
        if isinstance(remote, dict):
            delegate = _parse_delegate(remote)
    if not delegate:
        return render_template("delegates_detail.html", delegate=None, **page_context("Delegate")), 404
    return render_template("delegates_detail.html", delegate=delegate, **page_context(f"Delegate · {delegate.name}"))


@app.post("/delegates/<delegate_id>/assign")
def delegate_assign(delegate_id: str) -> Response:
    delegates = get_delegate_registry()
    delegate = delegates.get(delegate_id)
    correlation_id = ensure_correlation_id(request.form.get("correlation_id"))
    if not delegate:
        remote = ALPHONSE.get_delegate(delegate_id)
        if isinstance(remote, dict):
            delegate = _parse_delegate(remote)
    if not delegate:
        response = Response("Delegate not found in UI or backend API", status=404)
        response.headers["X-UI-Event-Type"] = UI_EVENT_TYPES["command_failed"]
        return with_contract_headers(response, correlation_id, ok=False)

    command = request.form.get("command", "").strip()
    if not command:
        response = Response("Missing command", status=400)
        response.headers["X-UI-Event-Type"] = UI_EVENT_TYPES["command_failed"]
        return with_contract_headers(response, correlation_id, ok=False)

    fallback_capability = delegate.capabilities[0] if delegate.capabilities else "unspecified"
    capability = request.form.get("capability", "").strip() or fallback_capability
    assign_result = ALPHONSE.assign_delegate(delegate.id, capability, command, correlation_id)
    assigned = bool(assign_result.get("ok"))
    card = DelegationCard(
        delegate_id=delegate.id,
        delegate_name=delegate.name,
        capability=capability,
        command=command,
        status="assigned" if assigned else "queued_local",
        timestamp=now_iso(),
        correlation_id=correlation_id,
    )
    with CHAT_TIMELINE_LOCK:
        CHAT_TIMELINE.append({"type": "delegation", "delegation": card})
    response = Response(render_template("partials/delegation_assignment_result.html", delegation=card))
    response.headers["X-UI-Event-Type"] = (
        UI_EVENT_TYPES["delegation_assigned"] if assigned else UI_EVENT_TYPES["command_failed"]
    )
    return with_contract_headers(response, correlation_id, ok=True)


@app.post("/chat/messages")
def chat_messages() -> str:
    content = request.form.get("message", "").strip()
    correlation_id = ensure_correlation_id(request.form.get("correlation_id"))
    if not content:
        response = Response("", status=400)
        response.headers["X-UI-Event-Type"] = UI_EVENT_TYPES["command_failed"]
        return with_contract_headers(response, correlation_id, ok=False)

    with CHAT_TIMELINE_LOCK:
        CHAT_TIMELINE.append(
            {
                "type": "message",
                "message": ChatMessage(
                    role="user",
                    content=content,
                    timestamp=now_iso(),
                    correlation_id=correlation_id,
                ),
            }
        )
        CHAT_TIMELINE.append(
            {
                "type": "message",
                "message": ChatMessage(
                    role="assistant",
                    content="Thinking...",
                    timestamp=now_iso(),
                    correlation_id=correlation_id,
                ),
            }
        )
        entries = list(CHAT_TIMELINE)

    worker = threading.Thread(
        target=_resolve_async_assistant_reply,
        args=(content, correlation_id),
        daemon=True,
    )
    worker.start()

    response = Response(render_template("partials/chat_timeline.html", entries=entries))
    response.headers["X-UI-Event-Type"] = UI_EVENT_TYPES["command_received"]
    return with_contract_headers(response, correlation_id)


@app.get("/chat/timeline")
def chat_timeline() -> str:
    with CHAT_TIMELINE_LOCK:
        entries = list(CHAT_TIMELINE)
    response = Response(render_template("partials/chat_timeline.html", entries=entries))
    response.headers["X-UI-Event-Type"] = UI_EVENT_TYPES["command_received"]
    return with_contract_headers(response, ensure_correlation_id())


@app.get("/ui/presence")
def ui_presence() -> str:
    presence = ALPHONSE.presence_snapshot()
    response = Response(render_template("partials/presence.html", presence=presence, now=now_iso()))
    event_type = UI_EVENT_TYPES["presence_update"]
    if presence.get("status") == "disconnected":
        event_type = UI_EVENT_TYPES["presence_idle"]
    response.headers["X-UI-Event-Type"] = event_type
    return with_contract_headers(response, ensure_correlation_id())


@app.get("/stream/presence")
def stream_presence() -> Response:
    def generate() -> Iterable[str]:
        while True:
            payload = {
                "event_type": UI_EVENT_TYPES["presence_update"],
                "timestamp": now_iso(),
                "presence": ALPHONSE.presence_snapshot(),
            }
            yield "event: presence\n"
            yield f"data: {json.dumps(payload)}\n\n"
            time.sleep(10)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/stream/chat")
def stream_chat() -> Response:
    correlation_id = ensure_correlation_id(request.args.get("correlation_id"))
    with CHAT_TIMELINE_LOCK:
        source_message = next(
            (
                entry["message"]
                for entry in reversed(CHAT_TIMELINE)
                if entry.get("type") == "message"
                and isinstance(entry.get("message"), ChatMessage)
                and entry["message"].correlation_id == correlation_id
            ),
            None,
        )
    source_text = source_message.content if source_message else "Message received."
    reply = f"Alphonse stream placeholder: {source_text}"
    chunks = [part for part in reply.split(" ") if part]

    def generate() -> Iterable[str]:
        yield "event: chat_start\n"
        yield f"data: {json.dumps({'correlation_id': correlation_id, 'timestamp': now_iso()})}\n\n"
        for part in chunks:
            payload = {
                "correlation_id": correlation_id,
                "chunk": f"{part} ",
                "timestamp": now_iso(),
                "event_type": "ui.event.chat.chunk",
            }
            yield "event: chat_chunk\n"
            yield f"data: {json.dumps(payload)}\n\n"
            time.sleep(0.35)
        yield "event: chat_complete\n"
        yield f"data: {json.dumps({'correlation_id': correlation_id, 'timestamp': now_iso(), 'event_type': 'ui.event.chat.complete'})}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    app.run(debug=True, port=5001)
