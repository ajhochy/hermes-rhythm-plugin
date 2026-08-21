"""M5 is a bounded local/upstream contract, never a proxy."""
from __future__ import annotations

import importlib
import json
import sys
import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plugins.rhythm.contracts.validate import load_contract


TOKEN = "rhythm-m5-token-" + "x" * 24


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes" / "profiles" / "m5"))
    sys.modules.pop("plugins.rhythm.dashboard.plugin_api", None)
    mod = importlib.import_module("plugins.rhythm.dashboard.plugin_api")
    app = FastAPI()
    app.include_router(mod.router, prefix="/api/plugins/rhythm")
    return TestClient(app), mod


def _connect(client, mod, transport):
    mod.request = transport
    response = client.put("/api/plugins/rhythm/connection", json={"access_token": TOKEN})
    assert response.status_code == 200, response.text


def _transport(calls, *, mutation_result=None, identity="user-1", workspace="ws-1"):
    reads = {
        "/planner/weeks/2026-08-17": {"weekLabel": "Aug 17 – Aug 23", "weekStart": "2026-08-17", "days": [], "backlog": []},
        "/recurring-rules": {"items": []},
        "/project-templates": {"items": []},
        "/project-instances": {"items": []},
    }
    def transport(method, url, headers, body, timeout):
        path = url.removeprefix("https://api.rhythm.app")
        calls.append((method, path, json.loads(body) if body else None, headers))
        if path == "/auth/me": return 200, {}, {"id": identity}
        if path == "/workspaces/me": return 200, {}, {"id": workspace}
        if method == "GET" and path in reads: return 200, {}, reads[path]
        if method in {"POST", "PATCH", "DELETE"}: return 200, {}, mutation_result if mutation_result is not None else {"id": path.rsplit("/", 1)[-1]}
        raise AssertionError((method, path))
    return transport


def test_m5_has_exact_read_registry_and_no_broad_write():
    m5 = load_contract("api-operations")["milestones"]["M5"]
    assert m5["transport"] == "bounded_local_rest_to_pinned_upstream_v1"
    assert m5["fail_closed"] is True
    assert "arbitrary_proxying" not in m5["approved_write_operations"]
    assert {row["path"] for row in m5["allowed_operations"]} >= {"/planner/weeks/{week_start}", "/rhythm-rules", "/project-templates", "/project-instances"}


def test_live_client_has_only_pinned_m5_paths_and_never_collaborator_routes():
    from plugins.rhythm.backend.client import ALLOWED_OPERATIONS
    assert ("GET", "/planner/weeks") in ALLOWED_OPERATIONS
    assert not any("collaborator" in path or "member" in path for _, path in ALLOWED_OPERATIONS)


def test_m5_operation_registry_exactly_matches_the_contract_union():
    mod = importlib.import_module("plugins.rhythm.dashboard.plugin_api")
    approved = set(load_contract("api-operations")["milestones"]["M5"]["approved_write_operations"])
    assert set(mod._M5_UPSTREAM) == approved
    assert all(method in {"POST", "PATCH", "DELETE"} and path.startswith("/") for method, path in mod._M5_UPSTREAM.values())


def test_m5_client_allows_the_pinned_planner_update_body_without_widening_m4():
    from plugins.rhythm.backend.client import RhythmClient
    seen = []
    def transport(method, url, headers, body, timeout):
        seen.append((method, url, json.loads(body)))
        return 200, {}, {"id": "task-1"}
    assert RhythmClient(TOKEN, transport=transport).call("PATCH", "/tasks/task-1", body={"notes": "Only the approved M5 body"}, m5=True) == {"id": "task-1"}
    assert seen == [("PATCH", "https://api.rhythm.app/tasks/task-1", {"notes": "Only the approved M5 body"})]


@pytest.mark.parametrize("path", ["/planner/weeks/2026-08-17", "/rhythm-rules", "/project-templates", "/project-instances"])
def test_m5_mounted_reads_use_only_canonical_pinned_gets(api, path):
    client, mod = api
    calls = []
    _connect(client, mod, _transport(calls))
    response = client.get(f"/api/plugins/rhythm{path}")
    assert response.status_code == 200, response.text
    assert all(method == "GET" for method, _, _, _ in calls[2:])
    assert all("member" not in upstream and "collaborator" not in upstream for _, upstream, _, _ in calls)


