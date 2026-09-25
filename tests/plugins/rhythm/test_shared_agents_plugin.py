"""Acceptance contracts RP-1 through RP-6 for the Rhythm bridge plugin."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from types import SimpleNamespace

import pytest


TOKEN = "A" * 43
ORIGIN = "http://127.0.0.1:7451"


def _snapshot(*, profile_id: str = "default"):
    source = SimpleNamespace(reference="projection-1")
    binding = SimpleNamespace(profile_id=profile_id)
    return SimpleNamespace(version=2, source=source, binding=binding)


def test_rp_1_bridge_client_enforces_transport_contract(monkeypatch, caplog):
    """Regression: callers can redirect, inject paths, or leak the bearer."""
    from agent.host_capabilities import HostCapability
    from plugins.rhythm import agent_bridge

    monkeypatch.setattr(
        agent_bridge.host_capabilities,
        "get",
        lambda name: HostCapability(TOKEN, ORIGIN) if name == "rhythm_bridge" else None,
    )
    seen = []

    def transport(method, url, headers, body, timeout, max_bytes):
        seen.append((method, url, headers, body, timeout, max_bytes))
        return 200, {}, {"id": "agent-1"}

    client = agent_bridge.BridgeClient(transport=transport)
    assert client.call("catalog.get", path_params={"agentId": "agent 1"}) == {"id": "agent-1"}
    assert seen[0][1] == f"{ORIGIN}/agent-bridge/v1/catalog/agent%201"
    assert seen[0][2]["X-Rhythm-Bridge-Capability"] == TOKEN

    with pytest.raises(agent_bridge.BridgeError) as unknown:
        client.call("not.an.operation")
    assert unknown.value.code == "operation_not_allowed"

    def redirect(*_args):
        return 302, {"location": "http://example.invalid/"}, {}

    with pytest.raises(agent_bridge.BridgeError) as redirected:
        agent_bridge.BridgeClient(transport=redirect).call("catalog.list")
    assert redirected.value.code == "redirect_rejected"
    assert TOKEN not in str(redirected.value)
    assert TOKEN not in caplog.text

    def oversized(*_args):
        return 200, {}, {"value": "x" * 300_000}

    with pytest.raises(agent_bridge.BridgeError) as too_large:
        agent_bridge.BridgeClient(transport=oversized).call("projection.check", path_params={"projectionId": "p-1"}, body={"sessionKey": "s", "includeSnapshot": False})
    assert too_large.value.code == "response_too_large"

    attempts = []

    def flaky(*args):
        attempts.append(args)
        if len(attempts) == 1:
            raise OSError("transient")
        return 201, {}, {"job": {"jobId": "job-1"}}

    replay = agent_bridge.BridgeClient(transport=flaky).call(
        "delegation.dispatch", body={"idempotencyKey": "fixed"}
    )
    assert replay["job"]["jobId"] == "job-1"
    assert len(attempts) == 2
    assert attempts[0][3] == attempts[1][3]

    class StubHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.path == "/agent-bridge/v1/catalog"
            assert self.headers["X-Rhythm-Bridge-Capability"] == TOKEN
            payload = b'{"schema":"rhythm.shared-agent-catalog.v1","agents":[]}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):
            pass

    stub = ThreadingHTTPServer(("127.0.0.1", 0), StubHandler)
    thread = threading.Thread(target=stub.serve_forever, daemon=True)
    thread.start()
    try:
        local_origin = f"http://127.0.0.1:{stub.server_address[1]}"
        monkeypatch.setattr(agent_bridge.host_capabilities, "get", lambda _name: HostCapability(TOKEN, local_origin))
        assert agent_bridge.BridgeClient().call("catalog.list")["agents"] == []
    finally:
        stub.shutdown()
        stub.server_close()
        thread.join(timeout=2)


def test_rp_2_provider_resolve_restore_check_and_errors(monkeypatch):
    """Regression: selection or bridge errors bypass frozen-policy checks."""
    from agent.host_capabilities import HostCapability
    from agent.session_policy import UnsupportedPolicy
    from plugins.rhythm import agent_bridge, shared_agents

    monkeypatch.setattr(shared_agents.host_capabilities, "get", lambda _name: HostCapability(TOKEN, ORIGIN))
    calls = []

    class Client:
        def call(self, op, **kwargs):
            calls.append((op, kwargs))
            if op == "projection.issue":
                return {"snapshot": {"version": 2}, "ownerId": "local-user", "projectionId": "projection-1"}
            if kwargs["body"]["includeSnapshot"]:
                return {"ok": True, "ownerId": "local-user", "snapshot": {"version": 2}}
            return {"ok": True, "ownerId": "local-user"}

    provider = shared_agents.RhythmSessionPolicyProvider(client=Client())
    payload, owner = provider.resolve(
        "rhythm-shared-agent:v1:agent-1@7",
        session_id="session-1",
        profile_id="default",
        runtime_generation="generation-1",
        transport=object(),
        cwd="/work/project",
    )
    assert (payload, owner) == ({"version": 2}, "local-user")
    assert calls[0] == (
        "projection.issue",
        {"body": {"sessionKey": "session-1", "cwd": "/work/project", "launchKind": "interactive", "acceptVersions": [2], "agentId": "agent-1", "expectedRevision": 7}},
    )
    assert provider.restore("projection-1", lineage_root="session-1", profile_id="default") == ({"version": 2}, "local-user")
    provider.check("projection-1", lineage_root="session-1", profile_id="default")

    from tui_gateway.session_driver import DriverTransport

    job_id = "00000000-0000-4000-8000-000000000001"
    with pytest.raises(UnsupportedPolicy) as wrong_transport:
        provider.resolve(
            f"rhythm-job:v1:{job_id}", session_id="child", profile_id="default",
            runtime_generation="g", transport=object(), cwd=None,
        )
    assert wrong_transport.value.code == "transport_not_allowed"
    with shared_agents.worker_claim(job_id, "B" * 43):
        provider.resolve(
            f"rhythm-job:v1:{job_id}", session_id="child", profile_id="default",
            runtime_generation="g", transport=DriverTransport(lambda _event: None), cwd=None,
        )
    assert calls[-1][1]["body"]["leaseToken"] == "B" * 43

    with pytest.raises(UnsupportedPolicy) as bad_profile:
        provider.resolve("rhythm-shared-agent:v1:agent-1@7", session_id="s", profile_id="other", runtime_generation="g", transport=object(), cwd=None)
    assert bad_profile.value.code == "profile_unsupported"
    with pytest.raises(UnsupportedPolicy) as bad_selection:
        provider.resolve("rhythm-shared-agent:v1:../bad@7", session_id="s", profile_id="default", runtime_generation="g", transport=object(), cwd=None)
    assert bad_selection.value.code == "selection_invalid"

    class ConflictClient:
        def call(self, *_args, **_kwargs):
            raise agent_bridge.BridgeError("revision_conflict")

    with pytest.raises(UnsupportedPolicy) as conflict:
        shared_agents.RhythmSessionPolicyProvider(client=ConflictClient()).resolve(
            "rhythm-shared-agent:v1:agent-1@7", session_id="s", profile_id="default", runtime_generation="g", transport=object(), cwd=None
        )
    assert conflict.value.code == "revision_conflict"


def test_rp_2_restore_uses_bridge_owner_in_fresh_provider_and_closes_on_mismatch():
    """Regression: cross-process restore depends on process-local owner memory."""
    from agent.session_policy import UnsupportedPolicy
    from plugins.rhythm import agent_bridge, shared_agents

    class FreshProcessClient:
        def call(self, op, **kwargs):
            assert op == "projection.check"
            assert kwargs == {
                "path_params": {"projectionId": "projection-1"},
                "body": {"sessionKey": "session-1", "includeSnapshot": True},
            }
            return {"ok": True, "ownerId": "local-user", "snapshot": {"version": 2}}

    provider = shared_agents.RhythmSessionPolicyProvider(client=FreshProcessClient())
    assert provider.restore(
        "projection-1", lineage_root="session-1", profile_id="default"
    ) == ({"version": 2}, "local-user")

    class OwnerMismatchClient:
        def call(self, *_args, **_kwargs):
            raise agent_bridge.BridgeError("projection_owner_mismatch")

    with pytest.raises(UnsupportedPolicy) as mismatch:
        shared_agents.RhythmSessionPolicyProvider(client=OwnerMismatchClient()).restore(
            "projection-1", lineage_root="session-1", profile_id="default"
        )
    assert mismatch.value.code == "projection_owner_mismatch"


def test_rp_3_register_is_idempotent(monkeypatch):
    """Regression: repeated discovery starts workers and providers twice."""
    import plugins.rhythm as rhythm

    rhythm._reset_shared_agent_registration_for_tests()
    calls = {"provider": 0, "worker": 0, "tools": []}

    monkeypatch.setattr(rhythm, "register_shared_agent_provider", lambda: calls.__setitem__("provider", calls["provider"] + 1))
    monkeypatch.setattr(rhythm, "start_delegation_worker", lambda: calls.__setitem__("worker", calls["worker"] + 1))
    monkeypatch.setattr(rhythm, "register_tools", lambda ctx: calls["tools"].append(("legacy", id(ctx))))
    monkeypatch.setattr(rhythm, "register_bridge_tools", lambda ctx: calls["tools"].append(("bridge", id(ctx))))

    class Context:
        pass

    ctx = Context()
    rhythm.register(ctx)
    rhythm.register(ctx)
    assert calls == {"provider": 1, "worker": 1, "tools": [("legacy", id(ctx)), ("bridge", id(ctx))]}


def test_rp_4_tools_require_v2_and_reuse_one_idempotency_key(monkeypatch):
    """Regression: non-shared sessions dispatch, or retries mint new jobs."""
    from plugins.rhythm import bridge_tools

    calls = []

    class Client:
        def call(self, op, **kwargs):
            calls.append((op, kwargs))
            return {"job": {"jobId": "job-1"}}

    monkeypatch.setattr(bridge_tools, "_client", lambda: Client())
    monkeypatch.setattr(bridge_tools, "current_policy", lambda: None)
    assert json.loads(bridge_tools.rhythm_delegate({"targetAgentId": "a", "prompt": "p"}))["error"] == "shared_agent_session_required"
    assert calls == []

    monkeypatch.setattr(bridge_tools, "current_policy", lambda: (_snapshot(), "lineage-1"))
    result = json.loads(bridge_tools.rhythm_delegate({"targetAgentId": "agent-2", "prompt": "work", "context": "ctx"}))
    assert result["job"]["jobId"] == "job-1"
    body = calls[0][1]["body"]
    assert body["parent"] == {"projectionId": "projection-1", "sessionKey": "lineage-1"}
    assert body["idempotencyKey"]
    assert len({body["idempotencyKey"]}) == 1


def test_rp_4_bridge_tool_schemas_and_dispatch_are_policy_scoped(tmp_path):
    """Regression: bridge tools leak through ordinary or deferred catalogs."""
    import model_tools
    from agent.session_policy import SessionPolicySnapshot
    from plugins.rhythm import bridge_tools
    from tools.registry import registry

    registrations = {}

    class Context:
        def register_tool(self, **kwargs):
            registrations[kwargs["name"]] = kwargs

    bridge_tools.register_bridge_tools(Context())
    expected = set(bridge_tools._TOOLS)
    assert set(registrations) == expected
    assert all(row.get("policy_scoped") is True for row in registrations.values())

    root = str(tmp_path.resolve())
    binding = {
        "session_id": "lineage-1",
        "owner_id": "local-user",
        "profile_id": "default",
        "runtime_generation": "generation-1",
    }
    payload = {
        "version": 2,
        "source": {
            "agent_id": "agent-1",
            "revision": 7,
            "reference": "projection-1",
        },
        "instructions": "frozen",
        "model": {"provider": "openrouter", "model": "fixture", "reasoning": None},
        "allowed_tools": sorted(expected),
        "tool_effects": {},
        "paths": {
            "root": root,
            "boundary": [root],
            "external": "deny",
            "protected": [],
        },
        "rules": [],
        "taint_gate": {"sources": [], "gated": []},
        "launch": {"kind": "interactive", "cwd": root},
    }
    allowed = SessionPolicySnapshot.from_mapping(payload, binding=binding)
    denied = SessionPolicySnapshot.from_mapping(
        {**payload, "allowed_tools": []}, binding=binding
    )
    v1 = SessionPolicySnapshot.from_mapping(
        {
            "version": 1,
            "source": {"agent_id": "legacy", "revision": 1},
            "instructions": "legacy",
            "model": {"provider": "openrouter", "model": "legacy", "reasoning": "low"},
            "allowed_tools": sorted(expected),
            "rules": [],
        },
        binding=binding,
    )

    previous = {name: registry.snapshot_registration(name) for name in expected}
    try:
        for row in registrations.values():
            registry.register(**row, override=True)

        def offered(policy=None):
            return {
                item["function"]["name"]
                for item in model_tools.get_tool_definitions(
                    enabled_toolsets=["rhythm"],
                    quiet_mode=True,
                    skip_tool_search_assembly=True,
                    session_policy=policy,
                )
            }

        assert expected.isdisjoint(offered())
        assert expected.isdisjoint(offered(v1))
        assert expected.isdisjoint(offered(denied))
        assert expected <= offered(allowed)

        def searched(policy=None):
            result = model_tools.handle_function_call(
                "tool_search",
                {"query": "rhythm", "limit": 20},
                enabled_toolsets=["rhythm"],
                session_policy=policy,
                policy_binding=binding if policy is not None else None,
            )
            return {item["name"] for item in json.loads(result)["matches"]}

        assert expected.isdisjoint(searched())
        assert expected <= searched(allowed)

        for name in expected:
            refused = json.loads(
                model_tools.handle_function_call(
                    name,
                    {},
                    skip_pre_tool_call_hook=True,
                    skip_tool_request_middleware=True,
                    skip_tool_execution_middleware=True,
                )
            )
            assert refused == {
                "error": "policy_scoped_tool_unavailable",
                "code": "policy_scoped_tool_unavailable",
            }
    finally:
        for name, prior in previous.items():
            current = registry.snapshot_registration(name)
            if current is not None:
                registry.restore_registration(name, current, prior)


def test_rp_5_delegation_reads_are_parent_scoped_and_untrusted(monkeypatch):
    """Regression: a job id can be read or cancelled outside its parent."""
    from plugins.rhythm import bridge_tools

    calls = []

    class Client:
        def call(self, op, **kwargs):
            calls.append((op, kwargs))
            if op == "delegation.result":
                return {"jobId": "job-1", "state": "succeeded", "untrusted": True, "text": "model text", "truncated": False, "deliveredAt": "now"}
            return {"jobs": []} if op == "delegation.status" else {"job": {"jobId": "job-1"}}

    monkeypatch.setattr(bridge_tools, "_client", lambda: Client())
    monkeypatch.setattr(bridge_tools, "current_policy", lambda: (_snapshot(), "lineage-1"))
    bridge_tools.rhythm_delegation_status({"jobId": "job-1"})
    result = json.loads(bridge_tools.rhythm_delegation_result({"jobId": "job-1"}))
    bridge_tools.rhythm_delegation_cancel({"jobId": "job-1"})
    parent = {"projectionId": "projection-1", "sessionKey": "lineage-1"}
    assert all(call[1]["body"]["parent"] == parent for call in calls)
    assert result["untrusted_user_text"] is True


def test_rp_6_memory_search_policy_bounds_and_consent(monkeypatch):
    """Regression: memory search escapes default-profile consent or trust labels."""
    from plugins.rhythm import agent_bridge, bridge_tools

    calls = []

    class Client:
        def call(self, op, **kwargs):
            calls.append((op, kwargs))
            return {"schema": "rhythm.memory-search.v1", "untrusted": True, "results": [{"ref": "opaque", "snippet": "text"}], "omitted": {"stale": 0, "unreadable": 0}}

    monkeypatch.setattr(bridge_tools, "_client", lambda: Client())
    monkeypatch.setattr(bridge_tools, "current_policy", lambda: (_snapshot(profile_id="other"), "lineage"))
    assert json.loads(bridge_tools.rhythm_memory_search({"query": "hello"}))["error"] == "shared_agent_session_required"
    assert calls == []

    monkeypatch.setattr(bridge_tools, "current_policy", lambda: (_snapshot(), "lineage"))
    result = json.loads(bridge_tools.rhythm_memory_search({"query": "hello", "limit": 10}))
    assert calls[0] == ("memory.search", {"body": {"query": "hello", "limit": 10}})
    assert result["untrusted_user_text"] is True

    class ConsentClient:
        def call(self, *_args, **_kwargs):
            raise agent_bridge.BridgeError("memory_vault_changed")

    monkeypatch.setattr(bridge_tools, "_client", lambda: ConsentClient())
    assert json.loads(bridge_tools.rhythm_memory_search({"query": "hello"}))["error"] == "memory_consent_required"
    assert json.loads(bridge_tools.rhythm_memory_search({"query": ""}))["error"] == "invalid_query"
