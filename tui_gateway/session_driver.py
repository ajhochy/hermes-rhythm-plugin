"""In-process JSON-RPC driver for headless Hermes worker sessions."""
from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from typing import Literal

from tui_gateway import server
from tui_gateway.transport import bind_transport, reset_transport


class DriverError(Exception):
    def __init__(self, message: str, *, code: str = "driver_error") -> None:
        super().__init__(message)
        self.code = code


class DriverTransport:
    def __init__(self, on_event: Callable[[dict], None]) -> None:
        self._on_event = on_event
        self._closed = False

    def write(self, obj: dict) -> bool:
        if self._closed:
            return False
        if not isinstance(obj, dict):
            return True
        if obj.get("method") == "event":
            params = obj.get("params")
            if not isinstance(params, dict):
                return True
            event = dict(params)
        elif isinstance(obj.get("type"), str):
            event = dict(obj)
        else:
            return True
        payload = event.pop("payload", None)
        if isinstance(payload, dict):
            event.update(payload)
        self._on_event(event)
        return True

    def close(self) -> None:
        self._closed = True


def is_driver_transport(transport) -> bool:
    return isinstance(transport, DriverTransport)


class DriverSession:
    def __init__(self, sid: str, session_key: str, transport: DriverTransport, timeout: float) -> None:
        self.sid = sid
        self.session_key = session_key
        self.transport = transport
        self._timeout = timeout
        self._closed = False
        self._lock = threading.Lock()

    def _request(self, method: str, params: dict) -> dict:
        request = {
            "jsonrpc": "2.0",
            "id": f"driver-{uuid.uuid4().hex}",
            "method": method,
            "params": params,
        }
        token = bind_transport(self.transport)
        try:
            response = server.handle_request(request)
        finally:
            reset_transport(token)
        if not isinstance(response, dict):
            raise DriverError("driver request returned no response")
        error = response.get("error")
        if isinstance(error, dict):
            data = error.get("data")
            code = data.get("code") if isinstance(data, dict) else error.get("code")
            raise DriverError(str(error.get("message") or "driver request failed"), code=str(code or "driver_error"))
        result = response.get("result")
        return result if isinstance(result, dict) else {}

    def submit(self, text: str) -> None:
        self._request(
            "prompt.submit",
            {"session_id": self.sid, "text": text, "request_id": uuid.uuid4().hex},
        )

    def interrupt(self) -> None:
        self._request("session.interrupt", {"session_id": self.sid})

    def respond_approval(self, request_id: str, choice: Literal["once", "deny"]) -> None:
        if choice not in ("once", "deny"):
            raise ValueError("unsupported approval choice")
        self._request(
            "approval.respond",
            {"session_id": self.sid, "request_id": request_id, "choice": choice},
        )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            try:
                self._request("session.close", {"session_id": self.sid})
            finally:
                self._closed = True
                self.transport.close()


def create_session(
    params: dict,
    *,
    on_event: Callable[[dict], None],
    timeout: float = 30.0,
) -> DriverSession:
    transport = DriverTransport(on_event)
    temporary = DriverSession("", "", transport, timeout)
    try:
        result = temporary._request("session.create", dict(params))
    except Exception:
        transport.close()
        raise
    sid = str(result.get("session_id") or "")
    session_key = str(result.get("stored_session_id") or result.get("session_key") or sid)
    if not sid:
        transport.close()
        raise DriverError("session.create returned no session_id", code="invalid_response")
    return DriverSession(sid, session_key, transport, timeout)