def test_m5_mounted_reads_strip_credential_shaped_fields_and_bound_values(api):
    client, mod = api
    calls = []
    transport = _transport(calls)
    original = transport
    def secret_read(method, url, headers, body, timeout):
        if url.endswith("/recurring-rules"):
            calls.append((method, "/recurring-rules", None, headers))
            return 200, {}, {"items": [], "accessToken": TOKEN, "authorization": "Bearer leaked"}
        return original(method, url, headers, body, timeout)
    _connect(client, mod, secret_read)
    response = client.get("/api/plugins/rhythm/rhythm-rules")
    assert response.status_code == 200
    assert TOKEN not in response.text
    assert "authorization" not in response.json()


@pytest.mark.parametrize("path", ["/planner/weeks/not-a-date", "/planner/weeks/2026-08-18", "/rhythm-rules/../../auth/me", "/project-instances/unsafe%2Fid"])
def test_m5_mounted_reads_reject_unsafe_ids_and_dates(api, path):
    client, mod = api
    calls = []
    _connect(client, mod, _transport(calls))
    response = client.get(f"/api/plugins/rhythm{path}")
    assert response.status_code in {404, 405, 422}
    assert all(method == "GET" for method, _, _, _ in calls)


def test_m5_operation_requires_bound_confirmation_and_exact_payload(api):
    client, mod = api
    calls = []
    _connect(client, mod, _transport(calls))
    payload = {"operation": "rhythms.update-rule", "entityId": "rule-1", "payload": {"enabled": False}, "generation": "generation-1"}
    assert client.post("/api/plugins/rhythm/workspace-operations", json=payload).status_code == 409
    assert not any(method != "GET" for method, _, _, _ in calls)
    receipt = client.post("/api/plugins/rhythm/workspace-operations/confirmation", json=payload)
    assert receipt.status_code == 200, receipt.text
    token = receipt.json()["confirmation"]
    changed = client.post("/api/plugins/rhythm/workspace-operations", json={**payload, "confirmation": token})
    assert changed.status_code == 200, changed.text
    mutation = [row for row in calls if row[0] == "PATCH"]
    assert [(method, path, body) for method, path, body, _ in mutation] == [("PATCH", "/recurring-rules/rule-1", {"enabled": False})]
    assert client.post("/api/plugins/rhythm/workspace-operations", json={**payload, "confirmation": token}).status_code == 409


@pytest.mark.parametrize("extra", [{"actorId": "user-2"}, {"workspaceId": "ws-2"}, {"url": "https://attacker.test"}])
def test_m5_confirmation_forbids_extra_or_arbitrary_fields(api, extra):
    client, mod = api
    calls = []
    _connect(client, mod, _transport(calls))
    payload = {"operation": "rhythms.update-rule", "entityId": "rule-1", "payload": {"enabled": False, **extra}, "generation": "generation-1"}
    response = client.post("/api/plugins/rhythm/workspace-operations/confirmation", json=payload)
    assert response.status_code == 422
    assert not any(method != "GET" for method, _, _, _ in calls)


def test_m5_receipt_binds_actor_workspace_profile_generation_and_payload(api, tmp_path, monkeypatch):
    client, mod = api
    calls = []
    current = {"identity": "user-1", "workspace": "ws-1"}
    _connect(client, mod, _transport(calls, identity=current["identity"], workspace=current["workspace"]))
    payload = {"operation": "rhythms.update-rule", "entityId": "rule-1", "payload": {"enabled": False}, "generation": "generation-1"}
    token = client.post("/api/plugins/rhythm/workspace-operations/confirmation", json=payload).json()["confirmation"]
    assert client.post("/api/plugins/rhythm/workspace-operations", json={**payload, "generation": "generation-2", "confirmation": token}).status_code == 409
    assert client.post("/api/plugins/rhythm/workspace-operations", json={**payload, "payload": {"enabled": True}, "confirmation": token}).status_code == 409
    other = tmp_path / "other"; other.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(other))
    assert client.post("/api/plugins/rhythm/workspace-operations", json={**payload, "confirmation": token}).status_code == 409


