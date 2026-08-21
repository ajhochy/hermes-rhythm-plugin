"""Mounted Rhythm REST routes. Secrets remain server-side at all times."""

from __future__ import annotations

import base64
import hashlib
import json
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
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from plugins.rhythm.backend.client import (
    OAUTH_CLIENT_ID,
    RhythmClient,
    RhythmProtocolError,
    RhythmRemoteError,
    _httpx_transport,
)
from plugins.rhythm.backend import store
from plugins.rhythm.dashboard import artifact_host

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
_workspace_confirmations: dict[str, _TaskConfirmation] = {}
_workspace_intents: dict[str, _TaskIntent] = {}


class WorkspaceOperation(BaseModel):
    """A deliberately non-proxy M5 envelope.  `operation` selects one entry in
    `_M5_UPSTREAM`; every payload is validated and projected server-side."""
    model_config = ConfigDict(extra="forbid")
    operation: Literal[
        "planner.schedule-task", "planner.update-task", "planner.update-project-step", "planner.schedule-project-step",
        "rhythms.create-rule", "rhythms.update-rule", "rhythms.delete-rule", "rhythms.create-step", "rhythms.update-step",
        "projects.create-template", "projects.update-template", "projects.delete-template", "projects.create-instance",
        "projects.update-step", "projects.update-template-step", "projects.create-step", "projects.delete-step", "projects.create-milestone",
        "messages.mark-read", "messages.mark-unread",
        "facilities.create-facility", "facilities.update-facility", "facilities.delete-facility",
        "facilities.create-reservation", "facilities.update-reservation", "facilities.delete-reservation",
        "facilities.update-group", "facilities.delete-group", "facilities.delete-series", "facilities.delete-reservations",
    ]
    entityId: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    payload: dict[str, str | int | bool | None | list[dict[str, str | int | bool | None]]] = Field(default_factory=dict, max_length=16)
    generation: str = Field(min_length=8, max_length=256)
    confirmation: str | None = Field(default=None, min_length=32, max_length=128)

    @model_validator(mode="after")
    def _operation_payload_is_exact(self):
        # Keep the envelope closed at Pydantic's ingress as well as at the
        # route boundary.  The normalized value is what receipt hashing and
        # mutation use, so equivalent payload ordering cannot change intent.
        self.payload = _m5_payload(self.operation, self.payload)
        return self


_M5_UPSTREAM: dict[str, tuple[str, str]] = {
    "planner.schedule-task": ("PATCH", "/tasks/{id}"), "planner.update-task": ("PATCH", "/tasks/{id}"),
    "planner.update-project-step": ("PATCH", "/project-instances/steps/{id}"), "planner.schedule-project-step": ("PATCH", "/project-instances/steps/{id}"),
    "rhythms.create-rule": ("POST", "/recurring-rules"), "rhythms.update-rule": ("PATCH", "/recurring-rules/{id}"), "rhythms.delete-rule": ("DELETE", "/recurring-rules/{id}"),
    "rhythms.create-step": ("POST", "/recurring-rules/{id}/steps"), "rhythms.update-step": ("PATCH", "/recurring-rules/{id}"),
    "projects.create-template": ("POST", "/project-templates"), "projects.update-template": ("PATCH", "/project-templates/{id}"), "projects.delete-template": ("DELETE", "/project-templates/{id}"),
    "projects.create-instance": ("POST", "/project-templates/{id}/generate"), "projects.update-step": ("PATCH", "/project-instances/steps/{id}"), "projects.update-template-step": ("PATCH", "/project-templates/{templateId}/steps/{id}"),
    "projects.create-step": ("POST", "/project-templates/{id}/steps"), "projects.delete-step": ("DELETE", "/project-templates/{templateId}/steps/{id}"),
    "projects.create-milestone": ("POST", "/project-instances/{id}/milestones"),
    "messages.mark-read": ("PATCH", "/message-threads/{id}"), "messages.mark-unread": ("PATCH", "/message-threads/{id}"),
    "facilities.create-facility": ("POST", "/facilities"), "facilities.update-facility": ("PATCH", "/facilities/{id}"), "facilities.delete-facility": ("DELETE", "/facilities/{id}"),
    "facilities.create-reservation": ("POST", "/facilities/{facilityId}/reservations"), "facilities.update-reservation": ("PATCH", "/facilities/{facilityId}/reservations/{id}"), "facilities.delete-reservation": ("DELETE", "/facilities/{facilityId}/reservations/{id}"),
    "facilities.update-group": ("PATCH", "/facilities/{facilityId}/reservations/{id}"), "facilities.delete-group": ("DELETE", "/facilities/{facilityId}/reservations/{id}"), "facilities.delete-series": ("DELETE", "/facilities/{facilityId}/reservation-series/{id}"), "facilities.delete-reservations": ("DELETE", "/facilities/automation-reservations"),
}


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
    for key, value in list(_workspace_confirmations.items()):
        if value.expires_at <= now:
            _workspace_confirmations.pop(key, None)
    for key, value in list(_workspace_intents.items()):
        if value.expires_at <= now:
            _workspace_intents.pop(key, None)


