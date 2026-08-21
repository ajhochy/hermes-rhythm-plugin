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
from datetime import date
from typing import Literal
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

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
@dataclass
class _TaskConfirmation:
    task_id: str
    operation: Literal["complete", "reschedule"]
    scheduled_date: str | None
    generation: str
    home: str
    actor_id: str
    workspace_id: str
    intent_digest: str
    expires_at: float


@dataclass
class _TaskIntent:
    expires_at: float
    claimed: bool = False


_task_confirmations: dict[str, _TaskConfirmation] = {}
_task_intents: dict[str, _TaskIntent] = {}
_TASK_CONFIRMATION_TTL_SECONDS = 60
MAX_PENDING_TASK_CONFIRMATIONS = 32
MAX_TASK_OPERATION_INTENTS = 64


class ConnectionInput(BaseModel):
    access_token: str = Field(min_length=8, max_length=2048)


class OAuthCallback(BaseModel):
    state: str = Field(min_length=16, max_length=256)
    code: str = Field(min_length=1, max_length=2048)


class TaskOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["complete", "reschedule"]
    generation: str = Field(min_length=8, max_length=256)
    scheduledDate: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    confirmation: str | None = Field(default=None, min_length=32, max_length=128)


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


def _prune_task_confirmations_locked() -> None:
    now = time.monotonic()
    for key, value in list(_task_confirmations.items()):
        if value.expires_at <= now:
            _task_confirmations.pop(key, None)
    for key, value in list(_task_intents.items()):
        if value.expires_at <= now:
            _task_intents.pop(key, None)


def _task_authorized(task: dict[str, Any], actor_id: str) -> bool:
    """Authorization is by bounded canonical ids only; names/initials are display data."""
    return task["ownerId"] == actor_id or any(row["id"] == actor_id for row in task["collaborators"])


def _operation_intent_digest(actor_id: str, workspace_id: str, task_id: str, operation: str, scheduled_date: str | None, generation: str) -> str:
    material = "\n".join((actor_id, workspace_id, task_id, operation, scheduled_date or "", generation))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


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


def _text(payload: dict[str, Any], name: str, maximum: int, *, required: bool = False) -> str | None:
    value = payload.get(name)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise RhythmProtocolError("schema_drift")
    return value.strip()


def _task(payload: dict[str, Any]) -> dict[str, Any]:
    ident = _text(payload, "id", 128, required=True)
    title = _text(payload, "title", 512, required=True)
    status = payload.get("status")
    bucket = payload.get("bucket")
    if status not in {"open", "in_progress", "waiting_for_reply", "done"} or bucket not in {"past-due", "today", "week", "month", "no-due", "completed"}:
        raise RhythmProtocolError("schema_drift")
    priority = payload.get("priority", 0)
    tags = payload.get("tags", [])
    collaborators = payload.get("collaborators", [])
    if type(priority) is not int or priority not in {0, 1, 2, 3} or not isinstance(tags, list) or len(tags) > 32 or not all(isinstance(tag, str) and 0 < len(tag) <= 64 for tag in tags) or not isinstance(collaborators, list) or len(collaborators) > 32:
        raise RhythmProtocolError("schema_drift")
    safe_collaborators = []
    for collaborator in collaborators:
        if not isinstance(collaborator, dict):
            raise RhythmProtocolError("schema_drift")
        safe_collaborators.append({"id": _text(collaborator, "id", 128, required=True), "name": _text(collaborator, "name", 256, required=True), "initials": _text(collaborator, "initials", 16, required=True)})
    result: dict[str, Any] = {
        "id": ident, "title": title, "notes": _text(payload, "notes", 8_192) or "", "status": status,
        "bucket": bucket, "priority": priority, "tags": tags, "createdAt": _text(payload, "createdAt", 64, required=True),
        "createdBy": _text(payload, "createdBy", 256, required=True), "ownerId": _text(payload, "ownerId", 128, required=True),
        "isShared": payload.get("isShared") is True, "sourceType": payload.get("sourceType", "manual"),
        "preferredAgent": payload.get("preferredAgent", ""), "energy": payload.get("energy", ""), "collaborators": safe_collaborators,
    }
    if result["sourceType"] not in {"manual", "rhythm", "project", "automation", "calendar_shadow_event", "prod_mirror"} or result["preferredAgent"] not in {"", "claude-code", "codex"} or result["energy"] not in {"", "🔥", "⚡", "🌱"}:
        raise RhythmProtocolError("schema_drift")
    for name in ("scheduledDate", "dueDate", "sourceName"):
        value = _text(payload, name, 256)
        if value is not None:
            result[name] = value
    return result


