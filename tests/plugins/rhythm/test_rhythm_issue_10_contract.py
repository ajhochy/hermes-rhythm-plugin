"""Issue 10 acceptance contract: bounded M6 message and facilities support."""
import importlib
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest


TOKEN = "rhythm-m6-token-" + "x" * 24


def _api(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    import sys
    sys.modules.pop("plugins.rhythm.dashboard.plugin_api", None)
    module = importlib.import_module("plugins.rhythm.dashboard.plugin_api")
    app = FastAPI(); app.include_router(module.router, prefix="/api/plugins/rhythm")
    client = TestClient(app)
    calls = []
    def transport(method, url, headers, body, timeout):
        path = url.removeprefix("https://api.vcrcapps.com"); calls.append((method, path, json.loads(body) if body else None))
        if path == "/auth/me": return 200, {}, {"id": "user-1"}
        if path == "/workspaces/me": return 200, {}, {"id": "ws-1", "role": "owner"}
        if path == "/message-threads": return 200, {}, {"items": [{"id": "thread-1", "title": "Team", "type": "group", "participants": [{"id": "user-1", "name": "Hermes", "initials": "H"}], "messages": [], "lastMessage": "", "updatedAt": "2026-08-21T09:00:00Z", "unreadCount": 1}]}
        if path == "/users": return 200, {}, {"items": [{"id": "user-1", "name": "Hermes", "initials": "H"}]}
        if path == "/facilities": return 200, {}, {"items": [{"id": "room-1", "name": "Quiet", "building": None, "description": "Room"}]}
        if path.startswith("/facilities/reservations") or path.startswith("/facilities/room-1/reservation-series"):
            return 200, {}, {"items": [{"id": "reservation-1", "facilityId": "room-1", "title": "Focus", "requesterName": "Hermes", "creatorId": "user-1", "start": "2026-08-21T09:00:00Z", "end": "2026-08-21T10:00:00Z", "notes": None}]}
        raise AssertionError((method, path))
    module.request = transport
    assert client.put("/api/plugins/rhythm/connection", json={"access_token": TOKEN}).status_code == 200
    return client, calls


def test_issue_10_c3_vendor_provenance_names_shared_head():
    """Catches a copied artifact whose provenance still points at the prior accepted source."""
    provenance = Path("plugins/rhythm/desktop/vendor/rhythm-workspace-ui/PROVENANCE.md").read_text()
    assert "d676faae5aff11796f39cb5f09031f57d5c5d061" in provenance


def test_issue_10_c1_mounted_reads_are_pinned_and_message_creation_is_not_a_route(tmp_path, monkeypatch):
    client, calls = _api(tmp_path, monkeypatch)
    for path in ("/messages", "/directory", "/facilities", "/facilities/reservations?start=2026-08-21T00%3A00%3A00Z&end=2026-08-22T00%3A00%3A00Z", "/facilities/room-1/series"):
        response = client.get(f"/api/plugins/rhythm{path}")
        assert response.status_code == 200, response.text
    assert client.post("/api/plugins/rhythm/messages").status_code == 405
    assert client.post("/api/plugins/rhythm/messages/thread-1/history").status_code == 405
    assert not any(method == "POST" and path.startswith("/message-threads") for method, path, _ in calls)


def test_issue_10_c2_facility_and_message_writes_are_explicit_and_no_create_send_is_allowlisted():
    module = importlib.import_module("plugins.rhythm.dashboard.plugin_api")
    operations = set(module._M5_UPSTREAM)
    assert {"messages.mark-read", "messages.mark-unread", "facilities.create-facility", "facilities.create-reservation", "facilities.delete-reservations"} <= operations
    assert not any("create-thread" in operation or ".send" in operation for operation in operations)
    from plugins.rhythm.backend.client import RhythmClient, RhythmProtocolError
    with __import__("pytest").raises(RhythmProtocolError):
        RhythmClient(TOKEN, transport=lambda *_: (200, {}, {})).call("POST", "/message-threads", body={})


def test_issue_10_c2_facility_receipt_has_one_pinned_mutation_and_canonical_readback(tmp_path, monkeypatch):
    client, _ = _api(tmp_path, monkeypatch)
    module = importlib.import_module("plugins.rhythm.dashboard.plugin_api")
    calls = []
    def transport(method, url, headers, body, timeout):
        path = url.removeprefix("https://api.vcrcapps.com"); calls.append((method, path, json.loads(body) if body else None))
        if path == "/auth/me": return 200, {}, {"id": "user-1", "isFacilitiesManager": True}
        if path == "/workspaces/me": return 200, {}, {"id": "ws-1", "role": "owner"}
        if method == "POST" and path == "/facilities": return 200, {}, {"id": "room-2", "untrusted": "ignored"}
        if method == "GET" and path == "/facilities/room-2": return 200, {}, {"id": "room-2", "name": "Focus", "building": None, "description": "Quiet", "accessToken": TOKEN}
        raise AssertionError((method, path))
    module.request = transport
    request = {"operation": "facilities.create-facility", "entityId": "new-facility", "payload": {"name": "Focus", "description": "Quiet"}, "generation": "generation-1"}
    receipt = client.post("/api/plugins/rhythm/workspace-operations/confirmation", json=request).json()["confirmation"]
    response = client.post("/api/plugins/rhythm/workspace-operations", json={**request, "confirmation": receipt})
    assert response.status_code == 200, response.text
    assert response.json() == {"id": "room-2", "name": "Focus", "building": None, "description": "Quiet"}
    assert [(method, path, body) for method, path, body in calls if method == "POST"] == [("POST", "/facilities", {"name": "Focus", "description": "Quiet"})]


def test_m6_facility_update_and_delete_use_the_exact_shared_receipt_payload_and_prove_absence(tmp_path, monkeypatch):
    """Catches adding facilityId after confirmation or reporting DELETE success before a canonical absence proof."""
    client, _ = _api(tmp_path, monkeypatch)
    module = importlib.import_module("plugins.rhythm.dashboard.plugin_api")
    calls = []
    deleted = {"value": False}

    def transport(method, url, headers, body, timeout):
        path = url.removeprefix("https://api.vcrcapps.com")
        calls.append((method, path, json.loads(body) if body else None))
        if path == "/auth/me": return 200, {}, {"id": "user-1", "isFacilitiesManager": True}
        if path == "/workspaces/me": return 200, {}, {"id": "ws-1", "role": "owner"}
        if path == "/facilities/room-1" and method == "GET":
            if deleted["value"]: return 404, {}, {"error": "not_found"}
            return 200, {}, {"id": "room-1", "workspaceId": "ws-1", "name": "Before"}
        if path == "/facilities/room-1" and method == "PATCH": return 200, {}, {"id": "room-1"}
        if path == "/facilities/room-1" and method == "DELETE": deleted["value"] = True; return 200, {}, {"id": "room-1"}
        raise AssertionError((method, path))

    module.request = transport
    update = {"operation": "facilities.update-facility", "entityId": "room-1", "payload": {"name": "After"}, "generation": "generation-1"}
    update_receipt = client.post("/api/plugins/rhythm/workspace-operations/confirmation", json=update).json()["confirmation"]
    assert client.post("/api/plugins/rhythm/workspace-operations", json={**update, "confirmation": update_receipt}).status_code == 200
    delete = {"operation": "facilities.delete-facility", "entityId": "room-1", "payload": {}, "generation": "generation-2"}
    delete_receipt = client.post("/api/plugins/rhythm/workspace-operations/confirmation", json=delete).json()["confirmation"]
    response = client.post("/api/plugins/rhythm/workspace-operations", json={**delete, "confirmation": delete_receipt})
    assert response.status_code == 200, response.text
    assert ("PATCH", "/facilities/room-1", {"name": "After"}) in calls
    assert [row[:2] for row in calls].count(("GET", "/facilities/room-1")) == 4


@pytest.mark.parametrize(("operation", "entity_id", "payload"), [
    ("facilities.update-reservation", "reservation-1", {"title": "Changed"}),
    ("facilities.delete-group", "group-1", {}),
    ("facilities.delete-series", "series-1", {}),
])
def test_m6_reservation_group_and_series_reauthorize_actual_targets_and_never_mutate_a_nonowner(tmp_path, monkeypatch, operation, entity_id, payload):
    """Catches authorizing only the facility, which lets a non-owner mutate a re-homed reservation/group/series."""
    client, _ = _api(tmp_path, monkeypatch)
    module = importlib.import_module("plugins.rhythm.dashboard.plugin_api")
    calls = []

    def transport(method, url, headers, body, timeout):
        path = url.removeprefix("https://api.vcrcapps.com")
        calls.append((method, path, json.loads(body) if body else None))
        if path == "/auth/me": return 200, {}, {"id": "user-1", "isFacilitiesManager": False}
        if path == "/workspaces/me": return 200, {}, {"id": "ws-1", "role": "owner"}
        if path == "/facilities/reservations" and method == "GET":
            return 200, {}, {"items": [{"id": "reservation-1", "facilityId": "room-1", "workspaceId": "ws-1", "createdByUserId": "user-2", "creatorId": "user-2", "title": "Reserved", "requesterName": "Other user", "start": "2026-08-22T10:00:00Z", "end": "2026-08-22T11:00:00Z", "notes": None}]}
        if path == "/facilities/reservations?grouped=true" and method == "GET":
            return 200, {}, {"items": [{"group": {"id": "group-1", "workspaceId": "ws-1", "createdByUserId": "user-2"}, "facilities": [{"id": "room-1"}]}]}
        if path == "/facilities" and method == "GET": return 200, {}, {"items": [{"id": "room-1"}]}
        if path == "/facilities/room-1/reservation-series" and method == "GET":
            return 200, {}, {"items": [{"id": "series-1", "facilityId": "room-1", "workspaceId": "ws-1", "createdByUserId": "user-2"}]}
        if method in {"PATCH", "DELETE"}: raise AssertionError("non-owner must not mutate")
        raise AssertionError((method, path))

    module.request = transport
    request = {"operation": operation, "entityId": entity_id, "payload": payload, "generation": "generation-1"}
    receipt = client.post("/api/plugins/rhythm/workspace-operations/confirmation", json=request).json()["confirmation"]
    response = client.post("/api/plugins/rhythm/workspace-operations", json={**request, "confirmation": receipt})
    assert response.status_code == 403, (response.text, calls)
    assert not any(method in {"PATCH", "DELETE"} for method, _, _ in calls)


def test_m6_bulk_delete_proves_every_submitted_id_absent_and_binds_workspace(tmp_path, monkeypatch):
    """Bulk cleanup succeeds only after a canonical collection read proves every requested ID absent."""
    client, _ = _api(tmp_path, monkeypatch)
    module = importlib.import_module("plugins.rhythm.dashboard.plugin_api")
    calls = []

    def transport(method, url, headers, body, timeout):
        path = url.removeprefix("https://api.vcrcapps.com")
        calls.append((method, path, json.loads(body) if body else None))
        if path == "/auth/me": return 200, {}, {"id": "user-1", "isFacilitiesManager": True}
        if path == "/workspaces/me": return 200, {}, {"id": "ws-1", "role": "facilities_manager"}
        if path == "/facilities/automation-reservations" and method == "DELETE":
            return 200, {}, {"deletedIds": ["reservation-1", "reservation-2"]}
        if path == "/facilities/reservations" and method == "GET": return 200, {}, {"items": []}
        raise AssertionError((method, path))

    module.request = transport
    request = {"operation": "facilities.delete-reservations", "entityId": "automation-reservations", "payload": {"ids": ["reservation-1", "reservation-2"]}, "generation": "generation-1"}
    receipt = client.post("/api/plugins/rhythm/workspace-operations/confirmation", json=request).json()["confirmation"]
    response = client.post("/api/plugins/rhythm/workspace-operations", json={**request, "confirmation": receipt})
    assert response.status_code == 200, response.text
    assert calls[-1][:2] == ("GET", "/facilities/reservations")
    assert module._m6_authorized("facilities.update-reservation", {"workspaceId": "other-ws", "creatorId": "user-1"}, {"id": "user-1", "isFacilitiesManager": True}, {"id": "ws-1"}) is False