def _m5_payload(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate one discriminated M5 operation and return its canonical body.

    This intentionally is not a generic ``dict`` sanitizer: unknown fields are
    rejected before a digest, confirmation, or upstream request exists.
    """
    schemas = {
        "planner.schedule-task": ({"scheduledDate": "date"}, {"scheduledDate"}),
        "planner.update-task": ({"notes": "text", "dueDate": "date?", "scheduledDate": "date?", "status": "task_status"}, set()),
        "planner.update-project-step": ({"notes": "text", "dueDate": "date?", "status": "step_status"}, set()),
        "planner.schedule-project-step": ({"dueDate": "date"}, {"dueDate"}),
        "rhythms.create-rule": ({"title": "short", "frequency": "frequency", "dayOfWeek": "weekday", "dayOfMonth": "day", "month": "month", "sequential": "bool", "enabled": "bool", "steps": "steps"}, {"title", "frequency"}),
        "rhythms.update-rule": ({"title": "short", "frequency": "frequency", "dayOfWeek": "weekday", "dayOfMonth": "day", "month": "month", "sequential": "bool", "enabled": "bool"}, set()),
        "rhythms.delete-rule": ({}, set()),
        "rhythms.create-step": ({"title": "short", "assigneeId": "id?"}, {"title"}),
        "rhythms.update-step": ({"steps": "steps"}, {"steps"}),
        "projects.create-template": ({"name": "short", "description": "text?", "anchorType": "anchor"}, {"name"}),
        "projects.update-template": ({"name": "short", "description": "text?", "anchorType": "anchor"}, set()),
        "projects.delete-template": ({}, set()),
        "projects.create-instance": ({"anchorDate": "date", "name": "short?"}, {"anchorDate"}),
        "projects.update-step": ({"title": "short", "notes": "text", "dueDate": "date?", "scheduledDate": "date?", "status": "step_status", "assigneeId": "id?", "milestoneId": "id?", "instanceId": "id", "templateId": "id"}, {"instanceId"}),
        "projects.update-template-step": ({"templateId": "id", "title": "short", "offsetDays": "offset", "offsetDescription": "short?", "assigneeId": "id?"}, {"templateId"}),
        "projects.create-step": ({"templateId": "id", "title": "short", "offsetDays": "offset", "offsetDescription": "short?", "assigneeId": "id?"}, {"templateId", "title", "offsetDays"}),
        "projects.delete-step": ({"templateId": "id"}, {"templateId"}),
        "projects.create-milestone": ({"title": "short"}, {"title"}),
        "messages.mark-read": ({"unreadCount": "zero"}, {"unreadCount"}),
        "messages.mark-unread": ({"unreadCount": "one"}, {"unreadCount"}),
        "facilities.create-facility": ({"name": "short", "building": "short?", "description": "text?"}, {"name"}),
        "facilities.update-facility": ({"name": "short", "building": "short?", "description": "text?"}, set()),
        "facilities.delete-facility": ({}, set()),
        "facilities.create-reservation": ({"facilityId": "id", "title": "short", "requesterName": "short?", "start": "timestamp", "end": "timestamp", "notes": "text?"}, {"facilityId", "title", "start", "end"}),
        "facilities.update-reservation": ({"facilityId": "id", "title": "short", "requesterName": "short?", "start": "timestamp", "end": "timestamp", "notes": "text?"}, {"facilityId"}),
        "facilities.delete-reservation": ({"facilityId": "id"}, {"facilityId"}),
        "facilities.update-group": ({"facilityId": "id", "title": "short", "requesterName": "short?", "start": "timestamp", "end": "timestamp", "notes": "text?"}, {"facilityId"}),
        "facilities.delete-group": ({"facilityId": "id"}, {"facilityId"}),
        "facilities.delete-series": ({"facilityId": "id"}, {"facilityId"}),
        "facilities.delete-reservations": ({"ids": "ids"}, {"ids"}),
    }
    try: allowed, required = schemas[operation]
    except KeyError: raise _invalid_request() from None
    if not isinstance(payload, dict) or set(payload) - set(allowed) or required - set(payload) or (not payload and allowed):
        raise _invalid_request()
    def valid(kind: str, value: Any) -> Any:
        nullable = kind.endswith("?")
        kind = kind.removesuffix("?")
        if value is None and nullable: return None
        if kind in {"short", "text"}:
            maximum = 256 if kind == "short" else 2_000
            if not isinstance(value, str) or not value.strip() or len(value) > maximum: raise _invalid_request()
            return value.strip()
        if kind == "id":
            if not isinstance(value, str) or not _safe_id(value): raise _invalid_request()
            return value
        if kind == "date":
            if not isinstance(value, str) or not _safe_iso_date(value): raise _invalid_request()
            return value
        if kind == "timestamp":
            if not isinstance(value, str) or len(value) > 64 or "T" not in value: raise _invalid_request()
            return value
        if kind == "zero":
            if value != 0: raise _invalid_request()
            return 0
        if kind == "one":
            if value != 1: raise _invalid_request()
            return 1
        if kind == "ids":
            if not isinstance(value, list) or not value or len(value) > 100 or not all(isinstance(item, str) and _safe_id(item) for item in value): raise _invalid_request()
            return sorted(set(value))
        if kind == "bool":
            if type(value) is not bool: raise _invalid_request()
            return value
        if kind == "offset":
            if type(value) is not int or not -3650 <= value <= 3650: raise _invalid_request()
            return value
        if kind == "frequency":
            if value not in {"daily", "weekly", "monthly", "yearly"}: raise _invalid_request()
            return value
        if kind == "weekday":
            if type(value) is not int or not 0 <= value <= 6: raise _invalid_request()
            return value
        if kind == "day":
            if type(value) is not int or not 1 <= value <= 31: raise _invalid_request()
            return value
        if kind == "month":
            if type(value) is not int or not 1 <= value <= 12: raise _invalid_request()
            return value
        if kind == "anchor":
            if value not in {"start_date", "due_date", "scheduled_date"}: raise _invalid_request()
            return value
        if kind == "task_status":
            if value not in {"open", "in_progress", "waiting_for_reply", "done"}: raise _invalid_request()
            return value
        if kind == "step_status":
            if value not in {"open", "done"}: raise _invalid_request()
            return value
        if kind == "steps":
            if not isinstance(value, list) or not value or len(value) > 100: raise _invalid_request()
            out = []
            for row in value:
                allowed_step_keys = {"title", "assigneeId"} if operation == "rhythms.create-rule" else {"id", "title", "order", "assigneeId"}
                if not isinstance(row, dict) or set(row) - allowed_step_keys or not isinstance(row.get("title"), str) or not row["title"].strip() or len(row["title"]) > 256:
                    raise _invalid_request()
                if operation != "rhythms.create-rule" and (not isinstance(row.get("id"), str) or not _safe_id(row["id"]) or type(row.get("order")) is not int or not 0 <= row["order"] < 100): raise _invalid_request()
                item = {"title": row["title"].strip()} if operation == "rhythms.create-rule" else {"id": row["id"], "title": row["title"].strip(), "order": row["order"]}
                if "assigneeId" in row: item["assigneeId"] = valid("id?", row["assigneeId"])
                out.append(item)
            return out
        raise _invalid_request()
    normalized = {key: valid(kind, payload[key]) for key, kind in allowed.items() if key in payload}
    return normalized


def _safe_iso_date(value: str) -> bool:
    try: return date.fromisoformat(value).isoformat() == value
    except ValueError: return False


def _safe_id(value: str) -> bool:
    return bool(value) and len(value) <= 128 and all(char.isalnum() or char in "_-" for char in value)


def _task_authorized(task: dict[str, Any], actor_id: str) -> bool:
    """Authorization is by bounded canonical ids only; names/initials are display data."""
    return task["ownerId"] == actor_id or any(row["id"] == actor_id for row in task["collaborators"])


def _operation_intent_digest(actor_id: str, workspace_id: str, task_id: str, operation: str, scheduled_date: str | None, generation: str) -> str:
    material = "\n".join((actor_id, workspace_id, task_id, operation, scheduled_date or "", generation))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _safe_identity(payload: dict[str, Any]) -> dict[str, Any]:
    ident = payload.get("id")
    email = payload.get("email")
    if not isinstance(ident, str) or not ident or len(ident) > 128:
        raise RhythmProtocolError("schema_drift")
    result = {"id": ident}
    if isinstance(email, str) and 3 <= len(email) <= 320 and "@" in email:
        result["email"] = email
    if type(payload.get("isFacilitiesManager")) is bool:
        result["isFacilitiesManager"] = payload["isFacilitiesManager"]
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


def _m5_digest(identity: dict[str, str], workspace: dict[str, str], payload: WorkspaceOperation) -> str:
    material = json.dumps([identity["id"], workspace["id"], payload.operation, payload.entityId, payload.payload, payload.generation], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode()).hexdigest()


def _canonical_m5_result(operation: str, entity_id: str, result: dict[str, Any]) -> dict[str, Any]:
    """Never publish an upstream mutation response for a different entity.

    Creation endpoints legitimately allocate a new id; every existing-entity
    operation must echo the exact canonical id it was authorized against.
    """
    creates = {"rhythms.create-rule", "projects.create-template", "projects.create-instance", "projects.create-step", "projects.create-milestone"}
    if operation not in creates and result.get("id") != entity_id:
        raise RhythmProtocolError("schema_drift")
    if operation in creates and (not isinstance(result.get("id"), str) or not result["id"]):
        raise RhythmProtocolError("schema_drift")
    return result


def _m5_readback_path(operation: str, entity_id: str, payload: dict[str, Any], *, parent_id: str | None = None) -> str:
    if operation.startswith("planner."):
        return f"/tasks/{entity_id}" if "task" in operation else f"/project-instances/steps/{entity_id}"
    if operation.startswith("rhythms."):
        return f"/recurring-rules/{entity_id}"
    if operation == "projects.update-template-step":
        return f"/project-templates/{payload['templateId']}/steps/{entity_id}"
    if operation == "projects.update-template" or operation == "projects.delete-template":
        return f"/project-templates/{entity_id}"
    if operation == "projects.update-step":
        return f"/project-instances/steps/{entity_id}"
    if operation == "projects.create-template": return f"/project-templates/{entity_id}"
    if operation == "projects.create-instance": return f"/project-instances/{entity_id}"
    if operation == "projects.create-step": return f"/project-templates/{parent_id}/steps/{entity_id}"
    if operation == "projects.create-milestone": return f"/project-instances/{parent_id}/milestones/{entity_id}"
    return f"/project-templates/{entity_id}"


def _m5_authorization_path(operation: str, entity_id: str, payload: dict[str, Any]) -> str | None:
    """The target (or parent) that must be canonically re-authorized."""
    if operation in {"rhythms.create-rule", "projects.create-template"}: return None
    if operation.startswith("planner.schedule-task") or operation.startswith("planner.update-task"): return f"/tasks/{entity_id}"
    if operation.startswith("planner.") or operation == "projects.update-step": return f"/project-instances/steps/{entity_id}"
    if operation == "projects.update-template-step": return f"/project-templates/{payload.get('templateId')}/steps/{entity_id}"
    if operation.startswith("rhythms."):
        return f"/recurring-rules/{entity_id}"
    if operation in {"projects.create-instance", "projects.create-step", "projects.delete-step"}: return f"/project-templates/{payload.get('templateId', entity_id)}"
    if operation == "projects.create-milestone": return f"/project-instances/{entity_id}"
    return f"/project-templates/{entity_id}"


def _m6_authorization_path(operation: str, entity_id: str, payload: dict[str, Any]) -> str | None:
    if operation.startswith("messages."): return f"/message-threads/{entity_id}"
    if operation in {"facilities.create-facility", "facilities.delete-reservations"}: return None
    if operation.startswith("facilities."):
        facility_id = payload.get("facilityId")
        return f"/facilities/{facility_id if isinstance(facility_id, str) else entity_id}"
    return None


def _m6_authorized(operation: str, target: Any, identity: dict[str, str], workspace: dict[str, str]) -> bool:
    if not isinstance(target, dict) or target.get("workspaceId") != workspace["id"]: return False
    if operation.startswith("messages."):
        return any(isinstance(row, dict) and row.get("id") == identity["id"] for row in target.get("participants", []))
    if identity.get("isFacilitiesManager") is True: return True
    if operation in {"facilities.update-facility", "facilities.delete-facility"}: return False
    return target.get("creatorId") == identity["id"] or target.get("createdByUserId") == identity["id"]


def _m6_workspace_can_manage(workspace: dict[str, Any]) -> bool:
    return workspace.get("role") in {"owner", "admin", "facilities_manager"}


def _m6_result(operation: str, entity_id: str, result: dict[str, Any]) -> dict[str, Any]:
    if operation in {"facilities.create-facility", "facilities.create-reservation"}:
        if not isinstance(result.get("id"), str) or not result["id"]: raise RhythmProtocolError("schema_drift")
    elif operation.startswith("facilities.delete"):
        return {"id": entity_id, "deleted": True}
    elif result.get("id") != entity_id:
        raise RhythmProtocolError("schema_drift")
    return result


def _m6_public(operation: str, value: Any) -> Any:
    if operation.startswith("messages."):
        if not isinstance(value, dict) or value.get("id") is None: raise RhythmProtocolError("schema_drift")
        return {"id": _m5_id(value), "unreadCount": value.get("unreadCount", 0)}
    if operation.startswith("facilities."):
        if isinstance(value, list): return [_facility_reservation(row) for row in value]
        if not isinstance(value, dict): raise RhythmProtocolError("schema_drift")
        return _facility_reservation(value) if "facilityId" in value else _facility(value)
    raise RhythmProtocolError("schema_drift")


def _facility(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict): raise RhythmProtocolError("schema_drift")
    building = raw.get("building")
    if building is not None and (not isinstance(building, str) or len(building) > 256): raise RhythmProtocolError("schema_drift")
    return {"id": _m5_id(raw), "name": _m5_text(raw.get("name"), 256), "building": building.strip() if isinstance(building, str) else None, "description": _m5_text(raw.get("description"), 2_000, "")}


def _facility_reservation(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict): raise RhythmProtocolError("schema_drift")
    notes = raw.get("notes")
    if notes is not None and (not isinstance(notes, str) or len(notes) > 2_000): raise RhythmProtocolError("schema_drift")
    result = {"id": _m5_id(raw), "facilityId": _m5_id(raw, "facilityId"), "title": _m5_text(raw.get("title"), 256), "requesterName": _m5_text(raw.get("requesterName"), 256, "Unknown"), "creatorId": _m5_id(raw, "creatorId"), "start": _m5_text(raw.get("start"), 64), "end": _m5_text(raw.get("end"), 64), "notes": notes.strip() if isinstance(notes, str) else None}
    for name in ("seriesId", "groupId"):
        if raw.get(name) is not None: result[name] = _m5_id(raw, name)
    for name in ("external", "conflicted", "automation"):
        if raw.get(name) is not None:
            if type(raw[name]) is not bool: raise RhythmProtocolError("schema_drift")
            result[name] = raw[name]
    return result


def _message_thread(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict): raise RhythmProtocolError("schema_drift")
    typ = raw.get("type", raw.get("threadType"))
    if typ not in {"direct", "group"}: raise RhythmProtocolError("schema_drift")
    return {"id": _m5_id(raw), "title": _m5_text(raw.get("title"), 256, "Untitled"), "type": typ, "participants": _m5_list(raw, "participants", _m5_member, 64), "messages": _m5_list(raw, "messages", _message, 500), "lastMessage": _m5_text(raw.get("lastMessage"), 2_000, ""), "updatedAt": _m5_text(raw.get("updatedAt"), 64, ""), "unreadCount": raw.get("unreadCount", 0)}


def _message(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict): raise RhythmProtocolError("schema_drift")
    return {"id": _m5_id(raw), "senderId": _m5_id(raw, "senderId"), "senderName": _m5_text(raw.get("senderName"), 256), "body": _m5_text(raw.get("body"), 8_192), "createdAt": _m5_text(raw.get("createdAt"), 64)}


def _m5_authorized(raw: Any, identity: dict[str, str], workspace: dict[str, str]) -> bool:
    if not isinstance(raw, dict) or raw.get("workspaceId") != workspace["id"]: return False
    if raw.get("ownerId") == identity["id"]: return True
    collaborators = raw.get("collaborators", [])
    return isinstance(collaborators, list) and any(isinstance(row, dict) and row.get("id") == identity["id"] and row.get("role") in {"owner", "editor", "write"} for row in collaborators)


def _m5_workspace_can_create(workspace: dict[str, Any]) -> bool:
    return workspace.get("role") in {"owner", "admin", "editor"}


def _m5_desired(raw: Any, entity_id: str, body: dict[str, Any]) -> bool:
    return isinstance(raw, dict) and raw.get("id") == entity_id and all(raw.get(key) == value for key, value in body.items())


def _m5_text(value: Any, maximum: int = 2_000, default: str | None = None) -> str:
    if value is None and default is not None: return default
    if value == "" and default == "": return ""
    if not isinstance(value, str) or not value.strip() or len(value) > maximum: raise RhythmProtocolError("schema_drift")
    return value.strip()


def _m5_id(raw: dict[str, Any], name: str = "id") -> str:
    value = raw.get(name)
    if not isinstance(value, str) or not _safe_id(value): raise RhythmProtocolError("schema_drift")
    return value


def _m5_list(raw: dict[str, Any], name: str, projector: Any, maximum: int = 500) -> list[dict[str, Any]]:
    value = raw.get(name, [])
    if not isinstance(value, list) or len(value) > maximum: raise RhythmProtocolError("schema_drift")
    return [projector(row) for row in value]


def _m5_member(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict): raise RhythmProtocolError("schema_drift")
    return {"id": _m5_id(raw), "name": _m5_text(raw.get("name"), 256, "Unknown"), "initials": _m5_text(raw.get("initials"), 16, "?")}


def _planner_task(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict): raise RhythmProtocolError("schema_drift")
    source = raw.get("source", "task")
    status = raw.get("status", "open")
    if source not in {"task", "project-step"} or status not in {"open", "done"}: raise RhythmProtocolError("schema_drift")
    result = {"id": _m5_id(raw), "source": source, "title": _m5_text(raw.get("title"), 512, "Untitled"), "notes": _m5_text(raw.get("notes"), 8_192, ""), "status": status, "scheduledOrder": raw.get("scheduledOrder", 0), "collaborators": _m5_list(raw, "collaborators", _m5_member, 32), "readonly": raw.get("readonly", False)}
    if type(result["scheduledOrder"]) is not int or result["scheduledOrder"] < 0 or type(result["readonly"]) is not bool: raise RhythmProtocolError("schema_drift")
    for name in ("projectStepId", "scheduledDate", "dueDate", "projectName", "energy"):
        if name in raw:
            result[name] = _m5_text(raw[name], 128)
    return result


def _planner_event(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict): raise RhythmProtocolError("schema_drift")
    all_day = raw.get("allDay", True)
    if type(all_day) is not bool: raise RhythmProtocolError("schema_drift")
    return {"id": _m5_id(raw), "title": _m5_text(raw.get("title"), 512, "Untitled"), "date": _m5_text(raw.get("date"), 32), "timeLabel": _m5_text(raw.get("timeLabel"), 128, "All day"), "notes": _m5_text(raw.get("notes"), 8_192, ""), "allDay": all_day}


def _planner_week_public(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict): raise RhythmProtocolError("schema_drift")
    days = value.get("days", [])
    if not isinstance(days, list) or len(days) > 100: raise RhythmProtocolError("schema_drift")
    projected_days = []
    for raw in days:
        if not isinstance(raw, dict): raise RhythmProtocolError("schema_drift")
        projected_days.append({"date": _m5_text(raw.get("date"), 32), "label": _m5_text(raw.get("label"), 128, _m5_text(raw.get("date"), 32)), "tasks": _m5_list(raw, "tasks", _planner_task, 200), "events": _m5_list(raw, "events", _planner_event, 200)})
    return {"weekStart": _m5_text(value.get("weekStart"), 32), "weekLabel": _m5_text(value.get("weekLabel"), 128, _m5_text(value.get("weekStart"), 32)), "days": projected_days, "backlog": _m5_list(value, "backlog", _planner_task, 200)}


def _rhythm_step(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict): raise RhythmProtocolError("schema_drift")
    result = {"id": _m5_id(raw), "title": _m5_text(raw.get("title"), 512, "Untitled")}
    if raw.get("assigneeId") is not None: result["assigneeId"] = _m5_id(raw, "assigneeId")
    return result


def _rhythm_rule(raw: Any, actor_id: str | None = None) -> dict[str, Any]:
    if not isinstance(raw, dict): raise RhythmProtocolError("schema_drift")
    frequency = raw.get("frequency", "weekly")
    if frequency not in {"weekly", "monthly", "annual"}: frequency = "annual" if frequency == "yearly" else (_ for _ in ()).throw(RhythmProtocolError("schema_drift"))
    owner_id = _m5_text(raw.get("ownerId"), 128, "unknown")
    result = {"id": _m5_id(raw), "title": _m5_text(raw.get("title"), 512, "Untitled"), "frequency": frequency, "dayOfWeek": raw.get("dayOfWeek", 0), "dayOfMonth": raw.get("dayOfMonth", 1), "month": raw.get("month", 1), "sequential": raw.get("sequential", False), "enabled": raw.get("enabled", True), "ownerId": "current-user" if actor_id and owner_id == actor_id else owner_id, "ownerName": _m5_text(raw.get("ownerName"), 256, "Unknown"), "collaborators": _m5_list(raw, "collaborators", _m5_member, 32), "steps": _m5_list(raw, "steps", _rhythm_step, 100), "generatedCount": raw.get("generatedCount", 0), "completedCount": raw.get("completedCount", 0), "remainingCount": raw.get("remainingCount", 0), "waitingOn": raw.get("waitingOn", None), "nextDueDate": raw.get("nextDueDate", None), "completionRatio": raw.get("completionRatio", 0), "createdAt": _m5_text(raw.get("createdAt"), 64, "1970-01-01")}
    if not all(type(result[key]) is int and result[key] >= 0 for key in ("dayOfWeek", "dayOfMonth", "month", "generatedCount", "completedCount", "remainingCount")) or type(result["completionRatio"]) not in {int, float} or not all(type(result[key]) is bool for key in ("sequential", "enabled")) or result["waitingOn"] is not None and not isinstance(result["waitingOn"], str) or result["nextDueDate"] is not None and not isinstance(result["nextDueDate"], str): raise RhythmProtocolError("schema_drift")
    return result


def _template_step(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict): raise RhythmProtocolError("schema_drift")
    result = {"id": _m5_id(raw), "title": _m5_text(raw.get("title"), 512, "Untitled"), "offsetDays": raw.get("offsetDays", 0), "offsetDescription": _m5_text(raw.get("offsetDescription"), 256, "")}
    if type(result["offsetDays"]) is not int or not -3650 <= result["offsetDays"] <= 3650: raise RhythmProtocolError("schema_drift")
    if raw.get("assigneeId") is not None: result["assigneeId"] = _m5_id(raw, "assigneeId")
    return result


def _template(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict): raise RhythmProtocolError("schema_drift")
    return {"id": _m5_id(raw), "name": _m5_text(raw.get("name"), 512, "Untitled"), "description": _m5_text(raw.get("description"), 2_000, ""), "anchorType": _m5_text(raw.get("anchorType"), 64, "start_date"), "steps": _m5_list(raw, "steps", _template_step, 100)}


def _project_step(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict): raise RhythmProtocolError("schema_drift")
    status = raw.get("status", "open")
    if status not in {"open", "done"}: raise RhythmProtocolError("schema_drift")
    result = {"id": _m5_id(raw), "title": _m5_text(raw.get("title"), 512, "Untitled"), "notes": _m5_text(raw.get("notes"), 8_192, ""), "status": status}
    for name in ("dueDate", "scheduledDate", "assigneeId", "milestoneId"):
        if raw.get(name) is not None: result[name] = _m5_id(raw, name) if name in {"assigneeId", "milestoneId"} else _m5_text(raw[name], 32)
    return result


def _milestone(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict): raise RhythmProtocolError("schema_drift")
    sort_order = raw.get("sortOrder", 0)
    if type(sort_order) is not int or sort_order < 0: raise RhythmProtocolError("schema_drift")
    return {"id": _m5_id(raw), "title": _m5_text(raw.get("title"), 512, "Untitled"), "sortOrder": sort_order}


def _instance(raw: Any, actor_id: str | None = None) -> dict[str, Any]:
    if not isinstance(raw, dict): raise RhythmProtocolError("schema_drift")
    status = raw.get("status", "planning")
    if status not in {"planning", "active", "on_hold", "complete"}: raise RhythmProtocolError("schema_drift")
    owner_id = _m5_text(raw.get("ownerId"), 128, "unknown")
    return {"id": _m5_id(raw), "templateId": _m5_text(raw.get("templateId"), 128, "unknown"), "name": _m5_text(raw.get("name"), 512, "Untitled"), "anchorDate": _m5_text(raw.get("anchorDate"), 32, "1970-01-01"), "status": status, "ownerId": "current-user" if actor_id and owner_id == actor_id else owner_id, "collaborators": _m5_list(raw, "collaborators", _m5_member, 32), "milestones": _m5_list(raw, "milestones", _milestone, 100), "steps": _m5_list(raw, "steps", _project_step, 500)}


def _m5_operation_kind(operation: str) -> str:
    if operation.startswith("rhythms."): return "rule"
    if operation in {"projects.update-step", "planner.update-project-step", "planner.schedule-project-step"}: return "project_step"
    if operation in {"projects.create-step", "projects.update-template-step"}: return "template_step"
    if operation == "projects.create-milestone": return "milestone"
    if operation == "projects.create-instance": return "instance"
    return "template"


def _m5_public(kind: str, value: Any, actor_id: str | None = None) -> dict[str, Any]:
    if kind == "planner": return _planner_week_public(value)
    if not isinstance(value, dict): raise RhythmProtocolError("schema_drift")
    projectors = {"templates": _template, "template": _template, "project_step": _project_step, "template_step": _template_step, "milestone": _milestone}
    if kind == "templates": return {"items": _m5_list(value, "items", _template, 500)}
    if kind == "rules": return {"items": _m5_list(value, "items", lambda row: _rhythm_rule(row, actor_id), 500)}
    if kind == "instances": return {"items": _m5_list(value, "items", lambda row: _instance(row, actor_id), 500)}
    if kind == "rule": return _rhythm_rule(value, actor_id)
    if kind == "instance": return _instance(value, actor_id)
    return projectors[kind](value)


@router.post("/workspace-operations/confirmation")
async def workspace_operation_confirmation(incoming_request: Request):
    payload = await _validated_body(incoming_request, WorkspaceOperation)
    _m5_payload(payload.operation, payload.payload)
    try:
        client, identity, workspace = _connected_client()
        digest = _m5_digest(identity, workspace, payload)
        nonce = secrets.token_urlsafe(32)
        with _oauth_lock:
            _prune_task_confirmations_locked()
            if digest in _workspace_intents or len(_workspace_confirmations) >= MAX_PENDING_TASK_CONFIRMATIONS:
                raise HTTPException(409, detail={"error": "confirmation_already_issued", "recoverable": True})
            expiry = time.monotonic() + _TASK_CONFIRMATION_TTL_SECONDS
            _workspace_intents[digest] = _TaskIntent(expiry)
            _workspace_confirmations[nonce] = _TaskConfirmation(payload.entityId, payload.operation, None, payload.generation, _canonical_home(), identity["id"], workspace["id"], digest, expiry)
        return {"confirmation": nonce}
    except Exception as exc:
        raise _error(exc) from None


@router.post("/workspace-operations")
async def workspace_operation(incoming_request: Request):
    payload = await _validated_body(incoming_request, WorkspaceOperation)
    body = {key: value for key, value in _m5_payload(payload.operation, payload.payload).items() if key not in {"instanceId", "templateId"}}
    if not payload.confirmation:
        raise HTTPException(409, detail={"error": "confirmation_required", "recoverable": True})
    with _oauth_lock:
        _prune_task_confirmations_locked()
        receipt = _workspace_confirmations.get(payload.confirmation)
    if receipt is None or receipt.home != _canonical_home() or (receipt.task_id, receipt.operation, receipt.generation) != (payload.entityId, payload.operation, payload.generation):
        raise HTTPException(409, detail={"error": "stale_confirmation", "recoverable": True})
    try:
        client, identity, workspace = _connected_client()
        # Stored connection metadata is display cache only. Re-pin actor and
        # workspace immediately before authorization and the one mutation.
        identity = _safe_identity(client.call("GET", "/auth/me"))
        workspace = client.call("GET", "/workspaces/me")
        canonical_workspace = _safe_workspace(workspace)
        if identity["id"] != receipt.actor_id or canonical_workspace["id"] != receipt.workspace_id or _m5_digest(identity, canonical_workspace, payload) != receipt.intent_digest:
            raise HTTPException(409, detail={"error": "stale_confirmation", "recoverable": True})
        if payload.operation.startswith(("messages.", "facilities.")):
            target_path = _m6_authorization_path(payload.operation, payload.entityId, payload.payload)
            if target_path is None:
                if identity.get("isFacilitiesManager") is not True and not _m6_workspace_can_manage(workspace): raise RhythmRemoteError("forbidden")
            else:
                target = client.call("GET", target_path)
                if not _m6_authorized(payload.operation, target, identity, canonical_workspace): raise RhythmRemoteError("forbidden")
            with _oauth_lock:
                intent = _workspace_intents.get(receipt.intent_digest)
                if _workspace_confirmations.get(payload.confirmation) is not receipt or intent is None or intent.claimed:
                    raise HTTPException(409, detail={"error": "stale_confirmation", "recoverable": True})
                intent.claimed = True; _workspace_confirmations.pop(payload.confirmation, None)
            method, template = _M5_UPSTREAM[payload.operation]
            path = template.format(id=payload.entityId, facilityId=payload.payload.get("facilityId", ""))
            upstream_body = {key: value for key, value in body.items() if key != "facilityId"}
            try:
                result = _m6_result(payload.operation, payload.entityId, client.call(method, path, body=upstream_body or None, idempotency_key=receipt.intent_digest, m5=True))
            except RhythmRemoteError as exc:
                if exc.kind in {"timeout", "network", "dns", "upstream_unavailable"}:
                    raise RhythmRemoteError("uncertain", exc.status_code) from exc
                raise
            if method == "DELETE": return result
            read_path = path if payload.operation not in {"facilities.create-facility", "facilities.create-reservation"} else (f"/facilities/{result['id']}" if payload.operation == "facilities.create-facility" else f"/facilities/{payload.payload['facilityId']}/reservations/{result['id']}")
            raw = client.call("GET", read_path)
            if raw.get("id") != result["id"]: raise RhythmRemoteError("conflict", 409)
            return _m6_public(payload.operation, raw)
        target_path = _m5_authorization_path(payload.operation, payload.entityId, payload.payload)
        if target_path is None:
            if not _m5_workspace_can_create(workspace): raise RhythmRemoteError("forbidden")
        else:
            target = client.call("GET", target_path)
            if not _m5_authorized(target, identity, canonical_workspace): raise RhythmRemoteError("forbidden")
        with _oauth_lock:
            intent = _workspace_intents.get(receipt.intent_digest)
            if _workspace_confirmations.get(payload.confirmation) is not receipt or intent is None or intent.claimed:
                raise HTTPException(409, detail={"error": "stale_confirmation", "recoverable": True})
            intent.claimed = True
            _workspace_confirmations.pop(payload.confirmation, None)
        method, template = _M5_UPSTREAM[payload.operation]
        path = template.format(id=payload.entityId, templateId=payload.payload.get("templateId", ""))
        try:
            result = _canonical_m5_result(
                payload.operation, payload.entityId,
                client.call(method, path, body=body or None, idempotency_key=receipt.intent_digest, m5=True),
            )
        except RhythmRemoteError as exc:
            # A failed mutation transport is not success even if a bounded
            # readback now resembles the requested state: another actor may
            # have made the same change. Read once for reconciliation, then
            # force the renderer to reload before retrying.
            if exc.kind in {"timeout", "network", "dns", "upstream_unavailable"}:
                try:
                    client.call("GET", _m5_readback_path(payload.operation, payload.entityId, payload.payload, parent_id=payload.entityId))
                except Exception:
                    pass
                raise RhythmRemoteError("uncertain", exc.status_code) from exc
            raise
        # Never return an upstream mutation response.  Re-read the canonical
        # resource and prove the intended state; ambiguity is never success.
        if method == "DELETE":
            try:
                client.call("GET", target_path or _m5_readback_path(payload.operation, payload.entityId, payload.payload))
            except RhythmRemoteError as exc:
                if exc.kind == "not_found": return {"id": payload.entityId, "deleted": True}
                raise
            raise RhythmRemoteError("conflict", 409)
        readback_id = result["id"] if payload.operation in {"rhythms.create-rule", "projects.create-template", "projects.create-instance", "projects.create-step", "projects.create-milestone"} else payload.entityId
        raw = client.call("GET", _m5_readback_path(payload.operation, readback_id, payload.payload, parent_id=payload.entityId))
        if not _m5_desired(raw, readback_id, body): raise RhythmRemoteError("conflict", 409)
        kind = _m5_operation_kind(payload.operation)
        return _m5_public(kind, raw, identity["id"])
    except Exception as exc:
        raise _error(exc) from None


@router.api_route("/planner/weeks/{week_start}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def planner_week(week_start: str, incoming_request: Request):
    if incoming_request.method != "GET" or not _safe_iso_date(week_start) or date.fromisoformat(week_start).weekday() != 0:
        raise HTTPException(405 if incoming_request.method != "GET" else 422, detail={"error": "read_only" if incoming_request.method != "GET" else "invalid_request", "recoverable": True})
    try:
        client, _, _ = _connected_client(); return _m5_public("planner", client.call("GET", f"/planner/weeks/{week_start}"))
    except Exception as exc: raise _error(exc) from None


@router.api_route("/rhythm-rules", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def rhythm_rules(incoming_request: Request):
    if incoming_request.method != "GET": raise HTTPException(405, detail={"error": "read_only", "recoverable": True})
    try:
        client, identity, _ = _connected_client(); return _m5_public("rules", client.call("GET", "/recurring-rules"), identity["id"])
    except Exception as exc: raise _error(exc) from None


@router.get("/rhythm-rules/{rule_id}")
def rhythm_rule(rule_id: str):
    try:
        client, identity, _ = _connected_client(); detail = _m5_public("rule", client.call("GET", f"/recurring-rules/{rule_id}"), identity["id"])
        if detail.get("id") != rule_id: raise RhythmProtocolError("schema_drift")
        return detail
    except Exception as exc: raise _error(exc) from None


@router.get("/project-templates")
def project_templates():
    try:
        client, _, _ = _connected_client(); return _m5_public("templates", client.call("GET", "/project-templates"))
    except Exception as exc: raise _error(exc) from None


@router.get("/project-instances")
def project_instances():
    try:
        client, identity, _ = _connected_client(); return _m5_public("instances", client.call("GET", "/project-instances"), identity["id"])
    except Exception as exc: raise _error(exc) from None


@router.get("/project-instances/{instance_id}")
def project_instance(instance_id: str):
    try:
        client, identity, _ = _connected_client(); detail = _m5_public("instance", client.call("GET", f"/project-instances/{instance_id}"), identity["id"])
        if detail.get("id") != instance_id: raise RhythmProtocolError("schema_drift")
        return detail
    except Exception as exc: raise _error(exc) from None


def _m7_public(value: Any) -> Any:
    """Bounded JSON projection for the declared M7 read-only resource set."""
    forbidden = {"token", "secret", "credential", "authorization", "url", "href", "path", "cookie"}
    if isinstance(value, str):
        return value[:2_000]
    if type(value) in {int, float, bool} or value is None:
        return value
    if isinstance(value, list):
        return [_m7_public(item) for item in value[:100]]
    if isinstance(value, dict):
        return {str(key)[:80]: _m7_public(item) for key, item in list(value.items())[:100] if not any(word in str(key).lower() for word in forbidden)}
    raise RhythmProtocolError("schema_drift")


@router.get("/automations/catalog")
def automations_catalog():
    try:
        client, _, _ = _connected_client(); return _m7_public(client.call("GET", "/automations/catalog"))
    except Exception as exc: raise _error(exc) from None


@router.get("/automations/rules")
def automations_rules():
    try:
        client, _, _ = _connected_client(); return _m7_public(client.call("GET", "/automations/rules"))
    except Exception as exc: raise _error(exc) from None


@router.get("/automations/rules/{rule_id}/preview")
def automation_preview(rule_id: str):
    if not _safe_id(rule_id): raise _invalid_request()
    try:
        client, _, _ = _connected_client(); return _m7_public(client.call("GET", f"/automations/rules/{rule_id}/preview"))
    except Exception as exc: raise _error(exc) from None


@router.get("/integrations/status")
def integrations_status():
    try:
        client, _, _ = _connected_client(); return _m7_public(client.call("GET", "/integrations/status"))
    except Exception as exc: raise _error(exc) from None


@router.get("/integrations/settings")
def integrations_settings():
    try:
        client, _, _ = _connected_client(); return _m7_public(client.call("GET", "/integrations/settings"))
    except Exception as exc: raise _error(exc) from None


@router.get("/integrations/sync")
def integrations_sync():
    try:
        client, _, _ = _connected_client(); return _m7_public(client.call("GET", "/integrations/sync"))
    except Exception as exc: raise _error(exc) from None


@router.get("/artifacts")
def artifacts():
    try:
        client, _, _ = _connected_client(); return _m7_public(client.call("GET", "/artifacts"))
    except Exception as exc: raise _error(exc) from None


@router.get("/artifacts/{artifact_id}/document")
def artifact_document(artifact_id: str):
    if not _safe_id(artifact_id): raise _invalid_request()
    try:
        client, _, _ = _connected_client(); raw = client.call("GET", f"/artifacts/{artifact_id}/document")
        return artifact_host.open_document(artifact_id, raw.get("bodyHtml", ""), raw.get("styleText", ""), raw.get("scriptText", ""))
    except Exception as exc: raise _error(exc) from None


@router.post("/artifacts/{artifact_id}/open")
async def artifact_open(artifact_id: str, incoming_request: Request):
    """Local test/dev entry point for a host-sanitized artifact bundle.

    Production callers supply the same bounded fields through the server-side
    artifact store; this route never accepts a URL, credential, or transport.
    """
    if not _safe_id(artifact_id):
        raise _invalid_request()
    try:
        payload = await incoming_request.json()
    except (TypeError, ValueError):
        raise _invalid_request() from None
    if not isinstance(payload, dict) or set(payload) - {"bodyHtml", "styleText", "scriptText"}:
        raise _invalid_request()
    return artifact_host.open_document(artifact_id, payload.get("bodyHtml", ""), payload.get("styleText", ""), payload.get("scriptText", ""))


@router.post("/artifacts/{artifact_id}/capability")
async def artifact_capability(artifact_id: str, incoming_request: Request):
    if not _safe_id(artifact_id):
        raise _invalid_request()
    try:
        payload = await incoming_request.json()
    except (TypeError, ValueError):
        raise _invalid_request() from None
    return artifact_host.receive(artifact_id, payload)


@router.get("/messages")
def message_threads():
    try:
        client, _, _ = _connected_client()
        raw = client.call("GET", "/message-threads")
        rows = raw.get("items", raw) if isinstance(raw, dict) else raw
        if not isinstance(rows, list) or len(rows) > 500: raise RhythmProtocolError("schema_drift")
        return [_message_thread(row) for row in rows]
    except Exception as exc: raise _error(exc) from None


@router.get("/messages/{thread_id}/history")
def message_history(thread_id: str):
    if not _safe_id(thread_id): raise _invalid_request()
    try:
        client, _, _ = _connected_client()
        raw = client.call("GET", f"/message-threads/{thread_id}/messages")
        rows = raw.get("items", raw) if isinstance(raw, dict) else raw
        if not isinstance(rows, list) or len(rows) > 500: raise RhythmProtocolError("schema_drift")
        return [_message(row) for row in rows]
    except Exception as exc: raise _error(exc) from None


@router.get("/directory")
def directory():
    try:
        client, _, _ = _connected_client(); raw = client.call("GET", "/users")
        rows = raw.get("items", raw) if isinstance(raw, dict) else raw
        if not isinstance(rows, list) or len(rows) > 500: raise RhythmProtocolError("schema_drift")
        return [_m5_member(row) for row in rows]
    except Exception as exc: raise _error(exc) from None


@router.get("/facilities")
def facilities():
    try:
        client, _, _ = _connected_client(); raw = client.call("GET", "/facilities")
        rows = raw.get("items", raw) if isinstance(raw, dict) else raw
        if not isinstance(rows, list) or len(rows) > 500: raise RhythmProtocolError("schema_drift")
        return [_facility(row) for row in rows]
    except Exception as exc: raise _error(exc) from None


@router.get("/facilities/reservations")
def facility_reservations(start: str, end: str):
    if not start or not end or len(start) > 64 or len(end) > 64: raise _invalid_request()
    try:
        client, _, _ = _connected_client(); raw = client.call("GET", f"/facilities/reservations?{urlencode({'start': start, 'end': end})}")
        rows = raw.get("items", raw) if isinstance(raw, dict) else raw
        if not isinstance(rows, list) or len(rows) > 500: raise RhythmProtocolError("schema_drift")
        return [_facility_reservation(row) for row in rows]
    except Exception as exc: raise _error(exc) from None


@router.get("/facilities/{facility_id}/series")
def facility_series(facility_id: str):
    if not _safe_id(facility_id): raise _invalid_request()
    try:
        client, _, _ = _connected_client(); raw = client.call("GET", f"/facilities/{facility_id}/reservation-series")
        rows = raw.get("items", raw) if isinstance(raw, dict) else raw
        if not isinstance(rows, list) or len(rows) > 500: raise RhythmProtocolError("schema_drift")
        return [_facility_reservation(row) for row in rows]
    except Exception as exc: raise _error(exc) from None


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
