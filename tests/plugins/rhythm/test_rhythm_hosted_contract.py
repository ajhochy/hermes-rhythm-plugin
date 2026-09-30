"""Contracts copied from the shipping Rhythm desktop/API shapes, without live credentials."""

import json
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plugins.rhythm.backend.client import RhythmClient
from plugins.rhythm.dashboard import plugin_api


PUBLIC_CLIENT_ID = '123456-example.apps.googleusercontent.com'
SESSION_TOKEN = 'fixture-session-token'


def test_desktop_code_exchanges_at_pinned_rhythm_endpoint_for_session_token():
    calls = []

    def transport(method, url, headers, body, timeout):
        calls.append((method, url, headers, json.loads(body)))
        return 200, {}, {'sessionToken': SESSION_TOKEN, 'user': {'id': 7}}

    token = RhythmClient('', transport=transport).exchange_code(
        'code', 'verifier', 'http://127.0.0.1:48761/api/plugins/rhythm/oauth/callback'
    )

    assert token == SESSION_TOKEN
    assert calls == [(
        'POST', 'https://api.vcrcapps.com/auth/google/desktop-exchange',
        {'Accept': 'application/json', 'Content-Type': 'application/json'},
        {'code': 'code', 'codeVerifier': 'verifier', 'redirectUri': 'http://127.0.0.1:48761/api/plugins/rhythm/oauth/callback'},
    )]


def test_hosted_auth_me_and_workspace_ids_are_sanitized_from_numeric_api_shapes():
    identity = plugin_api._safe_identity({'user': {'id': 7, 'email': 'a@example.test', 'name': 'A'}, 'workspaceRole': 'staff'})
    workspace = plugin_api._safe_workspace({'id': 9, 'name': 'Team', 'joinCode': 'private'})
    assert identity == {'id': '7', 'email': 'a@example.test'}
    assert workspace == {'id': '9', 'name': 'Team'}


def test_oauth_start_uses_profile_configured_public_desktop_client_id(tmp_path, monkeypatch):
    home = tmp_path / '.hermes'
    home.mkdir()
    (home / 'config.yaml').write_text(
        f'plugins:\n  rhythm:\n    google_desktop_client_id: {PUBLIC_CLIENT_ID}\n'
    )
    monkeypatch.setenv('HERMES_HOME', str(home))
    monkeypatch.setattr(plugin_api, 'request', lambda method, url, headers, body, timeout: (200, {}, {'loginOnlyDesktopExchange': True}))
    app = FastAPI()
    app.include_router(plugin_api.router, prefix='/api/plugins/rhythm')
    client = TestClient(app, base_url='http://127.0.0.1:48761')
    result = client.post('/api/plugins/rhythm/oauth/start')
    assert result.status_code == 200
    query = parse_qs(urlsplit(result.json()['authorization_url']).query)
    assert query['client_id'] == [PUBLIC_CLIENT_ID]
    assert query['redirect_uri'] == ['http://127.0.0.1:48761/api/plugins/rhythm/oauth/callback']


def test_oauth_start_fails_closed_without_public_client_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path / '.hermes'))
    app = FastAPI()
    app.include_router(plugin_api.router, prefix='/api/plugins/rhythm')
    result = TestClient(app, base_url='http://127.0.0.1:48761').post('/api/plugins/rhythm/oauth/start')
    assert result.status_code == 503
    assert 'authorization_url' not in result.json()


def test_oauth_start_requests_the_same_grant_as_the_electron_desktop_app(tmp_path, monkeypatch):
    """Catches a narrowed plugin grant.

    The shared POST /auth/google/desktop-exchange writes this grant's scope and
    refresh token onto the one Google account row. If the plugin asks for less
    than apps/electron/src/google-oauth-core.mjs does, or omits offline/consent,
    a plugin sign-in silently downgrades Calendar/Gmail and nulls the refresh
    token for every other client. Assert the full request, not just client_id.
    """
    home = tmp_path / '.hermes'
    home.mkdir()
    (home / 'config.yaml').write_text(f'plugins:\n  rhythm:\n    google_desktop_client_id: {PUBLIC_CLIENT_ID}\n')
    monkeypatch.setenv('HERMES_HOME', str(home))
    app = FastAPI()
    app.include_router(plugin_api.router, prefix='/api/plugins/rhythm')
    result = TestClient(app, base_url='http://127.0.0.1:48761').post('/api/plugins/rhythm/oauth/start')
    assert result.status_code == 200
    query = parse_qs(urlsplit(result.json()['authorization_url']).query)
    assert query['scope'] == ['openid email profile https://www.googleapis.com/auth/calendar.readonly']
    assert query['access_type'] == ['offline']
    assert query['prompt'] == ['consent']
    assert query['include_granted_scopes'] == ['true']