def _dashboard_summary(payload: dict[str, Any], identity: dict[str, str], workspace: dict[str, str]) -> dict[str, Any]:
    count = payload.get("openTaskCount")
    thread_count = payload.get("threadCount")
    tasks = payload.get("tasks")
    project = payload.get("project")
    threads = payload.get("unreadThreads")
    if type(count) is not int or not 0 <= count <= 10_000 or type(thread_count) is not int or not 0 <= thread_count <= 10_000 or not isinstance(tasks, list) or len(tasks) > 100 or project is not None or not isinstance(threads, list) or threads:
        raise RhythmProtocolError("schema_drift")
    summary_tasks = []
    for raw in tasks:
        if not isinstance(raw, dict):
            raise RhythmProtocolError("schema_drift")
        status, bucket = raw.get("status"), raw.get("bucket")
        if status not in {"open", "done"} or bucket not in {"past-due", "today", "week", "unscheduled"}:
            raise RhythmProtocolError("schema_drift")
        summary_tasks.append({"id": _text(raw, "id", 128, required=True), "title": _text(raw, "title", 512, required=True), "notes": _text(raw, "notes", 8_192) or "", "status": status, "bucket": bucket, "dueLabel": _text(raw, "dueLabel", 128, required=True)})
    return {"identity": identity, "workspace": workspace, "openTaskCount": count, "threadCount": thread_count, "tasks": summary_tasks, "project": None, "unreadThreads": []}


def _error(exc: Exception) -> HTTPException:
    # Route handlers deliberately raise public, bounded HTTP errors for stale
    # receipts and capacity limits.  Translating them again would turn a 409/429
    # into a misleading 502 and erase the client-visible outcome code.
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, ValueError):
        return HTTPException(400, detail={"error": "invalid_profile", "recoverable": True})
    if isinstance(exc, RhythmRemoteError):
        status = {"unauthorized": 401, "forbidden": 403, "not_found": 404, "conflict": 409, "uncertain": 409, "rate_limited": 429, "timeout": 504, "dns": 502, "tls": 502}.get(exc.kind, 502)
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


def _connected_client() -> tuple[RhythmClient, dict[str, str], dict[str, str]]:
    current = store.connection()
    if current is None:
        raise RhythmRemoteError("unauthorized")
    return RhythmClient(current["access_token"], transport=request), current["identity"], current["workspace"]


