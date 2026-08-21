"""Issue 10 acceptance contract: bounded M6 message and facilities support."""
import importlib
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


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
        path = url.removeprefix("https://api.rhythm.app"); calls.append((method, path, json.loads(body) if body else None))
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
    assert "704fd53e73f985bfa5eeeb08f1bc499762742dd3" in provenance


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
        path = url.removeprefix("https://api.rhythm.app"); calls.append((method, path, json.loads(body) if body else None))
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
