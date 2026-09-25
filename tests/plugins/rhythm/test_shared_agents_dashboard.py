"""Acceptance contract RP-9 for local shared-agent dashboard routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_rp_9_dashboard_routes_are_closed_and_passthrough(monkeypatch):
    """Regression: renderer routes become a proxy or expose the capability."""
    from plugins.rhythm.dashboard import shared_agents_api

    calls = []

    class Client:
        def call(self, op, **kwargs):
            calls.append((op, kwargs))
            if op == "agent.patch":
                return {"status": "confirmation_required", "confirmationId": "confirm-1", "expiresAt": "later"}
            if op == "agent.patch-status":
                return {"status": "pending"}
            if op == "catalog.list":
                return {"schema": "rhythm.shared-agent-catalog.v1", "agents": []}
            return {"schema": "rhythm.shared-agent.v1", "id": kwargs["path_params"]["agentId"]}

    monkeypatch.setattr(shared_agents_api, "_client", lambda: Client())
    app = FastAPI()
    app.include_router(shared_agents_api.router)
    client = TestClient(app)

    assert client.get("/shared-agents").status_code == 200
    assert client.get("/shared-agents/agent-1?sessionRevision=7").status_code == 200
    invalid_before = len(calls)
    assert client.get("/shared-agents/bad%2Fid").status_code == 400
    assert len(calls) == invalid_before

    saved = client.post("/shared-agents/agent-1/save", json={"expectedRevision": 7, "changes": {"label": "Renamed"}})
    assert saved.status_code == 202
    assert saved.json()["status"] == "confirmation_required"
    assert client.post("/shared-agents/agent-1/save", json={"expectedRevision": 7, "changes": {"label": "x"}, "extra": True}).status_code == 422
    status = client.post("/shared-agents/agent-1/save-status", json={"confirmationId": "confirm-1"})
    assert status.status_code == 200
    assert status.json() == {"status": "pending"}
    assert all("capability" not in str(response).lower() for response in (saved.json(), status.json()))

    manifest = __import__("json").loads((shared_agents_api.__file__ and __import__("pathlib").Path(shared_agents_api.__file__).with_name("manifest.json").read_text()))
    assert all("shared-agents" not in entry["path"] for entry in manifest["public_api"])

