from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional
from urllib import error, request as urlrequest
from urllib.parse import quote


class AlphonseClient:
    """HTTP adapter for Alphonse agent API with shape validation."""

    def __init__(self) -> None:
        self.base_url = os.getenv("ALPHONSE_API_BASE_URL", "http://localhost:8001").rstrip("/")
        token = os.getenv("ALPHONSE_API_TOKEN", "").strip()
        self.api_token = token or None
        self.message_timeout = _read_timeout_seconds("ALPHONSE_API_MESSAGE_TIMEOUT_SECONDS")

    def send_message(
        self,
        content: str,
        correlation_id: str,
        args: Optional[Dict[str, object]] = None,
    ) -> Dict[str, object]:
        payload = {
            "text": content,
            "args": args or {},
            "channel": "webui",
            "timestamp": int(time.time()),
            "correlation_id": correlation_id,
            "metadata": {"user_name": self._default_user_name()},
        }
        data = self._request_json(
            "POST",
            "/agent/message",
            payload=payload,
            timeout=self.message_timeout,
            unwrap_data=False,
        )
        if not self._valid_message_response(data):
            return {"ok": False, "status": "unavailable", "correlation_id": correlation_id}
        return {"ok": True, "status": "accepted", "correlation_id": correlation_id, "data": data}

    def presence_snapshot(self) -> Dict[str, str]:
        data = self._request_json("GET", "/agent/status", payload=None, timeout=3.0)
        if not self._valid_status_response(data):
            return {
                "status": "disconnected",
                "note": "Alphonse API unavailable",
            }
        assert isinstance(data, dict)
        runtime = data.get("runtime")
        state = "connected"
        if isinstance(runtime, dict):
            state = str(runtime.get("state") or runtime.get("status") or "connected")
        return {
            "status": state,
            "note": "Alphonse API connected",
        }

    def list_delegates(self) -> Optional[List[Dict[str, object]]]:
        payload = self._request_json("GET", "/api/v1/delegates", payload=None, timeout=3.0)
        delegates = self._extract_delegate_list(payload)
        if delegates is not None:
            return delegates
        payload = self._request_json("GET", "/delegates", payload=None, timeout=3.0)
        return self._extract_delegate_list(payload)

    def get_delegate(self, delegate_id: str) -> Optional[Dict[str, object]]:
        payload = self._request_json("GET", f"/api/v1/delegates/{delegate_id}", payload=None, timeout=3.0)
        delegate = self._extract_delegate(payload)
        if delegate is not None:
            return delegate
        payload = self._request_json("GET", f"/delegates/{delegate_id}", payload=None, timeout=3.0)
        return self._extract_delegate(payload)

    def assign_delegate(
        self,
        delegate_id: str,
        capability: str,
        command: str,
        correlation_id: str,
    ) -> Dict[str, object]:
        payload = {
            "capability": capability,
            "command": command,
            "correlation_id": correlation_id,
            "timestamp": time.time(),
        }
        response = self._request_json(
            "POST",
            f"/api/v1/delegates/{delegate_id}/assign",
            payload=payload,
            timeout=5.0,
        )
        if self._valid_delegate_assign_response(response):
            return {"ok": True, "status": "assigned", "data": response}
        response = self._request_json(
            "POST",
            f"/delegates/{delegate_id}/assign",
            payload=payload,
            timeout=5.0,
        )
        if self._valid_delegate_assign_response(response):
            return {"ok": True, "status": "assigned", "data": response}
        return {"ok": False, "status": "unavailable"}

    def coalesce_gap_proposals(self, limit: int = 300, min_cluster_size: int = 2) -> Dict[str, object]:
        payload = {"limit": limit, "min_cluster_size": min_cluster_size}
        response = self._request_json(
            "POST",
            "/agent/gap-proposals/coalesce",
            payload=payload,
            timeout=10.0,
            unwrap_data=False,
        )
        if not isinstance(response, dict):
            return {"ok": False, "status": "unavailable"}
        return {
            "ok": True,
            "status": "accepted",
            "created_count": int(response.get("created_count") or 0),
            "proposal_ids": response.get("proposal_ids") if isinstance(response.get("proposal_ids"), list) else [],
            "data": response,
        }

    def list_gap_proposals(self, status: Optional[str], limit: int = 50) -> Optional[List[Dict[str, object]]]:
        query_status = status.strip() if isinstance(status, str) and status.strip() else None
        path = f"/agent/gap-proposals?limit={limit}"
        if query_status:
            path = f"{path}&status={query_status}"
        response = self._request_json("GET", path, payload=None, timeout=5.0, unwrap_data=False)
        if isinstance(response, dict):
            items = response.get("items")
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
        return None

    def update_gap_proposal(
        self,
        proposal_id: str,
        status: str,
        reviewer: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, object]:
        payload: Dict[str, object] = {"status": status}
        if reviewer and reviewer.strip():
            payload["reviewer"] = reviewer.strip()
        if notes and notes.strip():
            payload["notes"] = notes.strip()
        response = self._request_json(
            "PATCH",
            f"/agent/gap-proposals/{proposal_id}",
            payload=payload,
            timeout=5.0,
            unwrap_data=False,
        )
        if not isinstance(response, dict):
            return {"ok": False, "status": "unavailable"}
        item = response.get("item")
        if not isinstance(item, dict):
            return {"ok": False, "status": "invalid"}
        return {"ok": True, "status": "updated", "item": item}

    def dispatch_gap_proposal(
        self,
        proposal_id: str,
        task_type: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> Dict[str, object]:
        payload: Dict[str, object] = {}
        if task_type and task_type.strip():
            payload["task_type"] = task_type.strip()
        if actor and actor.strip():
            payload["actor"] = actor.strip()
        response = self._request_json(
            "POST",
            f"/agent/gap-proposals/{proposal_id}/dispatch",
            payload=payload,
            timeout=8.0,
            unwrap_data=False,
        )
        if not isinstance(response, dict):
            return {"ok": False, "status": "unavailable"}
        task_id = response.get("task_id")
        task = response.get("task")
        if not isinstance(task_id, str):
            return {"ok": False, "status": "invalid"}
        return {"ok": True, "status": "dispatched", "task_id": task_id, "task": task, "data": response}

    def list_gap_tasks(self, status: Optional[str], limit: int = 50) -> Optional[List[Dict[str, object]]]:
        query_status = status.strip() if isinstance(status, str) and status.strip() else None
        path = f"/agent/gap-tasks?limit={limit}"
        if query_status:
            path = f"{path}&status={query_status}"
        response = self._request_json("GET", path, payload=None, timeout=5.0, unwrap_data=False)
        if isinstance(response, dict):
            items = response.get("items")
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
        return None

    def update_gap_task(self, task_id: str, status: str) -> Dict[str, object]:
        response = self._request_json(
            "PATCH",
            f"/agent/gap-tasks/{task_id}",
            payload={"status": status},
            timeout=5.0,
            unwrap_data=False,
        )
        if not isinstance(response, dict):
            return {"ok": False, "status": "unavailable"}
        item = response.get("item")
        if not isinstance(item, dict):
            return {"ok": False, "status": "invalid"}
        return {"ok": True, "status": "updated", "item": item}

    def list_abilities(
        self,
        enabled_only: Optional[bool] = None,
        limit: int = 50,
    ) -> Optional[List[Dict[str, object]]]:
        params = [f"limit={limit}"]
        if enabled_only is not None:
            params.append(f"enabled_only={'true' if enabled_only else 'false'}")
        path = "/agent/abilities"
        if params:
            path = f"{path}?{'&'.join(params)}"
        response = self._request_json("GET", path, payload=None, timeout=5.0, unwrap_data=False)
        return self._extract_items_list(response)

    def get_ability(self, intent_name: str) -> Optional[Dict[str, object]]:
        encoded = quote(intent_name, safe="")
        response = self._request_json(
            "GET",
            f"/agent/abilities/{encoded}",
            payload=None,
            timeout=5.0,
            unwrap_data=False,
        )
        if isinstance(response, dict):
            item = response.get("item")
            if isinstance(item, dict):
                return item
            if "intent_name" in response and isinstance(response.get("intent_name"), str):
                return response
        return None

    def create_ability(self, payload: Dict[str, object]) -> Dict[str, object]:
        response = self._request_json(
            "POST",
            "/agent/abilities",
            payload=payload,
            timeout=8.0,
            unwrap_data=False,
        )
        if not isinstance(response, dict):
            return {"ok": False, "status": "unavailable"}
        item = response.get("item")
        if isinstance(item, dict):
            return {"ok": True, "status": "created", "item": item}
        if "intent_name" in response and isinstance(response.get("intent_name"), str):
            return {"ok": True, "status": "created", "item": response}
        return {"ok": False, "status": "invalid"}

    def update_ability(self, intent_name: str, updates: Dict[str, object]) -> Dict[str, object]:
        encoded = quote(intent_name, safe="")
        response = self._request_json(
            "PATCH",
            f"/agent/abilities/{encoded}",
            payload=updates,
            timeout=8.0,
            unwrap_data=False,
        )
        if not isinstance(response, dict):
            return {"ok": False, "status": "unavailable"}
        item = response.get("item")
        if isinstance(item, dict):
            return {"ok": True, "status": "updated", "item": item}
        if "intent_name" in response and isinstance(response.get("intent_name"), str):
            return {"ok": True, "status": "updated", "item": response}
        return {"ok": False, "status": "invalid"}

    def delete_ability(self, intent_name: str) -> Dict[str, object]:
        encoded = quote(intent_name, safe="")
        response = self._request_json(
            "DELETE",
            f"/agent/abilities/{encoded}",
            payload=None,
            timeout=5.0,
            unwrap_data=False,
        )
        if response is None:
            return {"ok": False, "status": "missing_or_unavailable"}
        if isinstance(response, dict):
            deleted = response.get("deleted")
            if isinstance(deleted, bool):
                return {"ok": deleted, "status": "deleted" if deleted else "not_deleted", "data": response}
            return {"ok": True, "status": "deleted", "data": response}
        return {"ok": True, "status": "deleted"}

    def _request_json(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, object]],
        timeout: Optional[float],
        unwrap_data: bool = True,
    ) -> Optional[Any]:
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
                    if unwrap_data:
                        data = parsed.get("data")
                        if data is not None:
                            return data
                    return parsed
                if isinstance(parsed, list):
                    return parsed
        except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError):
            return None
        return None

    def _default_user_name(self) -> str:
        return (
            os.getenv("ALPHONSE_UI_USER_NAME", "").strip()
            or os.getenv("USER", "").strip()
            or "Alphonse UI"
        )

    def _extract_delegate_list(self, payload: Optional[Any]) -> Optional[List[Dict[str, object]]]:
        if isinstance(payload, list):
            items = [item for item in payload if self._valid_delegate(item)]
            return items if items else None
        if isinstance(payload, dict):
            candidates = payload.get("delegates")
            if isinstance(candidates, list):
                items = [item for item in candidates if self._valid_delegate(item)]
                return items if items else None
        return None

    def _extract_items_list(self, payload: Optional[Any]) -> Optional[List[Dict[str, object]]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            items = payload.get("items")
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
            abilities = payload.get("abilities")
            if isinstance(abilities, list):
                return [item for item in abilities if isinstance(item, dict)]
        return None

    def _extract_delegate(self, payload: Optional[Any]) -> Optional[Dict[str, object]]:
        if self._valid_delegate(payload):
            assert isinstance(payload, dict)
            return payload
        if isinstance(payload, dict):
            candidate = payload.get("delegate")
            if self._valid_delegate(candidate):
                assert isinstance(candidate, dict)
                return candidate
        return None

    def _valid_message_response(self, payload: Optional[Any]) -> bool:
        if not isinstance(payload, dict):
            return False
        message = payload.get("message")
        return isinstance(message, str)

    def _valid_status_response(self, payload: Optional[Any]) -> bool:
        if not isinstance(payload, dict):
            return False
        runtime = payload.get("runtime")
        if runtime is None:
            return True
        return isinstance(runtime, dict)

    def _valid_delegate_assign_response(self, payload: Optional[Any]) -> bool:
        if payload is None:
            return False
        if isinstance(payload, dict):
            status = payload.get("status")
            if isinstance(status, str):
                return True
            if "delegate_id" in payload or "id" in payload:
                return True
            return len(payload) > 0
        return False

    def _valid_delegate(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        delegate_id = payload.get("id")
        name = payload.get("name")
        capabilities = payload.get("capabilities")
        contract_version = payload.get("contract_version")
        if not isinstance(delegate_id, str) or not delegate_id.strip():
            return False
        if not isinstance(name, str) or not name.strip():
            return False
        if not isinstance(capabilities, list):
            return False
        if not all(isinstance(item, str) for item in capabilities):
            return False
        if not isinstance(contract_version, str) or not contract_version.strip():
            return False
        return True


def _read_timeout_seconds(name: str) -> Optional[float]:
    value = os.getenv(name)
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized or normalized in {"none", "infinite", "inf", "0"}:
        return None
    try:
        seconds = float(normalized)
        if seconds <= 0:
            return None
        return seconds
    except ValueError:
        return None
