"""M5 is a bounded local/upstream contract, never a proxy."""
from __future__ import annotations

import importlib
import json
import sys
import threading
import time
from pathlib import Path

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
        path = url.removeprefix("https://api.vcrcapps.com")
        calls.append((method, path, json.loads(body) if body else None, headers))
        if path == "/auth/me": return 200, {}, {"id": identity}
        if path == "/workspaces/me": return 200, {}, {"id": workspace, "role": "owner"}
        if method == "GET" and path.startswith("/recurring-rules/"):
            return 200, {}, {"id": path.rsplit("/", 1)[-1], "ownerId": identity, "workspaceId": workspace, "enabled": False}
        if method == "GET" and path.startswith("/project-templates/"):
            return 200, {}, {"id": path.rsplit("/", 1)[-1], "ownerId": identity, "workspaceId": workspace}
        if method == "GET" and path.startswith("/project-instances/"):
            return 200, {}, {"id": path.rsplit("/", 1)[-1], "ownerId": identity, "workspaceId": workspace}
        if method == "GET" and path.startswith("/tasks/"):
            return 200, {}, {"id": path.rsplit("/", 1)[-1], "ownerId": identity, "workspaceId": workspace, "status": "open"}
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
    milestones = load_contract("api-operations")["milestones"]
    approved = set(milestones["M5"]["approved_write_operations"]) | set(milestones["M6"]["approved_write_operations"])
    assert set(mod._M5_UPSTREAM) == approved
    assert all(method in {"POST", "PATCH", "DELETE"} and path.startswith("/") for method, path in mod._M5_UPSTREAM.values())


def test_m5_client_allows_the_pinned_planner_update_body_without_widening_m4():
    from plugins.rhythm.backend.client import RhythmClient
    seen = []
    def transport(method, url, headers, body, timeout):
        seen.append((method, url, json.loads(body)))
        return 200, {}, {"id": "task-1"}
    assert RhythmClient(TOKEN, transport=transport).call("PATCH", "/tasks/task-1", body={"notes": "Only the approved M5 body"}, m5=True) == {"id": "task-1"}
    assert seen == [("PATCH", "https://api.vcrcapps.com/tasks/task-1", {"notes": "Only the approved M5 body"})]


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
                return 200, {}, {"id": "rule-1", "enabled": False, "ownerId": "user-1", "workspaceId": "ws-1"}
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


@pytest.mark.parametrize("route,payload", [
    ("/planner/weeks/2026-08-17", {"weekStart": "2026-08-17", "weekLabel": "Week", "accessToken": TOKEN,
                                      "days": [{"date": "2026-08-17", "tasks": [{"id": "task-1", "title": "Safe", "nested": {"refreshToken": TOKEN}}]}],
                                      "backlog": [{"id": "task-2", "title": "Safe", "credential": TOKEN}]}),
    ("/rhythm-rules", {"items": [{"id": "rule-1", "title": "Rule", "apiKey": TOKEN, "steps": [{"id": "step-1", "title": "Step", "token": TOKEN}]}]}),
    ("/project-templates", {"items": [{"id": "template-1", "name": "Template", "refreshToken": TOKEN, "steps": [{"id": "step-1", "title": "Step", "credential": TOKEN}]}]}),
    ("/project-instances", {"items": [{"id": "instance-1", "name": "Instance", "token": TOKEN, "milestones": [{"id": "milestone-1", "title": "M", "apiKey": TOKEN}], "steps": [{"id": "step-1", "title": "Step", "nested": {"credential": TOKEN}}]}]}),
])
def test_m5_reads_use_strict_canonical_projections_at_every_nesting_level(api, route, payload):
    """Catches a recursive reflector leaking a newly-shaped secret field."""
    client, mod = api
    calls = []
    base = _transport(calls)
    def transport(method, url, headers, body, timeout):
        if method == "GET" and url.endswith(route):
            calls.append((method, route, None, headers))
            return 200, {}, payload
        return base(method, url, headers, body, timeout)
    _connect(client, mod, transport)
    response = client.get(f"/api/plugins/rhythm{route}")
    assert response.status_code == 200, response.text
    rendered = response.text.lower()
    for forbidden in (TOKEN.lower(), "accesstoken", "refreshtoken", "apikey", "credential", '"nested"'):
        assert forbidden not in rendered


