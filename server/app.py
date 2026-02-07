from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

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


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


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
    if not content:
        return "", 204

    ack = ALPHONSE.send_message(content)
    message = ChatMessage(
        role="user",
        content=content,
        timestamp=now_iso(),
        correlation_id=ack["correlation_id"],
    )
    CHAT_MESSAGES.append(message)
    return render_template("partials/chat_message.html", message=message)


@app.get("/chat/timeline")
def chat_timeline() -> str:
    return render_template("partials/chat_timeline.html", messages=CHAT_MESSAGES)


@app.get("/ui/presence")
def ui_presence() -> str:
    presence = ALPHONSE.presence_snapshot()
    return render_template("partials/presence.html", presence=presence, now=now_iso())


if __name__ == "__main__":
    app.run(debug=True, port=5001)
