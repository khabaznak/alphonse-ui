from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

from flask import Flask, Response, jsonify, redirect, render_template, request, url_for
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


def _resolve_async_assistant_reply(
    content: str,
    correlation_id: str,
    args: Optional[Dict[str, object]] = None,
) -> None:
    dispatch = ALPHONSE.send_message(content, correlation_id, args=args)
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


def _resolve_async_asset_assistant_reply(
    *,
    correlation_id: str,
    asset_id: str,
    audio_mode: str,
    provider: str,
    channel: str,
) -> None:
    app.logger.info(
        "voice.message_payload correlation_id=%s provider=%s channel=%s content.type=asset content.assets[0].asset_id=%s content.assets[0].kind=audio controls.audio_mode=%s",
        correlation_id,
        provider,
        channel,
        asset_id,
        audio_mode,
    )
    dispatch = ALPHONSE.send_asset_message(
        correlation_id=correlation_id,
        asset_id=asset_id,
        audio_mode=audio_mode,
        provider=provider,
        channel=channel,
        kind="audio",
    )
    app.logger.info(
        "voice.message_dispatched correlation_id=%s provider=%s channel=%s asset_id=%s ok=%s",
        correlation_id,
        provider,
        channel,
        asset_id,
        bool(dispatch.get("ok")),
    )

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