@pytest.mark.parametrize("operation,entity,payload", [
    ("rhythms.update-rule", "rule-1", {"enabled": False, "unexpected": "no"}),
    ("projects.update-step", "step-1", {"templateId": "template-1", "title": 12}),
    ("planner.schedule-task", "task-1", {}),
    ("rhythms.create-rule", "new-rule", {"title": "Rule", "frequency": "hourly"}),
])
def test_m5_operation_payloads_are_discriminated_exact_and_normalized(api, operation, entity, payload):
    """Catches an envelope validator accepting values outside the named operation schema."""
    client, mod = api
    calls = []
    _connect(client, mod, _transport(calls))
    response = client.post("/api/plugins/rhythm/workspace-operations/confirmation", json={"operation": operation, "entityId": entity, "payload": payload, "generation": "generation-1"})
    assert response.status_code == 422
    assert not any(method in {"POST", "PATCH", "DELETE"} for method, _, _, _ in calls)


def test_m5_delete_emits_supplied_idempotency_key_without_a_delete_body():
    """Catches a DELETE dropping its deterministic intent header because it has no JSON body."""
    from plugins.rhythm.backend.client import RhythmClient
    seen = []
    def transport(method, url, headers, body, timeout):
        seen.append((method, headers, body))
        return 200, {}, {}
    RhythmClient(TOKEN, transport=transport).call("DELETE", "/recurring-rules/rule-1", idempotency_key="intent-key", m5=True)
    assert len(seen) == 1
    assert seen[0][0] == "DELETE" and seen[0][2] is None
    assert seen[0][1]["Idempotency-Key"] == "intent-key"
    assert "Content-Type" not in seen[0][1]


def test_m5_mutation_response_is_canonical_readback_not_raw_mutation(api):
    """Catches returning a secret-bearing PATCH response instead of the canonical DTO."""
    client, mod = api
    calls = []
    def transport(method, url, headers, body, timeout):
        path = url.removeprefix("https://api.vcrcapps.com")
        calls.append((method, path, json.loads(body) if body else None, headers))
        if path == "/auth/me": return 200, {}, {"id": "user-1"}
        if path == "/workspaces/me": return 200, {}, {"id": "ws-1", "role": "owner"}
        if path == "/recurring-rules/rule-1" and method == "GET": return 200, {}, {"id": "rule-1", "title": "Canonical", "enabled": False, "ownerId": "user-1", "workspaceId": "ws-1", "token": TOKEN}
        if path == "/recurring-rules/rule-1" and method == "PATCH": return 200, {}, {"id": "rule-1", "token": TOKEN, "raw": "untrusted"}
        if path == "/recurring-rules": return 200, {}, {"items": []}
        raise AssertionError((method, path))
    _connect(client, mod, transport)
    request = {"operation": "rhythms.update-rule", "entityId": "rule-1", "payload": {"enabled": False}, "generation": "generation-1"}
    token = client.post("/api/plugins/rhythm/workspace-operations/confirmation", json=request).json()["confirmation"]
    response = client.post("/api/plugins/rhythm/workspace-operations", json={**request, "confirmation": token})
    assert response.status_code == 200, response.text
    assert response.json()["id"] == "rule-1"
    assert response.json()["title"] == "Canonical"
    assert response.json()["enabled"] is False
    assert set(response.json()) >= {"frequency", "ownerId", "ownerName", "collaborators", "steps", "createdAt"}
    assert [row[:2] for row in calls].count(("GET", "/recurring-rules/rule-1")) >= 2


def test_m5_reauthorizes_canonical_target_after_confirmation_before_mutation(api):
    """Catches an owner change between confirmation and PATCH being trusted from renderer/cache state."""
    client, mod = api
    calls = []
    phase = {"changed": False}
    def transport(method, url, headers, body, timeout):
        path = url.removeprefix("https://api.vcrcapps.com")
        calls.append((method, path, json.loads(body) if body else None, headers))
        if path == "/auth/me": return 200, {}, {"id": "user-1"}
        if path == "/workspaces/me": return 200, {}, {"id": "ws-1", "role": "owner"}
        if path == "/recurring-rules/rule-1" and method == "GET":
            return 200, {}, {"id": "rule-1", "ownerId": "user-2" if phase["changed"] else "user-1", "workspaceId": "ws-1", "enabled": False}
        if method == "PATCH": raise AssertionError("must not mutate a re-homed owner")
        raise AssertionError((method, path))
    _connect(client, mod, transport)
    request = {"operation": "rhythms.update-rule", "entityId": "rule-1", "payload": {"enabled": False}, "generation": "generation-1"}
    token = client.post("/api/plugins/rhythm/workspace-operations/confirmation", json=request).json()["confirmation"]
    phase["changed"] = True
    response = client.post("/api/plugins/rhythm/workspace-operations", json={**request, "confirmation": token})
    assert response.status_code == 403
    assert not any(method == "PATCH" for method, _, _, _ in calls)