@router.api_route("/dashboard-summary", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def dashboard_summary(incoming_request: Request):
    if incoming_request.method != "GET":
        raise HTTPException(405, detail={"error": "read_only", "recoverable": True})
    try:
        client, identity, workspace = _connected_client()
        return _dashboard_summary(client.call("GET", "/dashboard/summary"), identity, workspace)
    except Exception as exc:
        raise _error(exc) from None


@router.api_route("/tasks", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def task_list(incoming_request: Request):
    if incoming_request.method != "GET":
        raise HTTPException(405, detail={"error": "read_only", "recoverable": True})
    try:
        client, _, _ = _connected_client()
        payload = client.call("GET", "/tasks")
        rows = payload.get("tasks")
        if not isinstance(rows, list) or len(rows) > 500:
            raise RhythmProtocolError("schema_drift")
        if not all(isinstance(row, dict) for row in rows):
            raise RhythmProtocolError("schema_drift")
        return {"tasks": [_task(row) for row in rows]}
    except Exception as exc:
        raise _error(exc) from None


@router.api_route("/tasks/{task_id}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def task_detail(task_id: str, incoming_request: Request):
    if incoming_request.method != "GET":
        raise HTTPException(405, detail={"error": "read_only", "recoverable": True})
    try:
        client, _, _ = _connected_client()
        detail = _task(client.call("GET", f"/tasks/{task_id}"))
        if detail["id"] != task_id:
            raise RhythmProtocolError("schema_drift")
        return detail
    except Exception as exc:
        raise _error(exc) from None


@router.post("/tasks/{task_id}/confirmation")
async def task_operation_confirmation(task_id: str, incoming_request: Request):
    payload = await _validated_body(incoming_request, TaskOperation)
    if payload.operation == "reschedule" and not payload.scheduledDate:
        raise _invalid_request()
    if payload.operation == "complete" and payload.scheduledDate is not None:
        raise _invalid_request()
    if payload.scheduledDate is not None:
        try:
            if date.fromisoformat(payload.scheduledDate).isoformat() != payload.scheduledDate:
                raise ValueError
        except ValueError:
            raise _invalid_request() from None
    try:
        client, identity, workspace = _connected_client()
        detail = _task(client.call("GET", f"/tasks/{task_id}"))
        if detail["id"] != task_id or not _task_authorized(detail, identity["id"]):
            raise RhythmRemoteError("forbidden")
        intent_digest = _operation_intent_digest(identity["id"], workspace["id"], task_id, payload.operation, payload.scheduledDate, payload.generation)
        nonce = secrets.token_urlsafe(32)
        with _oauth_lock:
            _prune_task_confirmations_locked()
            if intent_digest in _task_intents:
                raise HTTPException(409, detail={"error": "confirmation_already_issued", "recoverable": True})
            if len(_task_confirmations) >= MAX_PENDING_TASK_CONFIRMATIONS:
                raise HTTPException(429, detail={"error": "confirmation_pending_limit", "recoverable": True})
            if len(_task_intents) >= MAX_TASK_OPERATION_INTENTS:
                raise HTTPException(429, detail={"error": "confirmation_pending_limit", "recoverable": True})
            expires_at = time.monotonic() + _TASK_CONFIRMATION_TTL_SECONDS
            _task_intents[intent_digest] = _TaskIntent(expires_at)
            _task_confirmations[nonce] = _TaskConfirmation(task_id, payload.operation, payload.scheduledDate, payload.generation, _canonical_home(), identity["id"], workspace["id"], intent_digest, expires_at)
        return {"confirmation": nonce, "task": detail}
    except Exception as exc:
        raise _error(exc) from None


@router.post("/tasks/{task_id}/operations")
async def task_operation(task_id: str, incoming_request: Request):
    payload = await _validated_body(incoming_request, TaskOperation)
    if not payload.confirmation:
        raise HTTPException(409, detail={"error": "confirmation_required", "recoverable": True})
    with _oauth_lock:
        _prune_task_confirmations_locked()
        bound = _task_confirmations.get(payload.confirmation)
    if bound is None or bound.home != _canonical_home() or (bound.task_id, bound.operation, bound.scheduled_date, bound.generation) != (task_id, payload.operation, payload.scheduledDate, payload.generation):
        raise HTTPException(409, detail={"error": "stale_confirmation", "recoverable": True})
    try:
        client, _, _ = _connected_client()
        # Reconnect/read immediately before the one mutation; stored metadata is
        # not authority and a connection/profile switch must fail closed.
        identity = _safe_identity(client.call("GET", "/auth/me"))
        workspace = _safe_workspace(client.call("GET", "/workspaces/me"))
        detail = _task(client.call("GET", f"/tasks/{task_id}"))
        if identity["id"] != bound.actor_id or workspace["id"] != bound.workspace_id:
            raise HTTPException(409, detail={"error": "stale_confirmation", "recoverable": True})
        if detail["id"] != task_id or not _task_authorized(detail, identity["id"]):
            raise RhythmRemoteError("forbidden")
        with _oauth_lock:
            # Do not consume a usable receipt on an attacker/mismatch request;
            # only the exact, revalidated intent gets the single-flight lease.
            if _task_confirmations.get(payload.confirmation) is not bound:
                raise HTTPException(409, detail={"error": "stale_confirmation", "recoverable": True})
            intent = _task_intents.get(bound.intent_digest)
            if intent is None or intent.expires_at <= time.monotonic() or intent.claimed:
                raise HTTPException(409, detail={"error": "stale_confirmation", "recoverable": True})
            # This in-memory lease remains through success, conflict, and
            # ambiguity.  A process restart has no receipt/lease and therefore
            # rejects the old nonce rather than issuing a repeat PATCH.
            intent.claimed = True
            _task_confirmations.pop(payload.confirmation, None)
        return _task(client.mutate_task(task_id, payload.operation, payload.scheduledDate, idempotency_key=bound.intent_digest))
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