def _append_chat_turn(user_content: str, correlation_id: str) -> List[Dict[str, object]]:
    with CHAT_TIMELINE_LOCK:
        CHAT_TIMELINE.append(
            {
                "type": "message",
                "message": ChatMessage(
                    role="user",
                    content=user_content,
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
        return list(CHAT_TIMELINE)


def _parse_audio_mode(value: Optional[str]) -> str:
    normalized = (value or "").strip().lower()
    if normalized in {"local_audio", "local", "true", "1", "on"}:
        return "local_audio"
    return "none"


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
            "title": "Abilities",
            "items": [
                {"label": "Abilities", "path": "/abilities"},
                {"label": "Gap Proposals", "path": "/skills/gap-proposals"},
                {"label": "Gap Tasks", "path": "/skills/gap-tasks"},
            ],
        },
        {
            "title": "Integrations",
            "items": [
                {"label": "Integrations", "path": "/integrations"},
                {"label": "Users", "path": "/users"},
                {"label": "Delegates", "path": "/delegates"},
                {"label": "Onboarding Profiles", "path": "/onboarding/profiles"},
                {"label": "Locations", "path": "/locations"},
                {"label": "Device Locations", "path": "/device-locations"},
                {"label": "API Keys", "path": "/tool-configs"},
                {"label": "Telegram Invites", "path": "/telegram/invites"},
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
                {"label": "Prompt Library", "path": "/prompts"},
            ],
        },
    ]


def external_sections() -> List[Dict[str, object]]:
    delegates = get_delegate_registry()
    delegate_items = [
        f"{delegate.name} ({delegate.status})" for delegate in delegates.values()
    ]
    users = ALPHONSE.list_users(active_only=False, limit=200) or []
    user_items = []
    for user in users:
        if not isinstance(user, dict):
            continue
        label = (
            str(
                user.get("display_name")
                or user.get("name")
                or user.get("email")
                or user.get("principal_id")
                or user.get("user_id")
                or "unknown-user"
            )
        ).strip()
        role = str(user.get("primary_role") or user.get("role") or "").strip()
        relationship = str(user.get("relationship") or "").strip()
        meta_bits = [value for value in (role, relationship) if value]
        if meta_bits:
            label = f"{label} · {' / '.join(meta_bits)}"
        if user.get("is_admin") is True:
            label = f"{label} · admin"
        user_items.append(label or "unknown-user")
    return [
        {
            "title": "Users",
            "items": user_items or ["No users linked"],
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


def page_context(title: str, show_context: bool = False, subtitle: Optional[str] = None) -> Dict[str, object]:
    return {
        "title": title,
        "subtitle": subtitle or "Server-rendered HTMX control surface",
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


def _parse_json_dict(raw: str) -> Optional[Dict[str, object]]:
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _parse_json_list(raw: str) -> Optional[List[object]]:
    if not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    return parsed


def _parse_int(raw: str) -> Optional[int]:
    if raw is None:
        return None
    if not raw.strip():
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _parse_float(raw: str) -> Optional[float]:
    if not raw.strip():
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_bool(raw: str, default: bool = False) -> bool:
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


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


@app.get("/tool-configs")
def tool_configs() -> str:
    limit = _query_int(request.args.get("limit"), default=100, min_value=1, max_value=1000)
    tool_key = (request.args.get("tool_key") or "").strip()
    active_only_raw = (request.args.get("active_only") or "").strip()
    active_only = _parse_bool(active_only_raw, default=False) if active_only_raw else None
    configs = ALPHONSE.list_tool_configs(tool_key=tool_key or None, active_only=active_only, limit=limit) or []
    selected_config_id = (request.args.get("config_id") or "").strip()
    selected_config = None
    if selected_config_id:
        selected_config = ALPHONSE.get_tool_config(selected_config_id)
    return render_template(
        "tool_configs.html",
        configs=configs,
        selected_config_id=selected_config_id,
        selected_config=selected_config,
        selected_limit=limit,
        selected_tool_key=tool_key,
        selected_active_only=active_only_raw,
        notice=(request.args.get("notice") or "").strip(),
        error=(request.args.get("error") or "").strip(),
        **page_context("Tool Configs"),
    )


@app.post("/tool-configs")
def tool_configs_create() -> Response:
    tool_key = (request.form.get("tool_key") or "").strip()
    name = (request.form.get("name") or "").strip()
    api_key = (request.form.get("api_key") or "").strip()
    is_active = _parse_bool(request.form.get("is_active") or "true", default=True)
    config_extra_raw = (request.form.get("config_json") or "").strip()
    config_extra = _parse_json_dict(config_extra_raw) if config_extra_raw else {}
    if config_extra is None:
        return redirect(url_for("tool_configs", notice="", error="config_json must be a JSON object"))
    if not tool_key or not name or not api_key:
        return redirect(url_for("tool_configs", notice="", error="tool_key, name, and api_key are required"))
    config_payload = {"api_key": api_key}
    config_payload.update(config_extra)
    payload = {
        "tool_key": tool_key,
        "name": name,
        "config": config_payload,
        "is_active": is_active,
    }
    result = ALPHONSE.create_tool_config(payload)
    if not result.get("ok"):
        return redirect(url_for("tool_configs", notice="", error=f"Failed to create tool config for {tool_key}"))
    return redirect(url_for("tool_configs", notice=f"Created tool config for {tool_key}", error=""))


@app.post("/tool-configs/<path:config_id>/delete")
def tool_configs_delete(config_id: str) -> Response:
    result = ALPHONSE.delete_tool_config(config_id)
    if not result.get("ok"):
        return redirect(url_for("tool_configs", notice="", error=f"Tool config {config_id} not found"))
    return redirect(url_for("tool_configs", notice=f"Deleted tool config {config_id}", error=""))


@app.get("/onboarding/profiles")
def onboarding_profiles() -> str:
    limit = _query_int(request.args.get("limit"), default=100, min_value=1, max_value=1000)
    state = (request.args.get("state") or "").strip()
    profiles = ALPHONSE.list_onboarding_profiles(state=state or None, limit=limit) or []
    selected_principal_id = (request.args.get("principal_id") or "").strip()
    selected_profile = None
    if selected_principal_id:
        selected_profile = ALPHONSE.get_onboarding_profile(selected_principal_id)
    return render_template(
        "onboarding_profiles.html",
        profiles=profiles,
        selected_principal_id=selected_principal_id,
        selected_profile=selected_profile,
        selected_limit=limit,
        selected_state=state,
        notice=(request.args.get("notice") or "").strip(),
        error=(request.args.get("error") or "").strip(),
        **page_context("Onboarding Profiles"),
    )


@app.post("/onboarding/profiles")
def onboarding_profiles_create() -> Response:
    principal_id = (request.form.get("principal_id") or "").strip()
    state = (request.form.get("state") or "").strip()
    primary_role = (request.form.get("primary_role") or "").strip()
    next_steps_raw = (request.form.get("next_steps") or "").strip()
    resume_token = (request.form.get("resume_token") or "").strip()
    completed_at = (request.form.get("completed_at") or "").strip()
    next_steps = []
    if next_steps_raw:
        if next_steps_raw.lstrip().startswith("["):
            parsed_steps = _parse_json_list(next_steps_raw)
            if parsed_steps is None:
                return redirect(url_for("onboarding_profiles", notice="", error="next_steps must be JSON array or CSV"))
            next_steps = [str(item) for item in parsed_steps]
        else:
            next_steps = [item.strip() for item in next_steps_raw.split(",") if item.strip()]
    if not principal_id:
        return redirect(url_for("onboarding_profiles", notice="", error="principal_id is required"))
    payload = {
        "principal_id": principal_id,
        "state": state or "in_progress",
        "primary_role": primary_role or None,
        "next_steps": next_steps,
        "resume_token": resume_token or None,
        "completed_at": completed_at or None,
    }
    result = ALPHONSE.create_onboarding_profile(payload)
    if not result.get("ok"):
        return redirect(url_for("onboarding_profiles", notice="", error=f"Failed to create profile {principal_id}"))
    return redirect(url_for("onboarding_profiles", notice=f"Created profile {principal_id}", error=""))


@app.post("/onboarding/profiles/<path:principal_id>/delete")
def onboarding_profiles_delete(principal_id: str) -> Response:
    result = ALPHONSE.delete_onboarding_profile(principal_id)
    if not result.get("ok"):
        return redirect(url_for("onboarding_profiles", notice="", error=f"Profile {principal_id} not found"))
    return redirect(url_for("onboarding_profiles", notice=f"Deleted profile {principal_id}", error=""))


@app.get("/locations")
def locations() -> str:
    limit = _query_int(request.args.get("limit"), default=100, min_value=1, max_value=1000)
    principal_id = (request.args.get("principal_id") or "").strip()
    label = (request.args.get("label") or "").strip()
    active_only_raw = (request.args.get("active_only") or "").strip()
    active_only = _parse_bool(active_only_raw, default=False) if active_only_raw else None
    items = ALPHONSE.list_locations(
        principal_id=principal_id or None,
        label=label or None,
        active_only=active_only,
        limit=limit,
    ) or []
    selected_location_id = (request.args.get("location_id") or "").strip()
    selected_location = None
    if selected_location_id:
        selected_location = ALPHONSE.get_location(selected_location_id)
    return render_template(
        "locations.html",
        locations=items,
        selected_location_id=selected_location_id,
        selected_location=selected_location,
        selected_limit=limit,
        selected_principal_id=principal_id,
        selected_label=label,
        selected_active_only=active_only_raw,
        notice=(request.args.get("notice") or "").strip(),
        error=(request.args.get("error") or "").strip(),
        **page_context("Locations"),
    )


@app.post("/locations")
def locations_create() -> Response:
    principal_id = (request.form.get("principal_id") or "").strip()
    label = (request.form.get("label") or "").strip()
    address_text = (request.form.get("address_text") or "").strip()
    latitude_raw = (request.form.get("latitude") or "").strip()
    longitude_raw = (request.form.get("longitude") or "").strip()
    source = (request.form.get("source") or "").strip()
    confidence_raw = (request.form.get("confidence") or "").strip()
    is_active = _parse_bool(request.form.get("is_active") or "true", default=True)
    location_id = (request.form.get("location_id") or "").strip()
    latitude = _parse_float(latitude_raw)
    longitude = _parse_float(longitude_raw)
    confidence = _parse_float(confidence_raw) if confidence_raw else None
    if not principal_id or not label or latitude is None or longitude is None:
        return redirect(url_for("locations", notice="", error="principal_id, label, latitude, longitude are required"))
    payload = {
        "location_id": location_id or None,
        "principal_id": principal_id,
        "label": label,
        "address_text": address_text or None,
        "latitude": latitude,
        "longitude": longitude,
        "source": source or "user",
        "confidence": confidence,
        "is_active": is_active,
    }
    result = ALPHONSE.create_location(payload)
    if not result.get("ok"):
        return redirect(url_for("locations", notice="", error=f"Failed to create location {location_id}"))
    return redirect(url_for("locations", notice=f"Created location {location_id or label}", error=""))


@app.post("/locations/<path:location_id>/delete")
def locations_delete(location_id: str) -> Response:
    result = ALPHONSE.delete_location(location_id)
    if not result.get("ok"):
        return redirect(url_for("locations", notice="", error=f"Location {location_id} not found"))
    return redirect(url_for("locations", notice=f"Deleted location {location_id}", error=""))


@app.get("/device-locations")
def device_locations() -> str:
    limit = _query_int(request.args.get("limit"), default=100, min_value=1, max_value=1000)
    principal_id = (request.args.get("principal_id") or "").strip()
    device_id = (request.args.get("device_id") or "").strip()
    items = ALPHONSE.list_device_locations(
        principal_id=principal_id or None,
        device_id=device_id or None,
        limit=limit,
    ) or []
    return render_template(
        "device_locations.html",
        device_locations=items,
        selected_principal_id=principal_id,
        selected_device_id=device_id,
        selected_limit=limit,
        notice=(request.args.get("notice") or "").strip(),
        error=(request.args.get("error") or "").strip(),
        **page_context("Device Locations"),
    )


@app.post("/device-locations")
def device_locations_create() -> Response:
    principal_id = (request.form.get("principal_id") or "").strip()
    device_id = (request.form.get("device_id") or "").strip()
    latitude_raw = (request.form.get("latitude") or "").strip()
    longitude_raw = (request.form.get("longitude") or "").strip()
    accuracy_raw = (request.form.get("accuracy_meters") or "").strip()
    source = (request.form.get("source") or "").strip()
    observed_at = (request.form.get("observed_at") or "").strip()
    metadata_raw = (request.form.get("metadata_json") or "").strip()
    metadata = _parse_json_dict(metadata_raw) if metadata_raw else {}
    if metadata is None:
        return redirect(url_for("device_locations", notice="", error="metadata_json must be a JSON object"))
    latitude = _parse_float(latitude_raw)
    longitude = _parse_float(longitude_raw)
    accuracy = _parse_float(accuracy_raw) if accuracy_raw else None
    if not principal_id or not device_id or latitude is None or longitude is None:
        return redirect(url_for("device_locations", notice="", error="principal_id, device_id, latitude, longitude are required"))
    payload = {
        "principal_id": principal_id,
        "device_id": device_id,
        "latitude": latitude,
        "longitude": longitude,
        "accuracy_meters": accuracy,
        "source": source or "alphonse_link",
        "observed_at": observed_at or None,
        "metadata": metadata,
    }
    result = ALPHONSE.create_device_location(payload)
    if not result.get("ok"):
        return redirect(url_for("device_locations", notice="", error="Failed to create device-location mapping"))
    return redirect(url_for("device_locations", notice="Created device-location mapping", error=""))


@app.get("/users")
def users() -> str:
    limit = _query_int(request.args.get("limit"), default=200, min_value=1, max_value=1000)
    active_only_raw = (request.args.get("active_only") or "").strip()
    active_only = _parse_bool(active_only_raw, default=False) if active_only_raw else None
    items = ALPHONSE.list_users(active_only=active_only, limit=limit) or []
    selected_user_id = (request.args.get("user_id") or "").strip()
    selected_user = None
    if selected_user_id:
        selected_user = ALPHONSE.get_user(selected_user_id)
    return render_template(
        "users.html",
        users=items,
        selected_user_id=selected_user_id,
        selected_user=selected_user,
        selected_limit=limit,
        selected_active_only=active_only_raw,
        notice=(request.args.get("notice") or "").strip(),
        error=(request.args.get("error") or "").strip(),
        **page_context("Users"),
    )


@app.post("/users")
def users_create() -> Response:
    user_id = (request.form.get("user_id") or "").strip()
    principal_id = (request.form.get("principal_id") or "").strip()
    display_name = (request.form.get("display_name") or "").strip()
    role = (request.form.get("role") or "").strip()
    relationship = (request.form.get("relationship") or "").strip()
    is_admin = _parse_bool(request.form.get("is_admin") or "false", default=False)
    is_active = _parse_bool(request.form.get("is_active") or "true", default=True)
    onboarded_at = (request.form.get("onboarded_at") or "").strip()
    if not user_id or not principal_id:
        return redirect(url_for("users", notice="", error="user_id and principal_id are required"))
    payload = {
        "user_id": user_id,
        "principal_id": principal_id,
        "display_name": display_name or None,
        "role": role or None,
        "relationship": relationship or None,
        "is_admin": is_admin,
        "is_active": is_active,
        "onboarded_at": onboarded_at or None,
    }
    result = ALPHONSE.create_user(payload)
    if not result.get("ok"):
        return redirect(url_for("users", notice="", error=f"Failed to create user {user_id}"))
    return redirect(url_for("users", notice=f"Created user {user_id}", error=""))


@app.post("/users/<path:user_id>/update")
def users_update(user_id: str) -> Response:
    role = (request.form.get("role") or "").strip()
    relationship = (request.form.get("relationship") or "").strip()
    is_admin_raw = (request.form.get("is_admin") or "").strip()
    updates: Dict[str, object] = {}
    if role:
        updates["role"] = role
    if relationship:
        updates["relationship"] = relationship
    if is_admin_raw:
        updates["is_admin"] = _parse_bool(is_admin_raw, default=False)
    if not updates:
        return redirect(url_for("users", notice="", error="No updates provided"))
    result = ALPHONSE.update_user(user_id, updates)
    if not result.get("ok"):
        return redirect(url_for("users", notice="", error=f"Failed to update user {user_id}"))
    return redirect(url_for("users", notice=f"Updated user {user_id}", error=""))


@app.post("/users/<path:user_id>/delete")
def users_delete(user_id: str) -> Response:
    result = ALPHONSE.delete_user(user_id)
    if not result.get("ok"):
        return redirect(url_for("users", notice="", error=f"User {user_id} not found"))
    return redirect(url_for("users", notice=f"Deleted user {user_id}", error=""))


@app.get("/telegram/invites")
def telegram_invites() -> str:
    limit = _query_int(request.args.get("limit"), default=200, min_value=1, max_value=1000)
    status = (request.args.get("status") or "").strip()
    invites = ALPHONSE.list_telegram_invites(status=status or None, limit=limit) or []
    selected_chat_id = (request.args.get("chat_id") or "").strip()
    selected_invite = None
    if selected_chat_id:
        selected_invite = ALPHONSE.get_telegram_invite(selected_chat_id)
    return render_template(
        "telegram_invites.html",
        invites=invites,
        selected_chat_id=selected_chat_id,
        selected_invite=selected_invite,
        selected_limit=limit,
        selected_status=status,
        notice=(request.args.get("notice") or "").strip(),
        error=(request.args.get("error") or "").strip(),
        **page_context("Telegram Invites"),
    )


@app.post("/telegram/invites/<path:chat_id>/status")
def telegram_invite_status(chat_id: str) -> Response:
    status = (request.form.get("status") or "").strip()
    if not status:
        return redirect(url_for("telegram_invites", notice="", error="status is required"))
    result = ALPHONSE.update_telegram_invite_status(chat_id, status)
    if not result.get("ok"):
        return redirect(url_for("telegram_invites", notice="", error=f"Failed to update invite {chat_id}"))
    return redirect(url_for("telegram_invites", notice=f"Updated invite {chat_id}", error=""))


@app.get("/prompts")
def prompts() -> str:
    key = (request.args.get("key") or "").strip()
    purpose = (request.args.get("purpose") or "").strip()
    enabled_only_raw = (request.args.get("enabled_only") or "").strip()
    enabled_only = _parse_bool(enabled_only_raw, default=False) if enabled_only_raw else None
    limit_raw = (request.args.get("limit") or "").strip()
    limit = _parse_int(limit_raw) if limit_raw else None
    items = ALPHONSE.list_prompts(
        key=key or None,
        enabled_only=enabled_only,
        purpose=purpose or None,
        limit=limit,
    ) or []
    selected_template_id = (request.args.get("template_id") or "").strip()
    selected_template = None
    if selected_template_id:
        selected_template = ALPHONSE.get_prompt(selected_template_id)
    return render_template(
        "prompts.html",
        prompts=items,
        selected_template_id=selected_template_id,
        selected_template=selected_template,
        selected_key=key,
        selected_purpose=purpose,
        selected_enabled_only=enabled_only_raw,
        selected_limit=limit_raw,
        notice=(request.args.get("notice") or "").strip(),
        error=(request.args.get("error") or "").strip(),
        **page_context("Prompt Library"),
    )


@app.post("/prompts")
def prompts_create() -> Response:
    key = (request.form.get("key") or "").strip()
    locale = (request.form.get("locale") or "").strip()
    address_style = (request.form.get("address_style") or "").strip()
    tone = (request.form.get("tone") or "").strip()
    channel = (request.form.get("channel") or "").strip()
    variant = (request.form.get("variant") or "").strip()
    policy_tier = (request.form.get("policy_tier") or "").strip()
    purpose = (request.form.get("purpose") or "").strip()
    template = (request.form.get("template") or "").strip()
    enabled = _parse_bool(request.form.get("enabled") or "true", default=True)
    priority_raw = (request.form.get("priority") or "").strip()
    priority = _parse_int(priority_raw) if priority_raw else 0
    changed_by = (request.form.get("changed_by") or "").strip()
    reason = (request.form.get("reason") or "").strip()
    if not key or not template:
        return redirect(url_for("prompts", notice="", error="key and template are required"))
    payload = {
        "key": key,
        "locale": locale or "any",
        "address_style": address_style or "any",
        "tone": tone or "any",
        "channel": channel or "any",
        "variant": variant or "default",
        "policy_tier": policy_tier or "safe",
        "purpose": purpose or "routing",
        "template": template,
        "enabled": enabled,
        "priority": priority,
        "changed_by": changed_by or "admin",
        "reason": reason or "manual_update",
    }
    result = ALPHONSE.create_prompt(payload)
    if not result.get("ok"):
        return redirect(url_for("prompts", notice="", error=f"Failed to create prompt {key}"))
    return redirect(url_for("prompts", notice=f"Created prompt {key}", error=""))


@app.post("/prompts/<path:template_id>/update")
def prompts_update(template_id: str) -> Response:
    template = (request.form.get("template") or "").strip()
    enabled_raw = (request.form.get("enabled") or "").strip()
    priority_raw = (request.form.get("priority") or "").strip()
    purpose = (request.form.get("purpose") or "").strip()
    changed_by = (request.form.get("changed_by") or "").strip()
    reason = (request.form.get("reason") or "").strip()
    updates: Dict[str, object] = {}
    if template:
        updates["template"] = template
    if enabled_raw:
        updates["enabled"] = _parse_bool(enabled_raw, default=False)
    if priority_raw:
        parsed_priority = _parse_int(priority_raw)
        if parsed_priority is None:
            return redirect(url_for("prompts", notice="", error=f"Invalid priority for {template_id}"))
        updates["priority"] = parsed_priority
    if purpose:
        updates["purpose"] = purpose
    if changed_by:
        updates["changed_by"] = changed_by
    if reason:
        updates["reason"] = reason
    if not updates:
        return redirect(url_for("prompts", notice="", error=f"No updates provided for {template_id}"))
    result = ALPHONSE.update_prompt(template_id, updates)
    if not result.get("ok"):
        return redirect(url_for("prompts", notice="", error=f"Failed to update {template_id}"))
    return redirect(url_for("prompts", notice=f"Updated prompt {template_id}", error=""))


@app.post("/prompts/<path:template_id>/rollback")
def prompts_rollback(template_id: str) -> Response:
    version_raw = (request.form.get("version") or "").strip()
    changed_by = (request.form.get("changed_by") or "").strip()
    reason = (request.form.get("reason") or "").strip()
    version = _parse_int(version_raw) if version_raw else None
    if version is None:
        return redirect(url_for("prompts", notice="", error=f"version is required for {template_id}"))
    payload = {
        "version": version,
        "changed_by": changed_by or "admin",
        "reason": reason or "rollback",
    }
    result = ALPHONSE.rollback_prompt(template_id, payload)
    if not result.get("ok"):
        return redirect(url_for("prompts", notice="", error=f"Failed to rollback {template_id}"))
    return redirect(url_for("prompts", notice=f"Rolled back prompt {template_id}", error=""))


@app.post("/prompts/<path:template_id>/delete")
def prompts_delete(template_id: str) -> Response:
    result = ALPHONSE.delete_prompt(template_id)
    if not result.get("ok"):
        return redirect(url_for("prompts", notice="", error=f"Prompt {template_id} not found"))
    return redirect(url_for("prompts", notice=f"Deleted prompt {template_id}", error=""))


@app.get("/delegates")
def delegates_list() -> str:
    delegates = list(get_delegate_registry().values())
    return render_template("delegates.html", delegates=delegates, **page_context("Delegates"))


@app.get("/abilities")
def abilities() -> str:
    enabled_filter = (request.args.get("enabled_only") or "all").strip().lower()
    enabled_only: Optional[bool] = None
    if enabled_filter in {"true", "1", "yes", "enabled"}:
        enabled_only = True
        enabled_filter = "true"
    elif enabled_filter in {"false", "0", "no", "disabled"}:
        enabled_only = False
        enabled_filter = "false"
    else:
        enabled_filter = "all"
    limit = _query_int(request.args.get("limit"), default=50, min_value=1, max_value=500)
    items = ALPHONSE.list_abilities(enabled_only=enabled_only, limit=limit) or []
    return render_template(
        "abilities.html",
        abilities=items,
        selected_enabled_only=enabled_filter,
        selected_limit=limit,
        notice=(request.args.get("notice") or "").strip(),
        error=(request.args.get("error") or "").strip(),
        **page_context("Abilities"),
    )


@app.post("/abilities")
def abilities_create() -> Response:
    intent_name = (request.form.get("intent_name") or "").strip()
    if not intent_name:
        return redirect(url_for("abilities", notice="", error="intent_name is required"))

    kind = (request.form.get("kind") or "").strip()
    source = (request.form.get("source") or "").strip()
    enabled_raw = (request.form.get("enabled") or "true").strip().lower()
    enabled = enabled_raw in {"1", "true", "yes", "on"}

    tools_raw = request.form.get("tools_json") or "[]"
    tools = _parse_json_list(tools_raw)
    if tools is None:
        return redirect(url_for("abilities", notice="", error="tools_json must be a JSON array"))

    spec_raw = request.form.get("spec_json") or "{}"
    spec = _parse_json_dict(spec_raw)
    if spec is None:
        return redirect(url_for("abilities", notice="", error="spec_json must be a JSON object"))
    spec_intent = spec.get("intent_name")
    if spec_intent is None:
        spec["intent_name"] = intent_name
    elif str(spec_intent) != intent_name:
        return redirect(url_for("abilities", notice="", error="spec.intent_name must match intent_name"))

    payload: Dict[str, object] = {
        "intent_name": intent_name,
        "enabled": enabled,
        "tools": tools,
        "spec": spec,
    }
    if kind:
        payload["kind"] = kind
    if source:
        payload["source"] = source

    result = ALPHONSE.create_ability(payload)
    if not result.get("ok"):
        return redirect(url_for("abilities", notice="", error=f"Failed to create ability {intent_name}"))
    return redirect(url_for("abilities", notice=f"Created ability {intent_name}", error=""))


@app.post("/abilities/<path:intent_name>/update")
def abilities_update(intent_name: str) -> Response:
    updates: Dict[str, object] = {}
    kind = (request.form.get("kind") or "").strip()
    source = (request.form.get("source") or "").strip()
    enabled_choice = (request.form.get("enabled_choice") or "unchanged").strip().lower()
    tools_raw = (request.form.get("tools_json") or "").strip()
    spec_raw = (request.form.get("spec_json") or "").strip()

    if kind:
        updates["kind"] = kind
    if source:
        updates["source"] = source
    if enabled_choice in {"true", "false"}:
        updates["enabled"] = enabled_choice == "true"
    if tools_raw:
        tools = _parse_json_list(tools_raw)
        if tools is None:
            return redirect(url_for("abilities", notice="", error=f"Invalid tools_json for {intent_name}"))
        updates["tools"] = tools
    if spec_raw:
        spec = _parse_json_dict(spec_raw)
        if spec is None:
            return redirect(url_for("abilities", notice="", error=f"Invalid spec_json for {intent_name}"))
        spec_intent = spec.get("intent_name")
        if spec_intent is not None and str(spec_intent) != intent_name:
            return redirect(
                url_for(
                    "abilities",
                    notice="",
                    error=f"spec.intent_name mismatch for {intent_name}",
                )
            )
        updates["spec"] = spec

    if not updates:
        return redirect(url_for("abilities", notice="", error=f"No updates provided for {intent_name}"))

    result = ALPHONSE.update_ability(intent_name, updates)
    if not result.get("ok"):
        return redirect(url_for("abilities", notice="", error=f"Failed to update {intent_name}"))
    return redirect(url_for("abilities", notice=f"Updated ability {intent_name}", error=""))


@app.post("/abilities/<path:intent_name>/delete")
def abilities_delete(intent_name: str) -> Response:
    result = ALPHONSE.delete_ability(intent_name)
    if not result.get("ok"):
        return redirect(url_for("abilities", notice="", error=f"Ability {intent_name} not found"))
    return redirect(url_for("abilities", notice=f"Deleted ability {intent_name}", error=""))


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

    entries = _append_chat_turn(content, correlation_id)

    worker = threading.Thread(
        target=_resolve_async_assistant_reply,
        args=(content, correlation_id),
        daemon=True,
    )
    worker.start()

    response = Response(render_template("partials/chat_timeline.html", entries=entries))
    response.headers["X-UI-Event-Type"] = UI_EVENT_TYPES["command_received"]
    return with_contract_headers(response, correlation_id)


@app.post("/chat/voice")
def chat_voice() -> Response:
    correlation_id = ensure_correlation_id(request.form.get("correlation_id"))
    provider = (request.form.get("provider") or "").strip() or "webui"
    channel = (request.form.get("channel") or "").strip() or "webui"
    upload = request.files.get("audio")
    if upload is None:
        response = jsonify({"ok": False, "error": "missing_audio", "correlation_id": correlation_id})
        response.status_code = 400
        response.headers["X-UI-Event-Type"] = UI_EVENT_TYPES["command_failed"]
        return with_contract_headers(response, correlation_id, ok=False)

    blob = upload.read()
    if not blob:
        response = jsonify({"ok": False, "error": "empty_audio", "correlation_id": correlation_id})
        response.status_code = 400
        response.headers["X-UI-Event-Type"] = UI_EVENT_TYPES["command_failed"]
        return with_contract_headers(response, correlation_id, ok=False)

    uploaded = ALPHONSE.upload_asset(
        content=blob,
        filename=upload.filename or "voice.webm",
        mime_type=upload.mimetype or "application/octet-stream",
        correlation_id=correlation_id,
        provider=provider,
        channel=channel,
        kind="audio",
    )
    if not uploaded.get("ok"):
        response = jsonify({"ok": False, "error": "asset_upload_failed", "correlation_id": correlation_id})
        response.status_code = 502
        response.headers["X-UI-Event-Type"] = UI_EVENT_TYPES["command_failed"]
        return with_contract_headers(response, correlation_id, ok=False)

    asset_id_raw = uploaded.get("asset_id")
    if not isinstance(asset_id_raw, str) or asset_id_raw == "":
        response = jsonify({"ok": False, "error": "asset_id_missing", "correlation_id": correlation_id})
        response.status_code = 502
        response.headers["X-UI-Event-Type"] = UI_EVENT_TYPES["command_failed"]
        return with_contract_headers(response, correlation_id, ok=False)
    asset_id = asset_id_raw

    app.logger.info(
        "voice.asset_uploaded correlation_id=%s provider=%s channel=%s asset_id=%s bytes=%s",
        correlation_id,
        provider,
        channel,
        asset_id,
        len(blob),
    )

    audio_mode = _parse_audio_mode(request.form.get("audio_mode"))
    content = f"[voice] asset={asset_id}"
    _append_chat_turn(content, correlation_id)

    worker = threading.Thread(
        target=_resolve_async_asset_assistant_reply,
        kwargs={
            "correlation_id": correlation_id,
            "asset_id": asset_id,
            "audio_mode": audio_mode,
            "provider": provider,
            "channel": channel,
        },
        daemon=True,
    )
    worker.start()

    response = jsonify(
        {
            "ok": True,
            "status": "accepted",
            "correlation_id": correlation_id,
            "message_id": correlation_id,
            "asset_id": asset_id,
            "provider": provider,
            "channel": channel,
            "audio_mode": audio_mode,
        }
    )
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