def test_m5_expiry_concurrency_and_canonical_identity_are_fail_closed(api):
    client, mod = api
    calls = []
    _connect(client, mod, _transport(calls, mutation_result={"id": "wrong-id"}))
    payload = {"operation": "rhythms.update-rule", "entityId": "rule-1", "payload": {"enabled": False}, "generation": "generation-1"}
    token = client.post("/api/plugins/rhythm/workspace-operations/confirmation", json=payload).json()["confirmation"]
    assert client.post("/api/plugins/rhythm/workspace-operations", json={**payload, "confirmation": token}).status_code == 502
    # A claimed receipt stays consumed even when its canonical response is wrong.
    assert client.post("/api/plugins/rhythm/workspace-operations", json={**payload, "confirmation": token}).status_code == 409
    mod._workspace_confirmations["expired"] = mod._TaskConfirmation("rule-1", "rhythms.update-rule", None, "generation-2", mod._canonical_home(), "user-1", "ws-1", "digest", time.monotonic() - 1)
    mod._prune_task_confirmations_locked()
    assert "expired" not in mod._workspace_confirmations


@pytest.mark.parametrize("outcome,status", [("conflict", 409), ("timeout", 409)])
def test_m5_mutation_conflict_and_ambiguous_timeout_never_report_success(api, outcome, status):
    client, mod = api
    calls = []
    base = _transport(calls)
    def transport(method, url, headers, body, timeout):
        if url.endswith("/recurring-rules/rule-1") and method == "PATCH":
            if outcome == "timeout":
                from plugins.rhythm.backend.client import RhythmRemoteError
                raise RhythmRemoteError("timeout")
            return 409, {}, {}
        if url.endswith("/recurring-rules/rule-1") and method == "GET":
            calls.append((method, "/recurring-rules/rule-1", None, headers))
            return 200, {}, {"id": "rule-1", "enabled": False}
        return base(method, url, headers, body, timeout)
    _connect(client, mod, transport)
    payload = {"operation": "rhythms.update-rule", "entityId": "rule-1", "payload": {"enabled": False}, "generation": "generation-1"}
    token = client.post("/api/plugins/rhythm/workspace-operations/confirmation", json=payload).json()["confirmation"]
    response = client.post("/api/plugins/rhythm/workspace-operations", json={**payload, "confirmation": token})
    assert response.status_code == status
    assert response.json()["detail"]["error"] == ("uncertain" if outcome == "timeout" else "conflict")
    assert client.post("/api/plugins/rhythm/workspace-operations", json={**payload, "confirmation": token}).status_code == 409


def test_m5_duplicate_receipts_allow_exactly_one_mutation(api):
    client, mod = api
    calls = []
    patch_started = threading.Event()
    release = threading.Event()
    base = _transport(calls)
    def transport(method, url, headers, body, timeout):
        if url.endswith("/recurring-rules/rule-1") and method == "PATCH":
            patch_started.set(); assert release.wait(2)
            calls.append((method, "/recurring-rules/rule-1", json.loads(body), headers))
            return 200, {}, {"id": "rule-1", "enabled": False}
        return base(method, url, headers, body, timeout)
    _connect(client, mod, transport)
    payload = {"operation": "rhythms.update-rule", "entityId": "rule-1", "payload": {"enabled": False}, "generation": "generation-1"}
    token = client.post("/api/plugins/rhythm/workspace-operations/confirmation", json=payload).json()["confirmation"]
    duplicate = "duplicate-receipt-token-000000000000000"
    with mod._oauth_lock:
        mod._workspace_confirmations[duplicate] = mod._workspace_confirmations[token]
    responses = []
    def invoke(receipt):
        responses.append(client.post("/api/plugins/rhythm/workspace-operations", json={**payload, "confirmation": receipt}).status_code)
    first = threading.Thread(target=invoke, args=(token,)); first.start(); assert patch_started.wait(2)
    second = threading.Thread(target=invoke, args=(duplicate,)); second.start(); second.join(2)
    release.set(); first.join(2)
    assert sorted(responses) == [200, 409]
    assert len([row for row in calls if row[0] == "PATCH"]) == 1
