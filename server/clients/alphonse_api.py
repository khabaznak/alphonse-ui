from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional
from urllib import error, request as urlrequest


class AlphonseClient:
    """HTTP adapter for Alphonse agent API with shape validation."""

    def __init__(self) -> None:
        self.base_url = os.getenv("ALPHONSE_API_BASE_URL", "http://localhost:8001").rstrip("/")
        token = os.getenv("ALPHONSE_API_TOKEN", "").strip()
        self.api_token = token or None

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
            timeout=5.0,
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

    def _request_json(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, object]],
        timeout: float,
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
