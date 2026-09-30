"""Issue #11 contract: exact shared artifact boundary plus Hermes-only authority."""

from __future__ import annotations

import hashlib
import importlib
import json
import re
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).parents[3]
VENDOR_DIR = ROOT / "plugins/rhythm/desktop/vendor/rhythm-workspace-ui"


def _router_module():
    sys.modules.pop("plugins.rhythm.dashboard.plugin_api", None)
    return importlib.import_module("plugins.rhythm.dashboard.plugin_api")


def test_issue_11_vendor_artifact_runtime_is_exact_and_opaque_origin():
    """Catches a hand-edited or weaker vendored iframe runtime, or a vendor/PROVENANCE drift.

    The prior version of this test diffed against a second copy of the built
    package at a hard-coded path outside the repo
    (``/Users/ajhochhalter/.hermes/worktrees/...``), which does not exist on a
    fresh checkout or in CI. The repo's own recorded provenance is the source
    of truth instead: PROVENANCE.md's SHA-256 for ``index.js`` must match the
    vendored file byte-for-byte (see plugins/rhythm/desktop/vendor/rhythm-workspace-ui/PROVENANCE.md).
    """
    runtime = (VENDOR_DIR / "dist/index.js").read_text()
    provenance = (VENDOR_DIR / "PROVENANCE.md").read_text()
    recorded = re.search(r"`index\.js`\s*`([0-9a-f]{64})`", provenance)
    assert recorded, "PROVENANCE.md must record index.js's SHA-256"
    assert hashlib.sha256(runtime.encode("utf-8")).hexdigest() == recorded.group(1), (
        "vendored dist/index.js no longer matches the hash recorded in PROVENANCE.md"
    )
    for required in ('sandbox: "allow-scripts"', "default-src 'none'", "connect-src 'none'", "form-action 'none'", "base-uri 'none'", "frame-src 'none'", "object-src 'none'", "navigate-to 'none'"):
        assert required in runtime
    assert "ArtifactHostPort" in (VENDOR_DIR / "dist/index.d.ts").read_text()


def test_issue_11_artifact_capabilities_are_session_bound_and_preserve_conflicts(monkeypatch, tmp_path):
    """Catches stale sessions or an unclassified capability reaching host state."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    mod = _router_module()
    app = FastAPI(); app.include_router(mod.router, prefix="/api/plugins/rhythm")
    client = TestClient(app)
    opened = client.post("/api/plugins/rhythm/artifacts/calendar/open", json={"bodyHtml": "<main>Calendar</main><script>bad()</script>", "styleText": "main { color: green }", "scriptText": "bad()"})
    assert opened.status_code == 200, opened.text
    document = opened.json()
    assert "<script" not in document["bodyHtml"].lower()
    assert document["scriptText"] == ""
    message = {key: document[key] for key in ("artifactId", "sessionId", "bundleGeneration", "stateGeneration")}
    message.update({"capability": "state.get", "payload": {}})
    current = client.post("/api/plugins/rhythm/artifacts/calendar/capability", json=message)
    assert current.status_code == 200 and current.json()["status"] == "ok"
    stale = client.post("/api/plugins/rhythm/artifacts/calendar/capability", json={**message, "stateGeneration": "state-stale"})
    assert stale.status_code == 200 and stale.json()["status"] == "conflict"
    rejected = client.post("/api/plugins/rhythm/artifacts/calendar/capability", json={**message, "capability": "pco.services.read"})
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"


def test_issue_11_allowlist_contains_only_classified_reads():
    """Catches adding sends, calendar writes, PCO writes, or a generic proxy."""
    from plugins.rhythm.backend.client import ALLOWED_OPERATIONS

    required = {
        ("GET", "/automations/catalog"), ("GET", "/automations/rules"),
        ("GET", "/automations/rules/{id}/preview"), ("GET", "/integrations/status"),
        ("GET", "/integrations/settings"), ("GET", "/integrations/sync"),
    }
    assert required <= ALLOWED_OPERATIONS
    assert all(method == "GET" for method, path in ALLOWED_OPERATIONS if path.startswith(("/automations", "/integrations")))
    forbidden = ("send", "message", "calendar", "pco", "proxy")
    assert not any(
        any(word in path.lower() for word in forbidden)
        for _, path in ALLOWED_OPERATIONS
        if path.startswith(("/automations", "/integrations"))
    )
    routes = {(method, route.path) for route in _router_module().router.routes for method in route.methods}
    assert {("GET", "/automations/catalog"), ("GET", "/automations/rules"), ("GET", "/automations/rules/{rule_id}/preview"), ("GET", "/integrations/status"), ("GET", "/integrations/settings"), ("GET", "/integrations/sync")} <= routes
    assert not any(method != "GET" and any(word in path.lower() for word in forbidden) for method, path in routes)
    contract = json.loads((ROOT / "docs/ai/contracts/issue-11.json").read_text())
    assert {criterion["criterion_id"] for criterion in contract["criteria"]} == {"issue-11-c1", "issue-11-c2", "issue-11-c3", "issue-11-c4"}
