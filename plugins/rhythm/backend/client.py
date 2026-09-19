"""Narrow, fail-closed HTTP client for the approved Rhythm API origin."""

from __future__ import annotations

import json
import hashlib
import socket
import ssl
import time
import zlib
from datetime import date
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import parse_qsl, urljoin, urlparse

APPROVED_ORIGIN = "https://api.vcrcapps.com"
DESKTOP_LOGIN_CAPABILITY_ENDPOINT = f"{APPROVED_ORIGIN}/auth/google/desktop-login-capability"
DESKTOP_EXCHANGE_ENDPOINT = f"{APPROVED_ORIGIN}/auth/google/desktop-login-exchange"
ALLOWED_OPERATIONS = {
    ("GET", "/auth/me"),
    ("GET", "/workspaces/me"),
    ("GET", "/dashboard/summary"),
    ("GET", "/tasks"),
    ("GET", "/planner/weeks"),
    ("GET", "/recurring-rules"),
    ("GET", "/project-templates"),
    ("GET", "/project-instances"),
    ("GET", "/automations/catalog"),
    ("GET", "/automations/rules"),
    ("GET", "/automations/rules/{id}/preview"),
    ("GET", "/integrations/status"),
    ("GET", "/integrations/settings"),
    ("GET", "/integrations/sync"),
    ("GET", "/artifacts"),
    ("GET", "/message-threads"),
    ("GET", "/users"),
    ("GET", "/facilities"),
    ("GET", "/facilities/reservations"),
}
MAX_RESPONSE_BYTES = 32_768
# The hosted dashboard includes several full task arrays before we project it
# to small cards. Bound that one pinned response independently of the other
# API reads; the public plugin route still emits at most MAX_RESPONSE_BYTES.
MAX_DASHBOARD_RESPONSE_BYTES = 131_072
MAX_TASKS_RESPONSE_BYTES = 1_048_576  # At most 500 bounded task records before projection.
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

    limit = (MAX_DASHBOARD_RESPONSE_BYTES if method == "GET" and url == f"{APPROVED_ORIGIN}/dashboard/summary"
             else MAX_TASKS_RESPONSE_BYTES if method == "GET" and url == f"{APPROVED_ORIGIN}/tasks"
             else MAX_RESPONSE_BYTES)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            # HTTPX advertises Brotli when its optional decoder is installed,
            # while our bounded raw/decoded stream deliberately supports only
            # identity, gzip and deflate. Negotiate exactly those encodings.
            with client.stream(method, url, headers={**headers, "Accept-Encoding": "gzip, deflate"}, content=body) as response:
                content_length = response.headers.get("content-length")
                if content_length is not None:
                    try:
                        if int(content_length) > limit:
                            raise RhythmProtocolError("response_too_large")
                    except ValueError as exc:
                        raise RhythmProtocolError("invalid_content_length") from exc

                encoding = response.headers.get("content-encoding", "identity").lower().strip()
                if encoding in ("", "identity"):
                    decoder = None
                elif encoding == "gzip":
                    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
                elif encoding == "deflate":
                    decoder = zlib.decompressobj()
                else:
                    raise RhythmProtocolError("unsupported_content_encoding")

                content = bytearray()
                raw_bytes = 0
                for raw_chunk in response.iter_raw():
                    raw_bytes += len(raw_chunk)
                    if raw_bytes > limit:
                        raise RhythmProtocolError("response_too_large")
                    decoded_chunk = (
                        raw_chunk
                        if decoder is None
                        else decoder.decompress(
                            raw_chunk, limit - len(content) + 1
                        )
                    )
                    content.extend(decoded_chunk)
                    if len(content) > limit:
                        raise RhythmProtocolError("response_too_large")
                if decoder is not None:
                    content.extend(decoder.flush(limit - len(content) + 1))
                    if len(content) > limit:
                        raise RhythmProtocolError("response_too_large")
                payload = json.loads(bytes(content).decode("utf-8")) if content else {}
                return response.status_code, dict(response.headers), payload
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
    except ValueError as exc:
        raise RhythmProtocolError("invalid_json") from exc


