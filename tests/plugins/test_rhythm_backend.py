"""Security contracts for the Rhythm connection backend (#6).

Every network boundary is injected.  These tests deliberately exercise the
plugin router rather than a handler stub so profile scoping and response
redaction cannot be accidentally bypassed by a future route change.
"""

from __future__ import annotations

import gzip
import importlib
import json
import os
import stat
import sys
import threading
import time
from pathlib import Path
from unittest.mock import ANY
from urllib.parse import parse_qsl

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request


TOKEN = "rhythm-test-token-" + "x" * 24
JOIN_CODE = "join-" + "q" * 20


def _router_module():
    sys.modules.pop("plugins.rhythm.dashboard.plugin_api", None)
    return importlib.import_module("plugins.rhythm.dashboard.plugin_api")


@pytest.fixture
def rhythm_home(tmp_path, monkeypatch):
    home = tmp_path / ".hermes" / "profiles" / "rhythm-test"
    home.mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home


@pytest.fixture
def api(rhythm_home):
    mod = _router_module()
    app = FastAPI()
    app.include_router(mod.router, prefix="/api/plugins/rhythm")
    return TestClient(app, base_url="http://127.0.0.1:49123"), mod


def _ok_transport(method, url, headers, body, timeout):
    if url == "https://oauth2.googleapis.com/token":
        assert method == "POST"
        return 200, {}, {"access_token": TOKEN}
    assert url.startswith("https://api.rhythm.app/")
    assert method == "GET"
    assert headers["Authorization"] == f"Bearer {TOKEN}"
    if url.endswith("/auth/me"):
        return 200, {}, {"id": "user-1", "email": "me@example.test", "joinCode": JOIN_CODE}
    if url.endswith("/workspaces/me"):
        return 200, {}, {"id": "ws-1", "name": "Personal", "enrollmentCode": JOIN_CODE}
    raise AssertionError(url)


def _loopback_request(port: int = 49123) -> Request:
    return Request(
        {
            "type": "http",
            "scheme": "http",
            "method": "GET",
            "path": "/api/plugins/rhythm/oauth/callback",
            "headers": [(b"host", f"127.0.0.1:{port}".encode())],
        }
    )


