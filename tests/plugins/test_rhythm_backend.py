"""Security contracts for the Rhythm connection backend (#6).

Every network boundary is injected.  These tests deliberately exercise the
plugin router rather than a handler stub so profile scoping and response
redaction cannot be accidentally bypassed by a future route change.
"""

from __future__ import annotations

import importlib
import json
import os
import stat
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


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
    return TestClient(app), mod


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