def _remote_error(status: int) -> RhythmRemoteError:
    kinds = {401: "unauthorized", 403: "forbidden", 404: "not_found", 409: "conflict", 429: "rate_limited"}
    return RhythmRemoteError(kinds.get(status, "upstream_unavailable" if status >= 500 else "upstream_error"), status)


@dataclass
class RhythmClient:
    token: str
    transport: Transport = _httpx_transport
    sleep: Callable[[float], None] = time.sleep

    def require_login_only_capability(self) -> None:
        """Refuse OAuth until the host guarantees exchange has no integration writes."""
        status, headers, payload = self.transport(
            "GET", DESKTOP_LOGIN_CAPABILITY_ENDPOINT,
            {"Accept": "application/json"}, None, REQUEST_TIMEOUT_SECONDS,
        )
        if 300 <= status < 400 or headers.get("location") or headers.get("Location"):
            raise RhythmProtocolError("redirect_rejected")
        if status != 200 or not isinstance(payload, dict) or payload.get("loginOnlyDesktopExchange") is not True:
            raise RhythmProtocolError("oauth_login_only_unavailable")

    def call(self, method: str, path: str, *, body: dict[str, Any] | None = None, idempotency_key: str | None = None, m5: bool = False) -> dict[str, Any]:
        method = method.upper()
        is_task_detail = method == "GET" and path.startswith("/tasks/") and _safe_task_id(path.removeprefix("/tasks/"))
        is_m5_read = method == "GET" and (
            (path.startswith("/planner/weeks/") and _safe_date(path.removeprefix("/planner/weeks/")))
            or (path.startswith("/recurring-rules/") and _safe_task_id(path.removeprefix("/recurring-rules/")))
            or _m5_project_read_path(path)
            or _m6_read_path(path)
        )
        is_m7_read = method == "GET" and (
            (path.startswith("/automations/rules/") and path.endswith("/preview") and _safe_task_id(path.removeprefix("/automations/rules/").removesuffix("/preview")))
            or (path.startswith("/artifacts/") and path.endswith("/document") and _safe_task_id(path.removeprefix("/artifacts/").removesuffix("/document")))
        )
        is_m5_mutation = m5 and method in {"POST", "PATCH", "DELETE"} and (_m5_mutation_path(method, path) or _m6_mutation_path(method, path)) and (method == "DELETE" or body is not None)
        is_task_mutation = method == "PATCH" and path.startswith("/tasks/") and _safe_task_id(path.removeprefix("/tasks/")) and body is not None
        if (method, path) not in ALLOWED_OPERATIONS and not is_task_detail and not is_task_mutation and not is_m5_read and not is_m5_mutation and not is_m7_read:
            raise RhythmProtocolError("operation_not_allowed")
        if is_task_mutation and not is_m5_mutation and set(body) not in ({"status"}, {"scheduledDate"}):
            raise RhythmProtocolError("operation_not_allowed")
        if body and body.get("status") != "done" and "status" in body:
            raise RhythmProtocolError("operation_not_allowed")
        if body and "scheduledDate" in body:
            if not isinstance(body["scheduledDate"], str):
                raise RhythmProtocolError("operation_not_allowed")
            try:
                if date.fromisoformat(body["scheduledDate"]).isoformat() != body["scheduledDate"]:
                    raise ValueError
            except ValueError as exc:
                raise RhythmProtocolError("operation_not_allowed") from exc
        parsed = urlparse(path)
        if parsed.scheme or parsed.netloc or not path.startswith("/"):
            raise RhythmProtocolError("origin_not_allowed")
        url = urljoin(APPROVED_ORIGIN, path)
        attempts = 2 if method == "GET" else 1
        encoded = json.dumps(body, separators=(",", ":")).encode() if body is not None else None
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        if encoded is not None:
            headers["Content-Type"] = "application/json"
        # An intent key is semantic, not a property of a request body.  In
        # particular, an approved DELETE must retain the caller's key without
        # inventing an uncontracted JSON body.
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        elif encoded is not None:
            headers["Idempotency-Key"] = hashlib.sha256(f"{method}:{path}:{encoded.decode()}".encode()).hexdigest()
        for attempt in range(attempts):
            try:
                status, response_headers, payload = self.transport(method, url, headers, encoded, REQUEST_TIMEOUT_SECONDS)
            except RhythmRemoteError:
                if attempt + 1 < attempts:
                    self.sleep(0.1)
                    continue
                raise
            location = response_headers.get("location") or response_headers.get("Location")
            if 300 <= status < 400 or location:
                raise RhythmProtocolError("redirect_rejected")
            if status >= 500 and attempt + 1 < attempts:
                self.sleep(0.1)
                continue
            if status != 200:
                raise _remote_error(status)
            if method == "GET" and path == "/tasks" and isinstance(payload, list):
                if len(payload) > 500 or not all(isinstance(row, dict) for row in payload):
                    raise RhythmProtocolError("schema_drift")
                payload = {"tasks": payload}
            if not isinstance(payload, dict):
                raise RhythmProtocolError("schema_drift")
            response_limit = (MAX_DASHBOARD_RESPONSE_BYTES if method == "GET" and path == "/dashboard/summary"
                              else MAX_TASKS_RESPONSE_BYTES if method == "GET" and path == "/tasks"
                              else MAX_RESPONSE_BYTES)
            if len(json.dumps(payload, separators=(",", ":")).encode()) > response_limit:
                raise RhythmProtocolError("response_too_large")
            return payload
        raise RhythmRemoteError("upstream_unavailable")

    def mutate_task(self, task_id: str, operation: str, scheduled_date: str | None = None, *, idempotency_key: str | None = None) -> dict[str, Any]:
        """Perform one semantic PATCH and succeed only after canonical GET reconciliation."""
        if operation == "complete":
            body = {"status": "done"}
        elif operation == "reschedule" and scheduled_date is not None:
            body = {"scheduledDate": scheduled_date}
        else:
            raise RhythmProtocolError("operation_not_allowed")
        # The caller supplies an identity-bound intent key.  Keep the fallback
        # deterministic for direct callers, but never derive it from credentials.
        key = idempotency_key or hashlib.sha256(f"rhythm-m4b:{task_id}:{operation}:{scheduled_date or ''}".encode()).hexdigest()
        uncertain: RhythmRemoteError | None = None
        try:
            self.call("PATCH", f"/tasks/{task_id}", body=body, idempotency_key=key)
        except RhythmRemoteError as exc:
            # A 409 is an authoritative rejection, not an ambiguous mutation.  Never
            # turn it into success merely because the desired state already existed.
            if exc.kind == "conflict":
                raise
            if exc.kind not in {"timeout", "network", "dns", "upstream_unavailable"}:
                raise
            uncertain = exc
        canonical = self.call("GET", f"/tasks/{task_id}")
        matched = canonical.get("id") == task_id and (canonical.get("status") == "done" if operation == "complete" else canonical.get("scheduledDate") == scheduled_date)
        # A transport ambiguity is never upgraded to success from readback: the
        # upstream might have applied a concurrent actor's identical state.
        if matched and uncertain is None:
            return canonical
        raise RhythmRemoteError("uncertain", uncertain.status_code) if uncertain is not None else RhythmRemoteError("conflict", 409)

    def exchange_code(self, code: str, verifier: str, redirect_uri: str) -> str:
        """Exchange a desktop PKCE code for a Rhythm session, never a Google token."""
        if not code or not verifier or not redirect_uri:
            raise RhythmProtocolError("invalid_oauth_callback")
        body = json.dumps(
            {
                "code": code,
                "codeVerifier": verifier,
                "redirectUri": redirect_uri,
            }
        ).encode()
        status, headers, payload = self.transport(
            "POST",
            DESKTOP_EXCHANGE_ENDPOINT,
            {"Accept": "application/json", "Content-Type": "application/json"},
            body,
            REQUEST_TIMEOUT_SECONDS,
        )
        if 300 <= status < 400 or headers.get("location") or headers.get("Location"):
            raise RhythmProtocolError("redirect_rejected")
        if status != 200:
            raise _remote_error(status)
        if not isinstance(payload, dict) or not isinstance(payload.get("sessionToken"), str) or not payload["sessionToken"]:
            raise RhythmProtocolError("schema_drift")
        return payload["sessionToken"]