def test_m5_template_step_is_a_distinct_confirmed_semantic_operation_and_route(api):
    """Catches template step edits being sent through the instance-step endpoint."""
    client, mod = api
    calls = []
    def transport(method, url, headers, body, timeout):
        path = url.removeprefix("https://api.vcrcapps.com")
        calls.append((method, path, json.loads(body) if body else None, headers))
        if path == "/auth/me": return 200, {}, {"id": "user-1"}
        if path == "/workspaces/me": return 200, {}, {"id": "ws-1", "role": "owner"}
        if path == "/project-templates/template-1/steps/step-1" and method == "GET": return 200, {}, {"id": "step-1", "ownerId": "user-1", "workspaceId": "ws-1", "title": "Canonical"}
        if path == "/project-templates/template-1/steps/step-1" and method == "PATCH": return 200, {}, {"id": "step-1"}
        raise AssertionError((method, path))
    _connect(client, mod, transport)
    request = {"operation": "projects.update-template-step", "entityId": "step-1", "payload": {"templateId": "template-1", "title": "Canonical"}, "generation": "generation-1"}
    token = client.post("/api/plugins/rhythm/workspace-operations/confirmation", json=request).json()["confirmation"]
    response = client.post("/api/plugins/rhythm/workspace-operations", json={**request, "confirmation": token})
    assert response.status_code == 200, response.text
    assert ("PATCH", "/project-templates/template-1/steps/step-1") in [(method, path) for method, path, _, _ in calls]
    assert not any(path == "/project-instances/steps/step-1" for _, path, _, _ in calls)


def test_m5_instance_step_update_authorizes_and_reads_back_the_exact_step(api):
    """Catches an instance step GET being rejected or replaced with a collection readback."""
    client, mod = api
    calls = []
    def transport(method, url, headers, body, timeout):
        path = url.removeprefix("https://api.vcrcapps.com")
        calls.append((method, path, json.loads(body) if body else None, headers))
        if path == "/auth/me": return 200, {}, {"id": "user-1"}
        if path == "/workspaces/me": return 200, {}, {"id": "ws-1", "role": "owner"}
        if path == "/project-instances/steps/step-1" and method == "GET": return 200, {}, {"id": "step-1", "title": "Canonical step", "notes": "", "status": "done", "ownerId": "user-1", "workspaceId": "ws-1"}
        if path == "/project-instances/steps/step-1" and method == "PATCH": return 200, {}, {"id": "step-1", "raw": "untrusted"}
        raise AssertionError((method, path))
    _connect(client, mod, transport)
    request = {"operation": "projects.update-step", "entityId": "step-1", "payload": {"instanceId": "instance-1", "status": "done"}, "generation": "generation-1"}
    receipt = client.post("/api/plugins/rhythm/workspace-operations/confirmation", json=request).json()["confirmation"]
    response = client.post("/api/plugins/rhythm/workspace-operations", json={**request, "confirmation": receipt})
    assert response.status_code == 200, response.text
    assert response.json()["id"] == "step-1"
    assert [row[:2] for row in calls].count(("GET", "/project-instances/steps/step-1")) >= 2


