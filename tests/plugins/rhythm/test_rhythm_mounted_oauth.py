"""Mounted-dashboard contracts for Rhythm's loopback OAuth callback."""

from __future__ import annotations

import json
import sys
from unittest.mock import patch
from urllib.parse import parse_qsl

from fastapi.testclient import TestClient


TOKEN = "rhythm-mounted-test-token-" + "x" * 24
PUBLIC_CLIENT_ID = "123456-example.apps.googleusercontent.com"


def _ok_transport(method, url, headers, body, timeout):
    if url == "https://api.vcrcapps.com/auth/google/desktop-login-capability":
        assert method == "GET" and body is None and "Authorization" not in headers
        return 200, {}, {"loginOnlyDesktopExchange": True}
    if url == "https://api.vcrcapps.com/auth/google/desktop-login-exchange":
        return 200, {}, {"sessionToken": TOKEN, "user": {"id": 7}}
    if url.endswith("/auth/me"):
        return 200, {}, {"id": "user-1", "email": "me@example.test"}
    if url.endswith("/workspaces/me"):
        return 200, {}, {"id": "ws-1", "name": "Personal"}
    raise AssertionError(url)


def _mounted_client(monkeypatch, tmp_path):
    home = tmp_path / ".hermes"
    home.mkdir()
    (home / "config.yaml").write_text(f"plugins:\n  rhythm:\n    google_desktop_client_id: {PUBLIC_CLIENT_ID}\n")
    monkeypatch.setenv("HERMES_HOME", str(home))
    from hermes_cli import web_server
    plugin_api = sys.modules["hermes_dashboard_plugin_rhythm"]

    exchanges = []

    def transport(method, url, headers, body, timeout):
        if url == "https://api.vcrcapps.com/auth/google/desktop-login-exchange":
            exchanges.append(json.loads(body))
        return _ok_transport(method, url, headers, body, timeout)

    monkeypatch.setattr(plugin_api, "request", transport)
    return TestClient(web_server.app, base_url="http://127.0.0.1:48761"), web_server, exchanges


def test_mounted_oauth_callback_uses_request_origin_and_is_only_public_plugin_api(monkeypatch, tmp_path):
    client, web_server, exchanges = _mounted_client(monkeypatch, tmp_path)
    auth = {web_server._SESSION_HEADER_NAME: web_server._SESSION_TOKEN}

    start = client.post("/api/plugins/rhythm/oauth/start", headers=auth)
    assert start.status_code == 200
    payload = start.json()
    query = dict(parse_qsl(payload["authorization_url"].split("?", 1)[1]))
    assert query["redirect_uri"] == "http://127.0.0.1:48761/api/plugins/rhythm/oauth/callback"

    callback = client.get(
        "/api/plugins/rhythm/oauth/callback",
        params={"state": payload["state"], "code": "mounted-code"},
    )
    assert callback.status_code == 200
    assert "mounted-code" not in callback.text
    assert TOKEN not in callback.text
    assert exchanges[0]["redirectUri"] == query["redirect_uri"]
    assert client.get("/api/plugins/rhythm/connection").status_code == 401
    assert client.post("/api/plugins/rhythm/oauth/callback").status_code == 401


def test_mounted_public_callback_is_gated_when_rhythm_is_disabled_at_runtime(monkeypatch, tmp_path):
    client, web_server, exchanges = _mounted_client(monkeypatch, tmp_path)
    auth = {web_server._SESSION_HEADER_NAME: web_server._SESSION_TOKEN}

    with patch("hermes_cli.plugins_cmd._get_enabled_set", return_value={"rhythm"}), patch(
        "hermes_cli.plugins_cmd._get_disabled_set", return_value=set()
    ):
        start = client.post("/api/plugins/rhythm/oauth/start", headers=auth)
        assert start.status_code == 200
        state = start.json()["state"]

    previous_auth_required = getattr(web_server.app.state, "auth_required", None)
    web_server.app.state.auth_required = True
    gated_client = TestClient(web_server.app, base_url="https://dashboard.example.test")
    try:
        with patch("hermes_cli.plugins_cmd._get_enabled_set", return_value={"rhythm"}), patch(
            "hermes_cli.plugins_cmd._get_disabled_set", return_value={"rhythm"}
        ):
            disabled = gated_client.get(
                "/api/plugins/rhythm/oauth/callback",
                params={"state": state, "code": "disabled-code"},
            )
            unknown = gated_client.get("/api/plugins/not-installed/oauth/callback")

        # Regression: a disabled public callback must be indistinguishable from
        # an unknown callback.  A plain legacy 401 disclosed that Rhythm exists.
        assert disabled.status_code == unknown.status_code == 401
        assert disabled.content == unknown.content
        assert disabled.headers == unknown.headers
        assert exchanges == []
    finally:
        web_server.app.state.auth_required = previous_auth_required

    with patch("hermes_cli.plugins_cmd._get_enabled_set", return_value={"rhythm"}), patch(
        "hermes_cli.plugins_cmd._get_disabled_set", return_value=set()
    ):
        enabled = client.get(
            "/api/plugins/rhythm/oauth/callback",
            params={"state": state, "code": "enabled-code"},
        )

    assert enabled.status_code == 200
    assert len(exchanges) == 1


def test_mounted_oauth_callback_rejects_hostile_or_invalid_state_without_echoing_values(monkeypatch, tmp_path, caplog):
    client, web_server, _ = _mounted_client(monkeypatch, tmp_path)
    auth = {web_server._SESSION_HEADER_NAME: web_server._SESSION_TOKEN}
    state = client.post("/api/plugins/rhythm/oauth/start", headers=auth).json()["state"]

    hostile = client.get(
        "/api/plugins/rhythm/oauth/callback",
        params={"state": state, "code": "sensitive-code"},
        headers={"host": "evil.test:48761"},
    )
    assert hostile.status_code == 400
    assert "sensitive-code" not in hostile.text

    invalid = client.get(
        "/api/plugins/rhythm/oauth/callback",
        params={"state": "x" * 16, "code": "sensitive-code"},
    )
    assert invalid.status_code == 409
    assert "sensitive-code" not in invalid.text
    assert "sensitive-code" not in caplog.text


def test_mounted_oauth_state_rejects_callback_origin_mismatch_without_consuming_state(monkeypatch, tmp_path):
    client, web_server, _ = _mounted_client(monkeypatch, tmp_path)
    auth = {web_server._SESSION_HEADER_NAME: web_server._SESSION_TOKEN}
    state = client.post("/api/plugins/rhythm/oauth/start", headers=auth).json()["state"]

    mismatch = client.get(
        "/api/plugins/rhythm/oauth/callback",
        params={"state": state, "code": "wrong-origin-code"},
        headers={"host": "127.0.0.1:48762"},
    )
    assert mismatch.status_code == 409
    assert "wrong-origin-code" not in mismatch.text
    assert client.get(
        "/api/plugins/rhythm/oauth/callback",
        params={"state": state, "code": "right-origin-code"},
    ).status_code == 200