def _safe_task_id(value: str) -> bool:
    return bool(value) and len(value) <= 128 and all(char.isalnum() or char in "_-" for char in value)


def _safe_date(value: str) -> bool:
    try:
        return date.fromisoformat(value).isoformat() == value
    except (TypeError, ValueError):
        return False


def _m5_project_read_path(path: str) -> bool:
    """Exact M5 project entity reads; collection envelopes are never entities."""
    parts = path.split("/")[1:]
    if len(parts) == 2 and parts[0] in {"project-templates", "project-instances"}:
        return _safe_task_id(parts[1])
    if len(parts) == 3 and parts[0] == "project-instances" and parts[1] == "steps":
        return _safe_task_id(parts[2])
    if len(parts) == 4 and parts[0] == "project-templates" and parts[2] == "steps":
        return _safe_task_id(parts[1]) and _safe_task_id(parts[3])
    if len(parts) == 4 and parts[0] == "project-instances" and parts[2] == "milestones":
        return _safe_task_id(parts[1]) and _safe_task_id(parts[3])
    return False


def _m5_mutation_path(method: str, path: str) -> bool:
    """The M5 upstream allowlist.  This intentionally excludes all member and
    collaborator routes and every arbitrary URL/body proxy."""
    parts = path.split("/")[1:]
    if not parts or any(not part or not _safe_task_id(part) for part in parts if part not in {"project-templates", "project-instances", "recurring-rules", "steps", "milestones", "generate"}):
        return False
    if parts[0] == "recurring-rules":
        return (method == "POST" and len(parts) in {1, 3} and (len(parts) == 1 or parts[2] == "steps")) or (method in {"PATCH", "DELETE"} and len(parts) == 2)
    if parts[0] == "project-templates":
        return (method == "POST" and (len(parts) == 1 or (len(parts) == 3 and parts[2] in {"steps", "generate"}))) or (method in {"PATCH", "DELETE"} and len(parts) in {2, 4} and (len(parts) == 2 or parts[2] == "steps"))
    if parts[0] == "project-instances":
        return (method == "PATCH" and len(parts) == 3 and parts[1] == "steps") or (method == "POST" and len(parts) == 3 and parts[2] == "milestones")
    if parts[0] == "tasks":
        return method == "PATCH" and len(parts) == 2
    return False