def test_import_has_no_filesystem_or_network_side_effects(monkeypatch, tmp_path):
    """Catches a regression where importing a dashboard plugin writes a store."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "empty"))
    before = list(tmp_path.rglob("*"))
    _router_module()
    assert list(tmp_path.rglob("*")) == before


def test_connection_lifecycle_validates_then_persists_redacted_metadata(api, monkeypatch):
    client, mod = api
    monkeypatch.setattr(mod, "request", _ok_transport)

    response = client.put("/api/plugins/rhythm/connection", json={"access_token": TOKEN})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["connected"] is True
    assert TOKEN not in json.dumps(data)
    assert JOIN_CODE not in json.dumps(data)
    assert data["identity"] == {"id": "user-1", "email": "me@example.test"}
    assert data["workspace"] == {"id": "ws-1", "name": "Personal"}

    assert client.get("/api/plugins/rhythm/connection").json()["connected"] is True
    assert client.get("/api/plugins/rhythm/health").json()["status"] == "ok"
    assert client.delete("/api/plugins/rhythm/connection").status_code == 204
    assert client.get("/api/plugins/rhythm/connection").json()["connected"] is False


def test_failed_validation_rolls_back_and_secret_never_enters_plugin_data(api, monkeypatch, rhythm_home):
    client, mod = api
    monkeypatch.setattr(mod, "request", lambda *args: (401, {}, {"token": TOKEN}))
    result = client.put("/api/plugins/rhythm/connection", json={"access_token": TOKEN})
    assert result.status_code == 401
    assert TOKEN not in result.text
    assert not (rhythm_home / "plugins" / "rhythm").exists()
    auth = rhythm_home / "auth.json"
    assert not auth.exists() or TOKEN not in auth.read_text()


def test_auth_store_is_profile_isolated_and_private(api, monkeypatch, rhythm_home, tmp_path):
    client, mod = api
    monkeypatch.setattr(mod, "request", _ok_transport)
    assert client.put("/api/plugins/rhythm/connection", json={"access_token": TOKEN}).status_code == 200
    store = rhythm_home / "auth.json"
    assert TOKEN in store.read_text()
    assert stat.S_IMODE(store.stat().st_mode) & 0o077 == 0

    other = tmp_path / ".hermes" / "profiles" / "other"
    other.mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(other))
    assert client.get("/api/plugins/rhythm/connection").json()["connected"] is False


@pytest.mark.parametrize("method,path", [("POST", "/anything"), ("PATCH", "/auth/me"), ("GET", "/not-allowed")])
def test_client_rejects_non_allowlisted_operations(method, path):
    from plugins.rhythm.backend.client import RhythmProtocolError, RhythmClient

    with pytest.raises(RhythmProtocolError):
        RhythmClient(TOKEN, transport=_ok_transport).call(method, path)


def test_client_rejects_redirect_and_nonapproved_origin():
    from plugins.rhythm.backend.client import RhythmProtocolError, RhythmClient

    def redirect(*args):
        return 302, {"location": "https://attacker.test/auth/me"}, {}

    with pytest.raises(RhythmProtocolError):
        RhythmClient(TOKEN, transport=redirect).call("GET", "/auth/me")
    with pytest.raises(RhythmProtocolError):
        RhythmClient(TOKEN, transport=_ok_transport).call("GET", "https://attacker.test/auth/me")


def test_read_retry_is_bounded_and_only_retries_safe_get():
    from plugins.rhythm.backend.client import RhythmClient

    calls = []
    def flaky(*args):
        calls.append(args)
        return (503, {}, {}) if len(calls) == 1 else (200, {}, {"id": "u"})

    assert RhythmClient(TOKEN, transport=flaky, sleep=lambda _: None).call("GET", "/auth/me") == {"id": "u"}
    assert len(calls) == 2


@pytest.mark.parametrize("status,kind", [(401, "unauthorized"), (403, "forbidden"), (404, "not_found"), (409, "conflict"), (429, "rate_limited"), (500, "upstream_unavailable")])
def test_error_mappings_are_distinct(status, kind):
    from plugins.rhythm.backend.client import RhythmRemoteError, RhythmClient

    with pytest.raises(RhythmRemoteError) as exc:
        RhythmClient(TOKEN, transport=lambda *args: (status, {}, {"access_token": TOKEN})).call("GET", "/auth/me")
    assert exc.value.kind == kind
    assert TOKEN not in str(exc.value)


@pytest.mark.parametrize("kind", ["tls", "dns", "timeout", "network"])
def test_transport_failures_remain_distinct_and_secret_free(kind):
    from plugins.rhythm.backend.client import RhythmRemoteError, RhythmClient

    def unavailable(*args):
        raise RhythmRemoteError(kind)

    with pytest.raises(RhythmRemoteError) as exc:
        RhythmClient(TOKEN, transport=unavailable, sleep=lambda _: None).call("GET", "/auth/me")
    assert exc.value.kind == kind
    assert TOKEN not in str(exc.value)


def test_schema_bounds_and_redaction(api, monkeypatch, caplog):
    client, mod = api
    huge = "x" * 5000
    def malformed(method, url, headers, body, timeout):
        return 200, {}, {"id": huge, "email": "not-an-email", "joinCode": JOIN_CODE}
    monkeypatch.setattr(mod, "request", malformed)
    response = client.put("/api/plugins/rhythm/connection", json={"access_token": TOKEN})
    assert response.status_code == 502
    assert TOKEN not in response.text and JOIN_CODE not in response.text
    assert TOKEN not in caplog.text and JOIN_CODE not in caplog.text


def test_read_only_dashboard_and_tasks_are_sanitized(api, monkeypatch):
    """The first live slice exposes canonical DTOs, never upstream objects."""
    client, mod = api

    def read_only_transport(method, url, headers, body, timeout):
        assert method == "GET"
        if url.endswith("/auth/me"):
            return 200, {}, {"id": "user-1", "email": "me@example.test", "joinCode": JOIN_CODE}
        if url.endswith("/workspaces/me"):
            return 200, {}, {"id": "ws-1", "name": "Personal", "enrollmentCode": JOIN_CODE}
        if url.endswith("/dashboard/summary"):
            return 200, {}, {
                "openTaskCount": 1,
                "threadCount": 0,
                "tasks": [{"id": "task-1", "title": "Review brief", "notes": "Private notes", "status": "open", "bucket": "today", "dueLabel": "Today", "joinCode": JOIN_CODE}],
                "project": None,
                "unreadThreads": [],
                "enrollment": JOIN_CODE,
            }
        if url.endswith("/tasks"):
            return 200, {}, {"tasks": [{"id": "task-1", "title": "Review brief", "notes": "Private notes", "status": "open", "bucket": "today", "priority": 1, "tags": ["work"], "createdAt": "2026-08-21", "createdBy": "Me", "ownerId": "user-1", "isShared": False, "sourceType": "manual", "preferredAgent": "", "energy": "", "collaborators": [], "joinCode": JOIN_CODE}]}
        if url.endswith("/tasks/task-1"):
            return 200, {}, {"id": "task-1", "title": "Review brief", "notes": "Private notes", "status": "open", "bucket": "today", "priority": 1, "tags": ["work"], "createdAt": "2026-08-21", "createdBy": "Me", "ownerId": "user-1", "isShared": False, "sourceType": "manual", "preferredAgent": "", "energy": "", "collaborators": [], "joinCode": JOIN_CODE}
        raise AssertionError(url)

    monkeypatch.setattr(mod, "request", read_only_transport)
    assert client.put("/api/plugins/rhythm/connection", json={"access_token": TOKEN}).status_code == 200
    summary = client.get("/api/plugins/rhythm/dashboard-summary")
    listing = client.get("/api/plugins/rhythm/tasks")
    detail = client.get("/api/plugins/rhythm/tasks/task-1")

    assert summary.status_code == listing.status_code == detail.status_code == 200
    assert summary.json()["identity"] == {"id": "user-1", "email": "me@example.test"}
    assert summary.json()["workspace"] == {"id": "ws-1", "name": "Personal"}
    assert listing.json()["tasks"][0]["id"] == detail.json()["id"] == "task-1"
    assert JOIN_CODE not in summary.text + listing.text + detail.text


@pytest.mark.parametrize(
    ("endpoint", "payload"),
    [
        ("/dashboard-summary", {"openTaskCount": True, "threadCount": 0, "tasks": [], "project": None, "unreadThreads": []}),
        ("/dashboard-summary", {"openTaskCount": 0, "threadCount": True, "tasks": [], "project": None, "unreadThreads": []}),
        ("/tasks", {"tasks": [{"id": "task-1", "title": "Review", "status": "open", "bucket": "today", "priority": True, "tags": [], "createdAt": "2026-08-21", "createdBy": "Me", "ownerId": "user-1"}]}),
    ],
)
def test_canonical_numeric_dtos_reject_booleans(api, monkeypatch, endpoint, payload):
    """Python bool is an int subclass; canonical DTO counts must not admit it."""
    client, mod = api

    def transport(method, url, headers, body, timeout):
        if url.endswith("/auth/me"):
            return 200, {}, {"id": "user-1"}
        if url.endswith("/workspaces/me"):
            return 200, {}, {"id": "ws-1"}
        if url.endswith("/dashboard/summary") and endpoint == "/dashboard-summary":
            return 200, {}, payload
        if url.endswith(endpoint):
            return 200, {}, payload
        raise AssertionError(url)

    monkeypatch.setattr(mod, "request", transport)
    assert client.put("/api/plugins/rhythm/connection", json={"access_token": TOKEN}).status_code == 200
    response = client.get(f"/api/plugins/rhythm{endpoint}")
    assert response.status_code == 502
    assert response.json() == {"detail": {"error": "schema_drift", "recoverable": True}}


def test_task_detail_rejects_unsafe_or_write_receipts():
    from plugins.rhythm.backend.client import RhythmProtocolError, RhythmClient

    client = RhythmClient(TOKEN, transport=_ok_transport)
    for method, path in (("POST", "/tasks"), ("PATCH", "/tasks/task-1"), ("GET", "/tasks/../../auth/me")):
        with pytest.raises(RhythmProtocolError, match="operation_not_allowed"):
            client.call(method, path)


def test_task_mutation_is_one_exact_patch_with_stable_idempotency_and_canonical_readback():
    from plugins.rhythm.backend.client import RhythmClient

    seen = []
    def transport(method, url, headers, body, timeout):
        seen.append((method, url, headers.copy(), body))
        if method == "PATCH":
            assert url.endswith("/tasks/task-1")
            return 200, {}, {"ignored": True}
        return 200, {}, {"id": "task-1", "status": "done"}

    client = RhythmClient(TOKEN, transport=transport)
    assert client.mutate_task("task-1", "complete") == {"id": "task-1", "status": "done"}
    assert [(method, body) for method, _, _, body in seen] == [("PATCH", b'{"status":"done"}'), ("GET", None)]
    key = seen[0][2]["Idempotency-Key"]
    assert TOKEN not in key
    # The key is deterministic for a particular semantic mutation, never a replay loop.
    keys = []
    RhythmClient(TOKEN, transport=lambda method, url, headers, body, timeout: (keys.append(headers.get("Idempotency-Key")) or (200, {}, {"id": "task-1", "status": "done"}))).mutate_task("task-1", "complete")
    assert keys[0] == key and len(keys) == 2


@pytest.mark.parametrize("failure", ["timeout", "network", "upstream_unavailable"])
def test_task_mutation_never_replays_ambiguous_patch_and_only_accepts_matching_readback(failure):
    from plugins.rhythm.backend.client import RhythmClient, RhythmRemoteError

    calls = []
    def transport(method, url, headers, body, timeout):
        calls.append(method)
        if method == "PATCH":
            raise RhythmRemoteError(failure)
        return 200, {}, {"id": "task-1", "status": "open"}

    with pytest.raises(RhythmRemoteError, match="uncertain"):
        RhythmClient(TOKEN, transport=transport).mutate_task("task-1", "complete")
    assert calls == ["PATCH", "GET"]


def test_task_mutation_marks_desired_readback_uncertain_after_ambiguous_patch():
    """An ambiguous PATCH is never success, even if a later GET looks desired."""
    from plugins.rhythm.backend.client import RhythmClient, RhythmRemoteError

    calls = []
    def transport(method, url, headers, body, timeout):
        calls.append(method)
        if method == "PATCH":
            raise RhythmRemoteError("timeout")
        return 200, {}, {"id": "task-1", "status": "done"}

    with pytest.raises(RhythmRemoteError, match="uncertain"):
        RhythmClient(TOKEN, transport=transport).mutate_task("task-1", "complete")
    assert calls == ["PATCH", "GET"]


def test_task_mutation_returns_conflict_for_successful_patch_with_stale_readback():
    """A canonical mismatch after HTTP success is conflict, never UnboundLocalError."""
    from plugins.rhythm.backend.client import RhythmClient, RhythmRemoteError

    def transport(method, url, headers, body, timeout):
        return (200, {}, {}) if method == "PATCH" else (200, {}, {"id": "task-1", "status": "open"})

    with pytest.raises(RhythmRemoteError, match="conflict") as exc:
        RhythmClient(TOKEN, transport=transport).mutate_task("task-1", "complete")
    assert exc.value.status_code == 409


def test_task_mutation_rejects_matching_state_for_a_different_canonical_task():
    from plugins.rhythm.backend.client import RhythmClient, RhythmRemoteError

    for operation, scheduled_date, canonical in (
        ("complete", None, {"id": "task-2", "status": "done"}),
        ("reschedule", "2026-02-28", {"id": "task-2", "scheduledDate": "2026-02-28"}),
    ):
        def transport(method, url, headers, body, timeout, canonical=canonical):
            return (200, {}, {}) if method == "PATCH" else (200, {}, canonical)

        with pytest.raises(RhythmRemoteError, match="conflict"):
            RhythmClient(TOKEN, transport=transport).mutate_task("task-1", operation, scheduled_date)


def test_task_mutation_409_is_not_misreported_as_success_or_replayed():
    from plugins.rhythm.backend.client import RhythmClient, RhythmRemoteError

    calls = []
    def transport(method, url, headers, body, timeout):
        calls.append(method)
        return (409, {}, {}) if method == "PATCH" else (200, {}, {"id": "task-1", "status": "done"})

    with pytest.raises(RhythmRemoteError, match="conflict"):
        RhythmClient(TOKEN, transport=transport).mutate_task("task-1", "complete")
    assert calls == ["PATCH"]


def test_task_mutation_rejects_unsafe_ids_dates_and_unallowlisted_bodies():
    from plugins.rhythm.backend.client import RhythmClient, RhythmProtocolError

    client = RhythmClient(TOKEN, transport=_ok_transport)
    for path, body in (("/tasks/../../auth/me", {"status": "done"}), ("/tasks/task-1", {"scheduledDate": "2026-02-30"}), ("/tasks/task-1", {"status": "open"}), ("/tasks/task-1", {"status": "done", "scheduledDate": "2026-02-28"})):
        with pytest.raises(RhythmProtocolError):
            client.call("PATCH", path, body=body)


def test_task_confirmation_is_owner_profile_payload_bound_one_time_and_never_transports_before_issue(api, monkeypatch, rhythm_home, tmp_path):
    client, mod = api
    calls = []
    task = {"id": "task-1", "title": "Review", "notes": "Read.", "status": "open", "bucket": "today", "priority": 1, "tags": [], "createdAt": "2026-08-21", "createdBy": "Me", "ownerId": "user-1", "isShared": False, "sourceType": "manual", "preferredAgent": "", "energy": "", "collaborators": []}
    def transport(method, url, headers, body, timeout):
        calls.append((method, url, body))
        if url.endswith("/auth/me"): return 200, {}, {"id": "user-1"}
        if url.endswith("/workspaces/me"): return 200, {}, {"id": "ws-1"}
        if url.endswith("/tasks/task-1") and method == "GET": return 200, {}, task
        if url.endswith("/tasks/task-1") and method == "PATCH":
            task["status"] = "done"
            return 200, {}, {}
        raise AssertionError((method, url))
    monkeypatch.setattr(mod, "request", transport)
    assert client.put("/api/plugins/rhythm/connection", json={"access_token": TOKEN}).status_code == 200
    payload = {"operation": "complete", "generation": "generation-123"}
    assert client.post("/api/plugins/rhythm/tasks/task-1/operations", json=payload).status_code == 409
    assert not any(method == "PATCH" for method, _, _ in calls)
    issued = client.post("/api/plugins/rhythm/tasks/task-1/confirmation", json=payload)
    assert issued.status_code == 200, issued.text
    token = issued.json()["confirmation"]
    assert TOKEN not in issued.text and TOKEN not in token
    changed = client.post("/api/plugins/rhythm/tasks/task-1/operations", json={**payload, "confirmation": token, "generation": "generation-456"})
    assert changed.status_code == 409
    assert not any(method == "PATCH" for method, _, _ in calls)
    duplicate = client.post("/api/plugins/rhythm/tasks/task-1/confirmation", json=payload)
    assert duplicate.status_code == 409
    success = client.post("/api/plugins/rhythm/tasks/task-1/operations", json={**payload, "confirmation": token})
    assert success.status_code == 200
    assert [method for method, _, _ in calls].count("PATCH") == 1
    assert client.post("/api/plugins/rhythm/tasks/task-1/operations", json={**payload, "confirmation": token}).status_code == 409
    other = tmp_path / "other-profile"; other.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(other))
    rehomed = client.post("/api/plugins/rhythm/tasks/task-1/confirmation", json=payload)
    assert rehomed.status_code == 401


def test_task_confirmation_rejects_nonowner_invalid_date_expiry_and_bounds(api, monkeypatch):
    client, mod = api
    task = {"id": "task-1", "title": "Review", "notes": "Read.", "status": "open", "bucket": "today", "priority": 1, "tags": [], "createdAt": "2026-08-21", "createdBy": "Other", "ownerId": "other-user", "isShared": True, "sourceType": "manual", "preferredAgent": "", "energy": "", "collaborators": []}
    def transport(method, url, headers, body, timeout):
        if url.endswith("/auth/me"): return 200, {}, {"id": "user-1"}
        if url.endswith("/workspaces/me"): return 200, {}, {"id": "ws-1"}
        if url.endswith("/tasks/task-1"): return 200, {}, task
        raise AssertionError(url)
    monkeypatch.setattr(mod, "request", transport)
    assert client.put("/api/plugins/rhythm/connection", json={"access_token": TOKEN}).status_code == 200
    denied = client.post("/api/plugins/rhythm/tasks/task-1/confirmation", json={"operation": "complete", "generation": "generation-123"})
    assert denied.status_code == 403, denied.text
    assert client.post("/api/plugins/rhythm/tasks/task-1/confirmation", json={"operation": "reschedule", "generation": "generation-123", "scheduledDate": "2026-02-30"}).status_code == 422
    # Expiry pruning and bounded pending state are lock-protected, matching OAuth state handling.
    mod._task_confirmations["expired"] = mod._TaskConfirmation("task-1", "complete", None, "generation-123", mod._canonical_home(), "user-1", "ws-1", "digest", time.monotonic() - 1)
    mod._prune_task_confirmations_locked()
    assert "expired" not in mod._task_confirmations


def test_task_confirmation_pending_cap_preserves_its_exact_429(api, monkeypatch):
    client, mod = api
    task = {"id": "task-1", "title": "Review", "notes": "Read.", "status": "open", "bucket": "today", "priority": 1, "tags": [], "createdAt": "2026-08-21", "createdBy": "Me", "ownerId": "user-1", "isShared": False, "sourceType": "manual", "preferredAgent": "", "energy": "", "collaborators": []}
    def transport(method, url, headers, body, timeout):
        if url.endswith("/auth/me"): return 200, {}, {"id": "user-1"}
        if url.endswith("/workspaces/me"): return 200, {}, {"id": "ws-1"}
        if url.endswith("/tasks/task-1"): return 200, {}, task
        raise AssertionError(url)
    monkeypatch.setattr(mod, "request", transport)
    assert client.put("/api/plugins/rhythm/connection", json={"access_token": TOKEN}).status_code == 200
    for index in range(mod.MAX_PENDING_TASK_CONFIRMATIONS):
        response = client.post("/api/plugins/rhythm/tasks/task-1/confirmation", json={"operation": "complete", "generation": f"generation-{index:03d}"})
        assert response.status_code == 200, response.text
    capped = client.post("/api/plugins/rhythm/tasks/task-1/confirmation", json={"operation": "complete", "generation": "generation-overflow"})
    assert capped.status_code == 429
    assert capped.json()["detail"]["error"] == "confirmation_pending_limit"


def test_task_confirmation_collaborator_identity_revalidation_and_duplicate_request_barrier(api, monkeypatch):
    client, mod = api
    patch_started = threading.Event()
    release_patch = threading.Event()
    patch_calls: list[str] = []
    current = {"identity": "user-1", "workspace": "ws-1"}
    task = {"id": "task-1", "title": "Review", "notes": "Read.", "status": "open", "bucket": "today", "priority": 1, "tags": [], "createdAt": "2026-08-21", "createdBy": "Other", "ownerId": "other-user", "isShared": True, "sourceType": "manual", "preferredAgent": "", "energy": "", "collaborators": [{"id": "user-1", "name": "Canonical collaborator", "initials": "CC"}]}
    def transport(method, url, headers, body, timeout):
        if url.endswith("/auth/me"): return 200, {}, {"id": current["identity"]}
        if url.endswith("/workspaces/me"): return 200, {}, {"id": current["workspace"]}
        if url.endswith("/tasks/task-1") and method == "GET": return 200, {}, task
        if url.endswith("/tasks/task-1") and method == "PATCH":
            patch_calls.append("PATCH")
            patch_started.set()
            assert release_patch.wait(2)
            task["status"] = "done"
            return 200, {}, {}
        raise AssertionError((method, url))
    monkeypatch.setattr(mod, "request", transport)
    assert client.put("/api/plugins/rhythm/connection", json={"access_token": TOKEN}).status_code == 200
    payload = {"operation": "complete", "generation": "generation-123"}
    issued = client.post("/api/plugins/rhythm/tasks/task-1/confirmation", json=payload)
    assert issued.status_code == 200
    token = issued.json()["confirmation"]
    # A second confirmation for the same exact intent is rejected before it can
    # create another receipt.  The injected historical duplicate below exercises
    # the operation-side lease as well.
    assert client.post("/api/plugins/rhythm/tasks/task-1/confirmation", json=payload).status_code == 409
    with mod._oauth_lock:
        mod._task_confirmations["duplicate-confirmation-token-000000000"] = mod._task_confirmations[token]
    responses: list[int] = []
    def invoke(receipt: str):
        responses.append(client.post("/api/plugins/rhythm/tasks/task-1/operations", json={**payload, "confirmation": receipt}).status_code)
    first = threading.Thread(target=invoke, args=(token,))
    first.start()
    assert patch_started.wait(2)
    second = threading.Thread(target=invoke, args=("duplicate-confirmation-token-000000000",))
    second.start()
    second.join(2)
    release_patch.set()
    first.join(2)
    assert sorted(responses) == [200, 409]
    assert patch_calls == ["PATCH"]

    fresh = client.post("/api/plugins/rhythm/tasks/task-1/confirmation", json={**payload, "generation": "generation-456"})
    assert fresh.status_code == 200
    current["workspace"] = "ws-2"
    rejected = client.post("/api/plugins/rhythm/tasks/task-1/operations", json={**payload, "generation": "generation-456", "confirmation": fresh.json()["confirmation"]})
    assert rejected.status_code == 409
    assert patch_calls == ["PATCH"]


@pytest.mark.parametrize(
    ("method", "path"),
    [("post", "/dashboard-summary"), ("patch", "/tasks/task-1"), ("delete", "/tasks/task-1")],
)
def test_dashboard_and_task_writes_are_unreachable(api, method, path):
    client, _ = api
    assert getattr(client, method)(f"/api/plugins/rhythm{path}").status_code == 405


@pytest.mark.parametrize(
    ("path", "payload", "secret"),
    [
        ("/api/plugins/rhythm/connection", {"access_token": "t" * 2049}, "t" * 2049),
        ("/api/plugins/rhythm/oauth/callback", {"state": "s" * 16, "code": "c" * 2049}, "c" * 2049),
    ],
)
def test_validation_errors_are_generic_and_do_not_echo_secrets(api, path, payload, secret, caplog):
    client, _ = api
    response = client.post(path, json=payload) if path.endswith("callback") else client.put(path, json=payload)
    assert response.status_code == 422
    assert response.json() == {"detail": {"error": "invalid_request", "recoverable": True}}
    assert secret not in response.text
    assert secret not in caplog.text


def test_httpx_streaming_rejects_oversized_body_without_reading_tail(monkeypatch):
    import httpx
    from plugins.rhythm.backend.client import MAX_RESPONSE_BYTES, RhythmProtocolError, _httpx_transport

    class TailPreservingStream(httpx.SyncByteStream):
        def __init__(self):
            self.yielded = []

        def __iter__(self):
            for index, chunk in enumerate((b"x" * MAX_RESPONSE_BYTES, b"x", b"unread-tail")):
                self.yielded.append(index)
                yield chunk

    stream = TailPreservingStream()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=stream))
    real_client = httpx.Client

    def mock_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", mock_client)
    with pytest.raises(RhythmProtocolError, match="response_too_large"):
        _httpx_transport("GET", "https://api.rhythm.app/auth/me", {}, None, 1.0)
    assert stream.yielded == [0, 1]


def test_httpx_streaming_rejects_oversized_content_length_before_reading_body(monkeypatch):
    import httpx
    from plugins.rhythm.backend.client import MAX_RESPONSE_BYTES, RhythmProtocolError, _httpx_transport

    class UnreadStream(httpx.SyncByteStream):
        def __iter__(self):
            raise AssertionError("response body must not be consumed")

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-length": str(MAX_RESPONSE_BYTES + 1)},
            stream=UnreadStream(),
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda *args, **kwargs: real_client(*args, transport=transport, **kwargs),
    )
    with pytest.raises(RhythmProtocolError, match="response_too_large"):
        _httpx_transport("GET", "https://api.rhythm.app/auth/me", {}, None, 1.0)


def test_httpx_streaming_enforces_decoded_size_bound(monkeypatch):
    import httpx
    from plugins.rhythm.backend.client import MAX_RESPONSE_BYTES, RhythmProtocolError, _httpx_transport

    compressed = gzip.compress(b"x" * (MAX_RESPONSE_BYTES + 1))
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-encoding": "gzip"},
            stream=httpx.ByteStream(compressed),
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda *args, **kwargs: real_client(*args, transport=transport, **kwargs),
    )
    with pytest.raises(RhythmProtocolError, match="response_too_large"):
        _httpx_transport("GET", "https://api.rhythm.app/auth/me", {}, None, 1.0)


def test_pkce_expiry_replay_and_concurrent_exchange(api, monkeypatch):
    client, mod = api
    monkeypatch.setattr(mod, "request", _ok_transport)
    first = client.post("/api/plugins/rhythm/oauth/start").json()
    assert "code_challenge=" in first["authorization_url"]
    assert first["authorization_url"].startswith("https://accounts.google.com/")
    assert TOKEN not in first["authorization_url"]
    state = first["state"]
    response = client.post("/api/plugins/rhythm/oauth/callback", json={"state": state, "code": "code-1"})
    assert response.status_code == 200
    assert client.post("/api/plugins/rhythm/oauth/callback", json={"state": state, "code": "code-1"}).status_code == 409

    expired = client.post("/api/plugins/rhythm/oauth/start").json()["state"]
    mod._oauth_states[expired].expires_at = time.monotonic() - 1
    assert client.post("/api/plugins/rhythm/oauth/callback", json={"state": expired, "code": "code-2"}).status_code == 410

    state = client.post("/api/plugins/rhythm/oauth/start").json()["state"]
    results = []
    def exchange():
        results.append(client.post("/api/plugins/rhythm/oauth/callback", json={"state": state, "code": "code-3"}).status_code)
    threads = [threading.Thread(target=exchange) for _ in range(2)]
    [thread.start() for thread in threads]
    [thread.join() for thread in threads]
    assert sorted(results) == [200, 409]


def test_pkce_wire_contract_and_get_handoff(api, monkeypatch):
    client, mod = api
    seen = []

    def transport(method, url, headers, body, timeout):
        if url == "https://oauth2.googleapis.com/token":
            seen.append(json.loads(body))
        return _ok_transport(method, url, headers, body, timeout)

    monkeypatch.setattr(mod, "request", transport)
    start = client.post("/api/plugins/rhythm/oauth/start").json()
    query = dict(parse_qsl(start["authorization_url"].split("?", 1)[1]))
    assert query["client_id"] == mod.OAUTH_CLIENT_ID
    assert query["redirect_uri"] == "http://127.0.0.1:49123/api/plugins/rhythm/oauth/callback"
    response = client.get(
        "/api/plugins/rhythm/oauth/callback",
        params={"state": start["state"], "code": "handoff-code"},
    )
    assert response.status_code == 200
    assert "handoff-code" not in response.text and TOKEN not in response.text
    assert seen == [
        {
            "grant_type": "authorization_code",
            "code": "handoff-code",
            "code_verifier": ANY,
            "client_id": mod.OAUTH_CLIENT_ID,
            "redirect_uri": "http://127.0.0.1:49123/api/plugins/rhythm/oauth/callback",
        }
    ]


def test_pkce_binds_callback_to_starting_home_and_prunes_states(api, monkeypatch, rhythm_home, tmp_path):
    client, mod = api
    monkeypatch.setattr(mod, "request", _ok_transport)
    first = client.post("/api/plugins/rhythm/oauth/start").json()["state"]
    other = tmp_path / ".hermes" / "profiles" / "other"
    other.mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(other))
    assert client.get(
        "/api/plugins/rhythm/oauth/callback", params={"state": first, "code": "code"}
    ).status_code == 409
    assert not (other / "auth.json").exists()
    assert not (rhythm_home / "auth.json").exists()

    monkeypatch.setenv("HERMES_HOME", str(rhythm_home))
    states = [
        client.post("/api/plugins/rhythm/oauth/start").json()["state"]
        for _ in range(mod.MAX_PENDING_OAUTH_STATES - 1)
    ]
    assert client.post("/api/plugins/rhythm/oauth/start").status_code == 429
    mod._oauth_states[states[0]].expires_at = time.monotonic() - 1
    assert client.post("/api/plugins/rhythm/oauth/start").status_code == 200
    assert states[0] not in mod._oauth_states


def test_pkce_concurrent_profiles_persist_only_to_their_bound_homes(api, monkeypatch, tmp_path):
    _, mod = api
    monkeypatch.setattr(mod, "request", _ok_transport)
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override

    homes = [tmp_path / ".hermes" / "profiles" / name for name in ("one", "two")]
    for home in homes:
        home.mkdir(parents=True)
    outcomes = []

    def complete(home):
        token = set_hermes_home_override(home)
        try:
            request = _loopback_request()
            state = mod.oauth_start(request)["state"]
            outcomes.append(mod._complete_oauth_callback(state, "code", request))
        finally:
            reset_hermes_home_override(token)

    threads = [threading.Thread(target=complete, args=(home,)) for home in homes]
    [thread.start() for thread in threads]
    [thread.join() for thread in threads]
    assert outcomes == [
        {
            "connected": True,
            "identity": {"id": "user-1", "email": "me@example.test"},
            "workspace": {"id": "ws-1", "name": "Personal"},
        }
    ] * 2
    for home in homes:
        assert TOKEN in (home / "auth.json").read_text()


def test_pkce_pending_states_do_not_survive_router_restart(api, monkeypatch):
    client, mod = api
    monkeypatch.setattr(mod, "request", _ok_transport)
    state = client.post("/api/plugins/rhythm/oauth/start").json()["state"]
    reloaded = _router_module()
    app = FastAPI()
    app.include_router(reloaded.router, prefix="/api/plugins/rhythm")
    response = TestClient(app).get(
        "/api/plugins/rhythm/oauth/callback", params={"state": state, "code": "code"}
    )
    assert response.status_code == 409


def test_dashboard_manifest_discovers_mounts_api_and_serves_its_local_asset(rhythm_home):
    from hermes_cli import web_server

    plugins = web_server._get_dashboard_plugins(force_rescan=True)
    rhythm = next(plugin for plugin in plugins if plugin["name"] == "rhythm")
    assert rhythm["entry"] == "dist/index.js"
    assert rhythm["has_api"] is True
    assert rhythm["tab"]["hidden"] is True

    client = TestClient(web_server.app)
    asset = client.get("/dashboard-plugins/rhythm/dist/index.js")
    assert asset.status_code == 200
    assert "RhythmApiOnlyPlugin" in asset.text
    api = client.get(
        "/api/plugins/rhythm/health",
        headers={web_server._SESSION_HEADER_NAME: web_server._SESSION_TOKEN},
    )
    assert api.status_code == 200
    assert api.json() == {"status": "disconnected"}
