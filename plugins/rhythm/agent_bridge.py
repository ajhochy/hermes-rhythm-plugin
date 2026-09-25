"""Bounded client for the local Rhythm agent bridge."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import quote, urlencode

from agent import host_capabilities


_OPERATIONS = {
    "catalog.list": ("GET", "/catalog", ()),
    "catalog.get": ("GET", "/catalog/{agentId}", ("agentId",)),
    "runtime.report": ("POST", "/runtime/report", ()),
    "agent.patch": ("POST", "/agents/{agentId}/patch", ("agentId",)),
    "agent.patch-status": ("POST", "/agents/{agentId}/patch-status", ("agentId",)),
    "projection.issue": ("POST", "/projections", ()),
    "projection.check": ("POST", "/projections/{projectionId}/check", ("projectionId",)),
    "delegation.dispatch": ("POST", "/delegations", ()),
    "delegation.status": ("POST", "/delegations/query", ()),
    "delegation.result": ("POST", "/delegations/{jobId}/result", ("jobId",)),
    "delegation.cancel": ("POST", "/delegations/{jobId}/cancel", ("jobId",)),
    "delegation.claim": ("POST", "/delegations/claim", ()),
    "delegation.report": ("POST", "/delegations/{jobId}/report", ("jobId",)),
    "memory.search": ("POST", "/memory/search", ()),
}
_CATALOG_RESPONSE_BYTES = 1024 * 1024
_DEFAULT_RESPONSE_BYTES = 256 * 1024
_HEADER = "X-Rhythm-Bridge-Capability"
_ERROR_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class BridgeError(Exception):
    """A sanitized bridge failure; messages never include bridge authority."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _httpx_transport(
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes | None,
    timeout: float,
    max_bytes: int,
) -> tuple[int, dict[str, str], dict[str, Any]]:
    import httpx

    try:
        with httpx.Client(
            follow_redirects=False,
            timeout=timeout,
            trust_env=False,
        ) as client:
            with client.stream(method, url, headers=headers, content=body) as response:
                length = response.headers.get("content-length")
                if length is not None and int(length) > max_bytes:
                    raise BridgeError("response_too_large")
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > max_bytes:
                        raise BridgeError("response_too_large")
                if not raw:
                    payload: dict[str, Any] = {}
                else:
                    parsed = json.loads(bytes(raw).decode("utf-8"))
                    if not isinstance(parsed, dict):
                        raise BridgeError("invalid_response")
                    payload = parsed
                return response.status_code, dict(response.headers), payload
    except BridgeError:
        raise
    except (httpx.HTTPError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise BridgeError("bridge_unavailable") from None


def _path_value(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise BridgeError("invalid_path_parameter")
    if any(ord(char) < 32 for char in value) or "/" in value or "\\" in value or value in {".", ".."}:
        raise BridgeError("invalid_path_parameter")
    return quote(value, safe="")


def _response_size(payload: Mapping[str, Any]) -> int:
    try:
        return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    except (TypeError, ValueError):
        raise BridgeError("invalid_response") from None


class BridgeClient:
    def __init__(self, transport: Callable[..., tuple[int, dict[str, str], dict[str, Any]]] = _httpx_transport):
        self._transport = transport

    def call(
        self,
        op: str,
        *,
        path_params: dict | None = None,
        body: dict | None = None,
        query: dict | None = None,
        timeout: float = 10.0,
    ) -> dict:
        operation = _OPERATIONS.get(op)
        if operation is None:
            raise BridgeError("operation_not_allowed")
        capability = host_capabilities.get("rhythm_bridge")
        if capability is None:
            raise BridgeError("bridge_unavailable")

        method, path_template, names = operation
        supplied = path_params or {}
        if set(supplied) != set(names):
            raise BridgeError("invalid_path_parameter")
        path = path_template
        for name in names:
            path = path.replace("{" + name + "}", _path_value(supplied[name]))

        if query:
            if op != "catalog.get" or set(query) != {"sessionRevision"}:
                raise BridgeError("invalid_query")
            revision = query["sessionRevision"]
            if type(revision) is not int or revision < 0:
                raise BridgeError("invalid_query")
            path += "?" + urlencode({"sessionRevision": revision})

        encoded = None
        if body is not None:
            if not isinstance(body, dict):
                raise BridgeError("invalid_request")
            encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {
            _HEADER: capability.token,
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "Content-Type": "application/json",
        }
        max_bytes = _CATALOG_RESPONSE_BYTES if op.startswith("catalog.") else _DEFAULT_RESPONSE_BYTES
        for attempt in range(2):
            try:
                status, _response_headers, payload = self._transport(
                    method,
                    capability.origin + "/agent-bridge/v1" + path,
                    headers,
                    encoded,
                    timeout,
                    max_bytes,
                )
                break
            except BridgeError as exc:
                if attempt or exc.code != "bridge_unavailable":
                    raise
            except Exception:
                if attempt:
                    raise BridgeError("bridge_unavailable") from None

        if 300 <= status < 400:
            raise BridgeError("redirect_rejected")
        if not isinstance(payload, Mapping):
            raise BridgeError("invalid_response")
        if _response_size(payload) > max_bytes:
            raise BridgeError("response_too_large")
        if not 200 <= status < 300:
            error = payload.get("error")
            code = error.get("code") if isinstance(error, Mapping) else None
            safe_code = code if isinstance(code, str) and _ERROR_CODE_RE.fullmatch(code) else "bridge_unavailable"
            raise BridgeError(safe_code)
        return dict(payload)
