"""Narrow, fail-closed HTTP client for the approved Rhythm API origin."""

from __future__ import annotations

import json
import socket
import ssl
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

APPROVED_ORIGIN = "https://api.rhythm.app"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
ALLOWED_OPERATIONS = {("GET", "/auth/me"), ("GET", "/workspaces/me")}
MAX_RESPONSE_BYTES = 32_768
REQUEST_TIMEOUT_SECONDS = 10.0
Transport = Callable[[str, str, dict[str, str], bytes | None, float], tuple[int, dict[str, str], Any]]


class RhythmProtocolError(RuntimeError):
    """The request or response violates the fixed Rhythm protocol."""


class RhythmRemoteError(RuntimeError):
    def __init__(self, kind: str, status_code: int | None = None):
        self.kind = kind
        self.status_code = status_code
        super().__init__(kind)


def _httpx_transport(method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float):
    import httpx

    try:
        response = httpx.request(method, url, headers=headers, content=body, timeout=timeout, follow_redirects=False)
    except httpx.TimeoutException as exc:
        raise RhythmRemoteError("timeout") from exc
    except httpx.ConnectError as exc:
        cause = exc.__cause__
        if isinstance(cause, ssl.SSLError):
            raise RhythmRemoteError("tls") from exc
        if isinstance(cause, socket.gaierror):
            raise RhythmRemoteError("dns") from exc
        raise RhythmRemoteError("network") from exc
    except ssl.SSLError as exc:
        raise RhythmRemoteError("tls") from exc
    content = response.content
    if len(content) > MAX_RESPONSE_BYTES:
        raise RhythmProtocolError("response_too_large")
    try:
        payload = response.json() if content else {}
    except ValueError as exc:
        raise RhythmProtocolError("invalid_json") from exc
    return response.status_code, dict(response.headers), payload


def _remote_error(status: int) -> RhythmRemoteError:
    kinds = {401: "unauthorized", 403: "forbidden", 404: "not_found", 409: "conflict", 429: "rate_limited"}
    return RhythmRemoteError(kinds.get(status, "upstream_unavailable" if status >= 500 else "upstream_error"), status)


@dataclass
class RhythmClient:
    token: str
    transport: Transport = _httpx_transport
    sleep: Callable[[float], None] = time.sleep

    def call(self, method: str, path: str) -> dict[str, Any]:
        method = method.upper()
        if (method, path) not in ALLOWED_OPERATIONS:
            raise RhythmProtocolError("operation_not_allowed")
        parsed = urlparse(path)
        if parsed.scheme or parsed.netloc or not path.startswith("/"):
            raise RhythmProtocolError("origin_not_allowed")
        url = urljoin(APPROVED_ORIGIN, path)
        attempts = 2 if method == "GET" else 1
        for attempt in range(attempts):
            try:
                status, headers, payload = self.transport(method, url, {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}, None, REQUEST_TIMEOUT_SECONDS)
            except RhythmRemoteError:
                if attempt + 1 < attempts:
                    self.sleep(0.1)
                    continue
                raise
            location = headers.get("location") or headers.get("Location")
            if 300 <= status < 400 or location:
                raise RhythmProtocolError("redirect_rejected")
            if status >= 500 and attempt + 1 < attempts:
                self.sleep(0.1)
                continue
            if status != 200:
                raise _remote_error(status)
            if not isinstance(payload, dict):
                raise RhythmProtocolError("schema_drift")
            if len(json.dumps(payload, separators=(",", ":"))) > MAX_RESPONSE_BYTES:
                raise RhythmProtocolError("response_too_large")
            return payload
        raise RhythmRemoteError("upstream_unavailable")

    def exchange_code(self, code: str, verifier: str) -> str:
        """Perform the one explicitly-defined OAuth exchange; never redirect."""
        if not code or not verifier:
            raise RhythmProtocolError("invalid_oauth_callback")
        body = json.dumps({"grant_type": "authorization_code", "code": code, "code_verifier": verifier}).encode()
        status, headers, payload = self.transport("POST", GOOGLE_TOKEN_ENDPOINT, {"Accept": "application/json", "Content-Type": "application/json"}, body, REQUEST_TIMEOUT_SECONDS)
        if 300 <= status < 400 or headers.get("location") or headers.get("Location"):
            raise RhythmProtocolError("redirect_rejected")
        if status != 200:
            raise _remote_error(status)
        if not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str) or not payload["access_token"]:
            raise RhythmProtocolError("schema_drift")
        return payload["access_token"]
