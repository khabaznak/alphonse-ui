from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional
from urllib import error, request as urlrequest

from flask import Flask, Response, redirect, render_template, request, url_for

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


class AlphonseClient:
    """HTTP adapter for Alphonse agent API."""

    def __init__(self) -> None:
        self.base_url = os.getenv("ALPHONSE_API_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
        token = os.getenv("ALPHONSE_API_TOKEN", "").strip()
        self.api_token = token or None

    def send_message(self, content: str, correlation_id: str) -> Dict[str, object]:
        payload = {
            "text": content,
            "channel": "webui",
            "timestamp": time.time(),
            "correlation_id": correlation_id,
            "metadata": {"source": "alphonse-ui"},
        }
        data = self._request_json("POST", "/agent/message", payload=payload, timeout=5.0)
        if data is None:
            return {"ok": False, "status": "unavailable", "correlation_id": correlation_id}
        return {"ok": True, "status": "accepted", "correlation_id": correlation_id, "data": data}

    def presence_snapshot(self) -> Dict[str, str]:
        data = self._request_json("GET", "/agent/status", payload=None, timeout=3.0)
        if data is None:
            return {
                "status": "disconnected",
                "note": "Alphonse API unavailable",
            }
        runtime = data.get("runtime")
        if isinstance(runtime, dict):
            state = str(runtime.get("state") or runtime.get("status") or "connected")
        else:
            state = "connected"
        return {
            "status": state,
            "note": "Alphonse API connected",
        }

    def _request_json(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, object]],
        timeout: float,
    ) -> Optional[Dict[str, object]]:
        url = f"{self.base_url}{path}"
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
        req = urlrequest.Request(url, data=body, method=method)
        req.add_header("Accept", "application/json")
        if payload is not None:
            req.add_header("Content-Type", "application/json")
        if self.api_token:
            req.add_header("x-alphonse-api-token", self.api_token)
        try:
            with urlrequest.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    data = parsed.get("data")
                    if isinstance(data, dict):
                        return data
                    return parsed
        except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError):
            return None
        return None


ALPHONSE = AlphonseClient()
CHAT_TIMELINE: List[Dict[str, object]] = []
DELEGATES: Dict[str, Delegate] = {
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
                {"label": "Skill Catalog", "path": "/chat"},
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
    delegate_items = [
        f"{delegate.name} ({delegate.status})" for delegate in DELEGATES.values()
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
    delegates = list(DELEGATES.values())
    return render_template("delegates.html", delegates=delegates, **page_context("Delegates"))


@app.get("/delegates/<delegate_id>")
def delegate_details(delegate_id: str) -> str:
    delegate = DELEGATES.get(delegate_id)
    if not delegate:
        return render_template("delegates_detail.html", delegate=None, **page_context("Delegate")), 404
    return render_template("delegates_detail.html", delegate=delegate, **page_context(f"Delegate · {delegate.name}"))


@app.post("/delegates/<delegate_id>/assign")
def delegate_assign(delegate_id: str) -> Response:
    delegate = DELEGATES.get(delegate_id)
    correlation_id = ensure_correlation_id(request.form.get("correlation_id"))
    if not delegate:
        response = Response("Delegate not found", status=404)
        response.headers["X-UI-Event-Type"] = UI_EVENT_TYPES["command_failed"]
        return with_contract_headers(response, correlation_id, ok=False)

    command = request.form.get("command", "").strip()
    if not command:
        response = Response("Missing command", status=400)
        response.headers["X-UI-Event-Type"] = UI_EVENT_TYPES["command_failed"]
        return with_contract_headers(response, correlation_id, ok=False)

    capability = request.form.get("capability", "").strip() or delegate.capabilities[0]
    card = DelegationCard(
        delegate_id=delegate.id,
        delegate_name=delegate.name,
        capability=capability,
        command=command,
        status="assigned",
        timestamp=now_iso(),
        correlation_id=correlation_id,
    )
    CHAT_TIMELINE.append({"type": "delegation", "delegation": card})
    response = Response(render_template("partials/delegation_assignment_result.html", delegation=card))
    response.headers["X-UI-Event-Type"] = UI_EVENT_TYPES["delegation_assigned"]
    return with_contract_headers(response, correlation_id, ok=True)


@app.post("/chat/messages")
def chat_messages() -> str:
    content = request.form.get("message", "").strip()
    correlation_id = ensure_correlation_id(request.form.get("correlation_id"))
    stream_mode = (request.args.get("stream") == "1") or (request.form.get("stream") == "1")
    if not content:
        response = Response("", status=400)
        response.headers["X-UI-Event-Type"] = UI_EVENT_TYPES["command_failed"]
        return with_contract_headers(response, correlation_id, ok=False)

    dispatch = ALPHONSE.send_message(content, correlation_id)
    message = ChatMessage(
        role="user",
        content=content,
        timestamp=now_iso(),
        correlation_id=correlation_id,
    )
    CHAT_TIMELINE.append({"type": "message", "message": message})
    event_type = UI_EVENT_TYPES["command_received"]
    if not dispatch.get("ok"):
        event_type = UI_EVENT_TYPES["command_failed"]
        CHAT_TIMELINE.append(
            {
                "type": "message",
                "message": ChatMessage(
                    role="system",
                    content="Command accepted by UI but Alphonse API is unavailable.",
                    timestamp=now_iso(),
                    correlation_id=correlation_id,
                ),
            }
        )
    response = Response(render_template("partials/chat_timeline.html", entries=CHAT_TIMELINE))
    response.headers["X-UI-Event-Type"] = event_type
    if stream_mode:
        response.headers["X-UI-Stream-Url"] = f"/stream/chat?correlation_id={correlation_id}"
    return with_contract_headers(response, correlation_id)


@app.get("/chat/timeline")
def chat_timeline() -> str:
    response = Response(render_template("partials/chat_timeline.html", entries=CHAT_TIMELINE))
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
