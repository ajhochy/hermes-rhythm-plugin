"""Mounted Rhythm REST routes. Secrets remain server-side at all times."""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from plugins.rhythm.backend.client import RhythmClient, RhythmProtocolError, RhythmRemoteError, _httpx_transport
from plugins.rhythm.backend import store

router = APIRouter()
log = logging.getLogger(__name__)
request = _httpx_transport
_OAUTH_TTL_SECONDS = 300
_oauth_lock = threading.Lock()


@dataclass
class _OAuthState:
    verifier: str
    expires_at: float
    consumed: bool = False


_oauth_states: dict[str, _OAuthState] = {}


class ConnectionInput(BaseModel):
    access_token: str = Field(min_length=8, max_length=2048)


class OAuthCallback(BaseModel):
    state: str = Field(min_length=16, max_length=256)
    code: str = Field(min_length=1, max_length=2048)


def _safe_identity(payload: dict[str, Any]) -> dict[str, str]:
    ident = payload.get("id")
    email = payload.get("email")
    if not isinstance(ident, str) or not ident or len(ident) > 128:
        raise RhythmProtocolError("schema_drift")
    result = {"id": ident}
    if isinstance(email, str) and 3 <= len(email) <= 320 and "@" in email:
        result["email"] = email
    return result


def _safe_workspace(payload: dict[str, Any]) -> dict[str, str]:
    workspace_id = payload.get("id")
    name = payload.get("name")
    if not isinstance(workspace_id, str) or not workspace_id or len(workspace_id) > 128:
        raise RhythmProtocolError("schema_drift")
    result = {"id": workspace_id}
    if isinstance(name, str) and name:
        result["name"] = name[:256]
    return result


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(400, detail={"error": "invalid_profile", "recoverable": True})
    if isinstance(exc, RhythmRemoteError):
        status = {"unauthorized": 401, "forbidden": 403, "not_found": 404, "conflict": 409, "rate_limited": 429, "timeout": 504, "dns": 502, "tls": 502}.get(exc.kind, 502)
        return HTTPException(status, detail={"error": exc.kind, "recoverable": True})
    return HTTPException(502, detail={"error": "schema_drift" if isinstance(exc, RhythmProtocolError) else "connection_error", "recoverable": True})


def _validated_connection(token: str) -> tuple[dict[str, str], dict[str, str]]:
    client = RhythmClient(token, transport=request)
    identity = _safe_identity(client.call("GET", "/auth/me"))
    workspace = _safe_workspace(client.call("GET", "/workspaces/me"))
    return identity, workspace


def _public(connection: dict[str, Any] | None) -> dict[str, Any]:
    if connection is None:
        return {"connected": False}
    return {"connected": True, "identity": connection.get("identity", {}), "workspace": connection.get("workspace", {})}


@router.put("/connection")
def put_connection(payload: ConnectionInput):
    try:
        identity, workspace = _validated_connection(payload.access_token)
        store.save(payload.access_token, identity, workspace)
        return _public({"identity": identity, "workspace": workspace})
    except Exception as exc:
        raise _error(exc) from None


@router.get("/connection")
def get_connection():
    try:
        return _public(store.connection())
    except ValueError:
        raise HTTPException(400, detail={"error": "invalid_profile", "recoverable": True}) from None


@router.delete("/connection", status_code=204)
def delete_connection():
    try:
        store.delete()
    except ValueError:
        raise HTTPException(400, detail={"error": "invalid_profile", "recoverable": True}) from None


@router.get("/health")
def health():
    try:
        current = store.connection()
        if current is None:
            return {"status": "disconnected"}
        identity, workspace = _validated_connection(current["access_token"])
        return {"status": "ok", "identity": identity, "workspace": workspace}
    except Exception as exc:
        raise _error(exc) from None


@router.post("/oauth/start")
def oauth_start():
    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    with _oauth_lock:
        _oauth_states[state] = _OAuthState(verifier, time.monotonic() + _OAUTH_TTL_SECONDS)
    query = urlencode({"response_type": "code", "client_id": "hermes-desktop", "redirect_uri": "http://127.0.0.1/rhythm/callback", "scope": "openid email profile", "code_challenge_method": "S256", "code_challenge": challenge, "state": state})
    return {"state": state, "authorization_url": f"https://accounts.google.com/o/oauth2/v2/auth?{query}"}


@router.post("/oauth/callback")
def oauth_callback(payload: OAuthCallback):
    with _oauth_lock:
        state = _oauth_states.get(payload.state)
        if state is None or state.consumed:
            raise HTTPException(409, detail={"error": "oauth_state_replayed", "recoverable": True})
        if state.expires_at <= time.monotonic():
            _oauth_states.pop(payload.state, None)
            raise HTTPException(410, detail={"error": "oauth_state_expired", "recoverable": True})
        state.consumed = True
    try:
        token = RhythmClient("", transport=request).exchange_code(payload.code, state.verifier)
        identity, workspace = _validated_connection(token)
        store.save(token, identity, workspace)
        return _public({"identity": identity, "workspace": workspace})
    except Exception as exc:
        raise _error(exc) from None
    finally:
        with _oauth_lock:
            _oauth_states.pop(payload.state, None)
