from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

from flask import Flask, Response, redirect, render_template, request, url_for

app = Flask(__name__, static_folder="static", template_folder="templates")


@dataclass
class ChatMessage:
    role: str
    content: str
    timestamp: str
    correlation_id: str


class AlphonseClient:
    """Stub adapter for future Alphonse connectivity."""

    def send_message(self, content: str) -> Dict[str, str]:
        correlation_id = f"local-{int(datetime.now().timestamp() * 1000)}"
        return {
            "correlation_id": correlation_id,
            "status": "accepted",
        }

    def presence_snapshot(self) -> Dict[str, str]:
        return {
            "status": "disconnected",
            "note": "Awaiting agent transport",
        }


ALPHONSE = AlphonseClient()
CHAT_MESSAGES: List[ChatMessage] = []
UI_EVENT_TYPES = {
    "presence_update": "ui.event.presence.update",
    "presence_idle": "ui.event.presence.idle",
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
            "items": ["No context linked"],
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


@app.post("/chat/messages")
def chat_messages() -> str:
    content = request.form.get("message", "").strip()
    correlation_id = ensure_correlation_id(request.form.get("correlation_id"))
    if not content:
        response = Response("", status=400)
        response.headers["X-UI-Event-Type"] = UI_EVENT_TYPES["command_failed"]
        return with_contract_headers(response, correlation_id, ok=False)

    ALPHONSE.send_message(content)
    message = ChatMessage(
        role="user",
        content=content,
        timestamp=now_iso(),
        correlation_id=correlation_id,
    )
    CHAT_MESSAGES.append(message)
    response = Response(render_template("partials/chat_message.html", message=message))
    response.headers["X-UI-Event-Type"] = UI_EVENT_TYPES["command_received"]
    return with_contract_headers(response, correlation_id)


@app.get("/chat/timeline")
def chat_timeline() -> str:
    response = Response(render_template("partials/chat_timeline.html", messages=CHAT_MESSAGES))
    response.headers["X-UI-Event-Type"] = UI_EVENT_TYPES["command_received"]
    return with_contract_headers(response, ensure_correlation_id())


@app.get("/ui/presence")
def ui_presence() -> str:
    presence = ALPHONSE.presence_snapshot()
    response = Response(render_template("partials/presence.html", presence=presence, now=now_iso()))
    response.headers["X-UI-Event-Type"] = UI_EVENT_TYPES["presence_update"]
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


if __name__ == "__main__":
    app.run(debug=True, port=5001)