@pytest.mark.parametrize("operation,entity_id,payload,post_path,readback_path", [
    ("projects.create-template", "new-template", {"name": "Template"}, "/project-templates", "/project-templates/template-1"),
    ("projects.create-instance", "template-1", {"anchorDate": "2026-08-17"}, "/project-templates/template-1/generate", "/project-instances/instance-1"),
    ("projects.create-step", "template-1", {"templateId": "template-1", "title": "Step", "offsetDays": 2}, "/project-templates/template-1/steps", "/project-templates/template-1/steps/step-1"),
    ("projects.create-milestone", "instance-1", {"title": "Milestone"}, "/project-instances/instance-1/milestones", "/project-instances/instance-1/milestones/milestone-1"),
])
def test_m5_project_creates_return_only_exact_canonical_entity_readbacks(api, operation, entity_id, payload, post_path, readback_path):
    """Catches a POST response or collection envelope being returned as a created entity."""
    client, mod = api
    calls = []
    created_id = readback_path.rsplit("/", 1)[-1]
    def transport(method, url, headers, body, timeout):
        path = url.removeprefix("https://api.vcrcapps.com")
        calls.append((method, path, json.loads(body) if body else None, headers))
        if path == "/auth/me": return 200, {}, {"id": "user-1"}
        if path == "/workspaces/me": return 200, {}, {"id": "ws-1", "role": "owner"}
        if method == "GET" and path in {"/project-templates/template-1", "/project-instances/instance-1"}:
            raw = {"id": path.rsplit("/", 1)[-1], "ownerId": "user-1", "workspaceId": "ws-1", "name": "Parent"}
            if path == readback_path:
                raw.update({"title": "Created", "anchorDate": "2026-08-17", "status": "active", "templateId": "template-1", **payload})
            return 200, {}, raw
        if method == "POST" and path == post_path: return 200, {}, {"id": created_id, "accessToken": TOKEN, "raw": "untrusted"}
        if method == "GET" and path == readback_path:
            raw = {"id": created_id, "ownerId": "user-1", "workspaceId": "ws-1", "name": "Created", "title": "Created", "anchorDate": "2026-08-17", "status": "active", "templateId": "template-1", "raw": "untrusted"}
            raw.update(payload)
            return 200, {}, raw
        raise AssertionError((method, path))
    _connect(client, mod, transport)
    request = {"operation": operation, "entityId": entity_id, "payload": payload, "generation": "generation-1"}
    receipt = client.post("/api/plugins/rhythm/workspace-operations/confirmation", json=request).json()["confirmation"]
    response = client.post("/api/plugins/rhythm/workspace-operations", json={**request, "confirmation": receipt})
    assert response.status_code == 200, response.text
    assert response.json()["id"] == created_id
    assert "accessToken" not in response.text and "raw" not in response.text
    assert ("GET", readback_path) in [(method, path) for method, path, _, _ in calls]


def test_m5_vendor_runtime_carries_template_step_operation_and_matching_capability_gates():
    """Catches the accepted runtime advertising a template-step operation behind instance-step gates."""
    runtime = (Path(__file__).parents[3] / "plugins/rhythm/desktop/vendor/rhythm-workspace-ui/dist/index.js").read_text()
    assert '"projects.update-template-step"' in runtime
    assert 'requestOperation(editor.step ? "projects.update-template-step" : "projects.create-step"' in runtime
    assert 'can("projects.update-template-step")' in runtime
    assert 'can(templateStepEditor.step ? "projects.update-template-step" : "projects.create-step")' in runtime


def test_m5_dto_fixtures_include_every_required_screen_field_and_strip_nested_secrets(api):
    """Catches a partial projection that type-casts but crashes a mounted screen's array/render path."""
    _, mod = api
    planner = mod._m5_public("planner", {"weekStart": "2026-08-17", "days": [{"date": "2026-08-17", "tasks": [{"id": "task-1", "title": "Plan", "nested": {"token": TOKEN}}], "events": [{"id": "event-1", "title": "Launch", "date": "2026-08-17"}]}], "backlog": []})
    rule = mod._m5_public("rule", {"id": "rule-1", "title": "Review", "steps": [{"id": "step-1", "title": "Read"}], "nested": {"token": TOKEN}})
    template = mod._m5_public("template", {"id": "template-1", "name": "Launch", "steps": [{"id": "step-1", "title": "Draft"}]})
    instance = mod._m5_public("instance", {"id": "instance-1", "name": "Launch", "steps": [{"id": "step-1", "title": "Ship"}], "milestones": [{"id": "milestone-1", "title": "Release"}]})
    assert set(planner) == {"weekStart", "weekLabel", "days", "backlog"}
    assert set(planner["days"][0]) == {"date", "label", "tasks", "events"}
    assert {"id", "source", "title", "notes", "status", "scheduledOrder", "collaborators", "readonly"} <= set(planner["days"][0]["tasks"][0])
    assert set(planner["days"][0]["events"][0]) == {"id", "title", "date", "timeLabel", "notes", "allDay"}
    assert {"id", "frequency", "ownerId", "ownerName", "collaborators", "steps", "generatedCount", "completedCount", "remainingCount", "waitingOn", "nextDueDate", "completionRatio", "createdAt"} <= set(rule)
    assert set(template) == {"id", "name", "description", "anchorType", "steps"}
    assert {"id", "templateId", "name", "anchorDate", "status", "ownerId", "collaborators", "milestones", "steps"} == set(instance)
    assert TOKEN not in json.dumps([planner, rule, template, instance])
