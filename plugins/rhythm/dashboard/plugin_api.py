"""Mounted Rhythm REST routes. Secrets remain server-side at all times."""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError

from plugins.rhythm.backend.client import (
    OAUTH_CLIENT_ID,
    RhythmClient,
    RhythmProtocolError,
    RhythmRemoteError,
    _httpx_transport,
)
from plugins.rhythm.backend import store

router = APIRouter()
log = logging.getLogger(__name__)
request = _httpx_transport
_OAUTH_TTL_SECONDS = 300
MAX_PENDING_OAUTH_STATES = 32
_oauth_lock = threading.Lock()


@dataclass
class _OAuthState:
    verifier: str
    expires_at: float
    home: str
    redirect_uri: str
    consumed: bool = False


_oauth_states: dict[str, _OAuthState] = {}


class ConnectionInput(BaseModel):
    access_token: str = Field(min_length=8, max_length=2048)


class OAuthCallback(BaseModel):
    state: str = Field(min_length=16, max_length=256)
    code: str = Field(min_length=1, max_length=2048)


def _invalid_request() -> HTTPException:
    return HTTPException(422, detail={"error": "invalid_request", "recoverable": True})


async def _validated_body(request: Request, model: type[BaseModel]) -> BaseModel:
    try:
        payload = await request.json()
        return model.model_validate(payload)
    except (TypeError, ValueError, ValidationError):
        raise _invalid_request() from None


def _canonical_home() -> str:
    from hermes_constants import get_hermes_home

    return str(get_hermes_home().resolve(strict=False))


def _loopback_redirect_uri(request: Request) -> str:
    """Build a callback URI from an unproxied, exact loopback request origin."""
    if request.url.scheme != "http" or any(
        request.headers.get(header)
        for header in ("forwarded", "x-forwarded-host", "x-forwarded-proto", "x-forwarded-port")
    ):
        raise HTTPException(400, detail={"error": "invalid_oauth_origin", "recoverable": True})
    host = request.headers.get("host", "").lower()
    if ":" not in host:
        raise HTTPException(400, detail={"error": "invalid_oauth_origin", "recoverable": True})
    hostname, port_text = host.rsplit(":", 1)
    if hostname not in {"127.0.0.1", "localhost"} or not port_text.isdigit():
        raise HTTPException(400, detail={"error": "invalid_oauth_origin", "recoverable": True})
    port = int(port_text)
    if not 1 <= port <= 65535:
        raise HTTPException(400, detail={"error": "invalid_oauth_origin", "recoverable": True})
    return f"http://{hostname}:{port}/api/plugins/rhythm/oauth/callback"


@contextmanager
def _home_scope(home: str):
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override

    token = set_hermes_home_override(home)
    try:
        yield
    finally:
        reset_hermes_home_override(token)


def _prune_oauth_states_locked() -> set[str]:
    now = time.monotonic()
    expired = {key for key, value in _oauth_states.items() if value.expires_at <= now}
    for key in expired:
        _oauth_states.pop(key, None)
    return expired


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
async def put_connection(request: Request):
    payload = await _validated_body(request, ConnectionInput)
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
def oauth_start(incoming_request: Request):
    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    redirect_uri = _loopback_redirect_uri(incoming_request)
    with _oauth_lock:
        _prune_oauth_states_locked()
        if len(_oauth_states) >= MAX_PENDING_OAUTH_STATES:
            raise HTTPException(429, detail={"error": "oauth_pending_limit", "recoverable": True})
        _oauth_states[state] = _OAuthState(
            verifier, time.monotonic() + _OAUTH_TTL_SECONDS, _canonical_home(), redirect_uri
        )
    query = urlencode(
        {
            "response_type": "code",
            "client_id": OAUTH_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "scope": "openid email profile",
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "state": state,
        }
    )
    return {"state": state, "authorization_url": f"https://accounts.google.com/o/oauth2/v2/auth?{query}"}


def _complete_oauth_callback(state_key: str, code: str, incoming_request: Request):
    with _oauth_lock:
        expired = _prune_oauth_states_locked()
        if state_key in expired:
            raise HTTPException(410, detail={"error": "oauth_state_expired", "recoverable": True})
        state = _oauth_states.get(state_key)
        if state is None or state.consumed:
            raise HTTPException(409, detail={"error": "oauth_state_replayed", "recoverable": True})
        if state.home != _canonical_home():
            raise HTTPException(409, detail={"error": "oauth_state_profile_mismatch", "recoverable": True})
        if state.redirect_uri != _loopback_redirect_uri(incoming_request):
            raise HTTPException(409, detail={"error": "oauth_state_origin_mismatch", "recoverable": True})
        state.consumed = True
    try:
        token = RhythmClient("", transport=request).exchange_code(code, state.verifier, state.redirect_uri)
        identity, workspace = _validated_connection(token)
        with _home_scope(state.home):
            store.save(token, identity, workspace)
        return _public({"identity": identity, "workspace": workspace})
    except Exception as exc:
        raise _error(exc) from None
    finally:
        with _oauth_lock:
            _oauth_states.pop(state_key, None)


@router.post("/oauth/callback")
async def oauth_callback(request: Request):
    payload = await _validated_body(request, OAuthCallback)
    return _complete_oauth_callback(payload.state, payload.code, request)


@router.get("/oauth/callback")
def oauth_callback_handoff(request: Request):
    try:
        payload = OAuthCallback.model_validate(
            {
                "state": request.query_params.get("state"),
                "code": request.query_params.get("code"),
            }
        )
    except ValidationError:
        raise _invalid_request() from None
    return _complete_oauth_callback(payload.state, payload.code, request)