def _m6_read_path(path: str) -> bool:
    """Exact M6 reads. Query strings are limited to the two bounded ranges."""
    parsed = urlparse(path)
    parts = parsed.path.split("/")[1:]
    if parsed.path in {"/message-threads", "/users", "/facilities"}:
        return not parsed.query
    if len(parts) == 3 and parts[0] == "message-threads" and parts[2] == "messages":
        return _safe_task_id(parts[1]) and not parsed.query
    if parsed.path == "/facilities/reservations":
        pairs = parse_qsl(parsed.query, keep_blank_values=True)
        if not pairs:
            return True
        if pairs == [("grouped", "true")]:
            return True
        return {key for key, _ in pairs} == {"start", "end"}
    if len(parts) == 2 and parts[0] == "facilities":
        return _safe_task_id(parts[1]) and not parsed.query
    if len(parts) == 4 and parts[0] == "facilities" and parts[2] == "reservations":
        return _safe_task_id(parts[1]) and _safe_task_id(parts[3]) and not parsed.query
    if len(parts) == 3 and parts[0] == "facilities" and parts[2] == "reservation-series":
        return _safe_task_id(parts[1]) and not parsed.query
    return False


def _m6_mutation_path(method: str, path: str) -> bool:
    """M6's semantic set deliberately excludes every message create/send route."""
    parts = path.split("/")[1:]
    if len(parts) == 2 and parts[0] == "message-threads":
        return method == "PATCH" and _safe_task_id(parts[1])
    if parts == ["facilities"]:
        return method == "POST"
    if len(parts) == 2 and parts[0] == "facilities":
        return method in {"PATCH", "DELETE"} and _safe_task_id(parts[1])
    if len(parts) == 3 and parts[0] == "facilities" and parts[2] in {"reservations", "reservation-series"}:
        return method == "POST" and _safe_task_id(parts[1])
    if len(parts) == 4 and parts[0] == "facilities" and parts[2] in {"reservations", "reservation-series"}:
        return method in {"PATCH", "DELETE"} and _safe_task_id(parts[1]) and _safe_task_id(parts[3])
    if parts == ["facilities", "automation-reservations"]:
        return method == "DELETE"
    return False
