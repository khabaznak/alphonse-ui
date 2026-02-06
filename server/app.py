from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Iterable

from flask import Flask, Response, render_template, request

app = Flask(__name__, static_folder="static", template_folder="templates")


NAV_ITEMS = [
    {"label": "Threshold", "path": "/"},
    {"label": "Command Console", "path": "/commands"},
    {"label": "Signals", "path": "/signals"},
    {"label": "Ritual Space", "path": "/ritual"},
    {"label": "Presence", "path": "/presence"},
    {"label": "Events", "path": "/events"},
    {"label": "Snapshots", "path": "/snapshots"},
    {"label": "Voice / Video", "path": "/voice"},
    {"label": "System", "path": "/system"},
]


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def page_context(title: str) -> dict:
    return {
        "title": title,
        "nav_items": NAV_ITEMS,
        "now": now_iso(),
        "path": request.path,
    }


@app.get("/")
def threshold() -> str:
    return render_template("threshold.html", **page_context("Threshold"))


@app.get("/commands")
def commands() -> str:
    return render_template("commands.html", **page_context("Command Console"))


@app.post("/commands/submit")
def commands_submit() -> str:
    payload = request.form.get("command", "").strip()
    return render_template(
        "partials/command_result.html",
        command=payload,
        received_at=now_iso(),
    )


@app.get("/signals")
def signals() -> str:
    return render_template("signals.html", **page_context("Signals"))


@app.post("/signals/submit")
def signals_submit() -> str:
    payload = request.form.get("signal", "").strip()
    return render_template(
        "partials/signal_result.html",
        signal=payload,
        received_at=now_iso(),
    )


@app.get("/ritual")
def ritual() -> str:
    return render_template("ritual.html", **page_context("Ritual Space"))


@app.get("/presence")
def presence() -> str:
    return render_template("presence.html", **page_context("Presence"))


@app.get("/events")
def events() -> str:
    return render_template("events.html", **page_context("Events Archive"))


@app.get("/snapshots")
def snapshots() -> str:
    return render_template("snapshots.html", **page_context("Snapshots"))


@app.get("/voice")
def voice() -> str:
    return render_template("voice.html", **page_context("Voice / Video"))


@app.get("/system")
def system() -> str:
    return render_template("system.html", **page_context("System"))


# HTMX fragments

@app.get("/fragments/status")
def fragment_status() -> str:
    return render_template("partials/status.html", now=now_iso())


@app.get("/fragments/events")
def fragment_events() -> str:
    return render_template("partials/events.html", now=now_iso())


@app.get("/fragments/snapshots")
def fragment_snapshots() -> str:
    return render_template("partials/snapshots.html", now=now_iso())


@app.get("/fragments/commands")
def fragment_commands() -> str:
    return render_template("partials/commands.html")


@app.get("/fragments/signals")
def fragment_signals() -> str:
    return render_template("partials/signals.html")


@app.get("/fragments/ritual")
def fragment_ritual() -> str:
    return render_template("partials/ritual.html")


@app.get("/fragments/voice")
def fragment_voice() -> str:
    return render_template("partials/voice.html")


@app.get("/fragments/system")
def fragment_system() -> str:
    # Placeholder health payload until agent transport is wired.
    health = {
        "transport": "Disconnected",
        "contract_version": "v0 (draft)",
        "ui_build": "skeleton-0.1",
        "last_check": now_iso(),
    }
    return render_template("partials/system.html", health=health)


# Client islands endpoints

@app.post("/chat/send")
def chat_send() -> Response:
    message = request.json.get("message", "") if request.is_json else ""
    payload = {
        "type": "chat_ack",
        "received_at": now_iso(),
        "message": message,
    }
    return Response(json.dumps(payload), mimetype="application/json")


@app.get("/stream/presence")
def stream_presence() -> Response:
    def generate() -> Iterable[str]:
        counter = 0
        while True:
            counter += 1
            event = {
                "type": "presence_ping",
                "sequence": counter,
                "timestamp": now_iso(),
            }
            yield f"event: presence\n"
            yield f"data: {json.dumps(event)}\n\n"
            time.sleep(5)

    return Response(generate(), mimetype="text/event-stream")


@app.get("/stream/chat")
def stream_chat() -> Response:
    def generate() -> Iterable[str]:
        counter = 0
        while True:
            counter += 1
            event = {
                "type": "chat_stream_ping",
                "sequence": counter,
                "timestamp": now_iso(),
            }
            yield f"event: chat\n"
            yield f"data: {json.dumps(event)}\n\n"
            time.sleep(10)

    return Response(generate(), mimetype="text/event-stream")


if __name__ == "__main__":
    app.run(debug=True, port=5001)