def test_oauth_start_needs_no_capability_probe_before_issuing_state(tmp_path, monkeypatch):
    """Catches a reintroduced precondition call to a route production lacks."""
    home = tmp_path / '.hermes'
    home.mkdir()
    (home / 'config.yaml').write_text(f'plugins:\n  rhythm:\n    google_desktop_client_id: {PUBLIC_CLIENT_ID}\n')
    monkeypatch.setenv('HERMES_HOME', str(home))
    calls = []
    monkeypatch.setattr(plugin_api, 'request', lambda method, url, headers, body, timeout: (calls.append(url), (404, {}, {}))[1])
    app = FastAPI()
    app.include_router(plugin_api.router, prefix='/api/plugins/rhythm')
    result = TestClient(app, base_url='http://127.0.0.1:48761').post('/api/plugins/rhythm/oauth/start')
    assert result.status_code == 200
    assert calls == []


def test_nested_hosted_dashboard_projects_bounded_cards_and_counts():
    task = {
        'id': 'task-1', 'title': 'Review', 'notes': 'Private detail', 'status': 'open',
        'scheduledDate': '2026-09-19', 'dueDate': None,
    }
    payload = {
        'tasks': {
            'openCount': 101, 'pastDue': [], 'today': [task], 'thisWeek': [],
            'unscheduled': [], 'recent': [],
        },
        'rhythms': {'activeCount': 0, 'items': []},
        'projects': {'activeCount': 0, 'items': []},
        'goals': {'activeCount': 0, 'items': []},
        'messages': {'threadCount': 4, 'unreadPreviews': []},
    }
    summary = plugin_api._dashboard_summary(payload, {'id': '7'}, {'id': '9'})
    assert summary['openTaskCount'] == 101
    assert summary['threadCount'] == 4
    assert summary['tasks'] == [{
        'id': 'task-1', 'title': 'Review', 'notes': 'Private detail', 'status': 'open',
        'bucket': 'today', 'dueLabel': '2026-09-19',
    }]
    assert summary['project'] is None and summary['unreadThreads'] == []


def test_dashboard_transport_accepts_bounded_realistic_raw_size_but_auth_me_keeps_small_cap(monkeypatch):
    import httpx
    from plugins.rhythm.backend.client import MAX_RESPONSE_BYTES, RhythmProtocolError, _httpx_transport

    body = json.dumps({'tasks': {'recent': [], 'padding': 'x' * 53_000}}).encode()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=httpx.ByteStream(body)))
    real_client = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda *args, **kwargs: real_client(*args, transport=transport, **kwargs))

    status, _, payload = _httpx_transport('GET', 'https://api.vcrcapps.com/dashboard/summary', {}, None, 1.0)
    assert status == 200 and len(payload['tasks']['padding']) == 53_000
    with pytest.raises(RhythmProtocolError, match='response_too_large'):
        _httpx_transport('GET', 'https://api.vcrcapps.com/auth/me', {}, None, 1.0)
    assert len(body) > MAX_RESPONSE_BYTES


def test_hosted_tasks_array_projects_numeric_owner_and_missing_optional_fields():
    hosted = {
        'id': 'task-1', 'title': 'Review', 'notes': 'Detail', 'dueDate': '2026-09-18',
        'scheduledDate': None, 'status': 'open', 'ownerId': 7, 'priority': None,
        'tags': [], 'energy': None, 'workspaceId': None, 'isShared': True,
        'collaborators': [{'userId': 8, 'name': 'A B', 'photoUrl': None}],
        'sourceType': None, 'sourceName': None, 'preferredAgent': None,
        'createdAt': '2026-09-18T12:00:00Z', 'updatedAt': '2026-09-18T12:00:00Z',
    }
    client = RhythmClient(SESSION_TOKEN, transport=lambda *args: (200, {}, [hosted]))
    payload = client.call('GET', '/tasks')
    assert payload == {'tasks': [hosted]}
    projected = plugin_api._task(payload['tasks'][0])
    assert projected['id'] == 'task-1'
    assert projected['ownerId'] == '7'
    assert projected['bucket'] == 'past-due'
    assert projected['priority'] == 0
    assert projected['sourceType'] == 'manual'
    assert projected['collaborators'] == [{'id': '8', 'name': 'A B', 'initials': 'AB'}]


def test_tasks_transport_accepts_bounded_hosted_array_but_other_reads_stay_small(monkeypatch):
    import httpx
    from plugins.rhythm.backend.client import RhythmProtocolError, _httpx_transport

    rows = [{'id': f'task-{i}', 'title': 'x' * 220} for i in range(287)]
    body = json.dumps(rows).encode()
    assert len(body) > 32_768
    transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=httpx.ByteStream(body)))
    real_client = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda *args, **kwargs: real_client(*args, transport=transport, **kwargs))
    status, _, payload = _httpx_transport('GET', 'https://api.vcrcapps.com/tasks', {}, None, 1.0)
    assert status == 200 and len(payload) == 287
    with pytest.raises(RhythmProtocolError, match='response_too_large'):
        _httpx_transport('GET', 'https://api.vcrcapps.com/auth/me', {}, None, 1.0)


def test_router_reads_hosted_contract_through_profile_connection(tmp_path, monkeypatch):
    home = tmp_path / '.hermes'
    home.mkdir()
    monkeypatch.setenv('HERMES_HOME', str(home))
    task = {
        'id': 'task-1', 'title': 'Review', 'notes': 'Detail', 'dueDate': None,
        'scheduledDate': None, 'status': 'open', 'ownerId': 7, 'priority': None,
        'tags': [], 'energy': None, 'isShared': False, 'collaborators': [],
        'sourceType': None, 'sourceName': None, 'preferredAgent': None,
        'createdAt': '2026-09-18T12:00:00Z',
    }
    dashboard = {
        'tasks': {'openCount': 1, 'pastDue': [], 'today': [], 'thisWeek': [],
                  'unscheduled': [task], 'recent': []},
        'rhythms': {}, 'projects': {}, 'goals': {},
        'messages': {'threadCount': 0, 'unreadPreviews': []},
    }
    def transport(method, url, headers, body, timeout):
        assert method == 'GET' and headers['Authorization'] == f'Bearer {SESSION_TOKEN}'
        if url.endswith('/auth/me'):
            return 200, {}, {'user': {'id': 7, 'email': 'a@example.test'}, 'workspaceRole': 'staff'}
        if url.endswith('/workspaces/me'):
            return 200, {}, {'id': 9, 'name': 'Team', 'joinCode': 'private'}
        if url.endswith('/dashboard/summary'):
            return 200, {}, dashboard
        if url.endswith('/tasks'):
            return 200, {}, [task]
        raise AssertionError(url)
    monkeypatch.setattr(plugin_api, 'request', transport)
    app = FastAPI()
    app.include_router(plugin_api.router, prefix='/api/plugins/rhythm')
    client = TestClient(app, base_url='http://127.0.0.1:48761')
    assert client.put('/api/plugins/rhythm/connection', json={'access_token': SESSION_TOKEN}).status_code == 200
    summary = client.get('/api/plugins/rhythm/dashboard-summary')
    tasks = client.get('/api/plugins/rhythm/tasks')
    assert summary.status_code == tasks.status_code == 200
    assert summary.json()['identity']['id'] == '7'
    assert summary.json()['workspace']['id'] == '9'
    assert summary.json()['openTaskCount'] == 1
    assert tasks.json()['tasks'][0]['ownerId'] == '7'
    assert SESSION_TOKEN not in summary.text + tasks.text
    assert 'private' not in summary.text + tasks.text


def test_httpx_advertises_only_supported_compression_and_rejects_ignored_negotiation(monkeypatch):
    import httpx
    from plugins.rhythm.backend.client import RhythmProtocolError, _httpx_transport

    seen = []
    def supported(request):
        seen.append(request.headers.get('accept-encoding'))
        return httpx.Response(200, stream=httpx.ByteStream(b'{"id":7}'))
    real_client = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda *args, **kwargs: real_client(*args, transport=httpx.MockTransport(supported), **kwargs))
    assert _httpx_transport('GET', 'https://api.vcrcapps.com/auth/me', {}, None, 1.0)[2] == {'id': 7}
    assert seen == ['gzip, deflate']

    def unsupported(request):
        return httpx.Response(200, headers={'content-encoding': 'br'}, stream=httpx.ByteStream(b'opaque'))
    monkeypatch.setattr(httpx, 'Client', lambda *args, **kwargs: real_client(*args, transport=httpx.MockTransport(unsupported), **kwargs))
    with pytest.raises(RhythmProtocolError, match='unsupported_content_encoding'):
        _httpx_transport('GET', 'https://api.vcrcapps.com/auth/me', {}, None, 1.0)
