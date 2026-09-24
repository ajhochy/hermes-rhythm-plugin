"""Native session policy plumbing without provider calls or a running server."""
from __future__ import annotations

import pytest

from agent.session_policy import register_session_policy_provider


class FixtureProvider:
    def __init__(self):
        self.revision = 1

    def resolve(self, selection, **context):
        assert selection == "opaque-fixture-selection"
        assert context["session_id"]
        assert context["transport"] is not None
        return ({
            "version": 1,
            "source": {"agent_id": "fixture-agent", "revision": self.revision},
            "instructions": f"FROZEN-FIXTURE-{self.revision}",
            "model": {"provider": "openrouter", "model": "fixture-model", "reasoning": "low"},
            "allowed_tools": [],
            "rules": [],
        }, "fixture-owner")


def test_session_create_uses_registered_provider_and_freezes_selection(monkeypatch):
    from tui_gateway import server

    provider = FixtureProvider()
    dispose = register_session_policy_provider(provider)
    monkeypatch.setattr(server, "_schedule_agent_build", lambda sid: None)
    try:
        result = server.handle_request({
            "id": "n0", "method": "session.create",
            "params": {"policy_selection": "opaque-fixture-selection"},
        })
        assert "error" not in result, result
        sid = result["result"]["session_id"]
        session = server._sessions[sid]
        old = session["session_policy"]
        assert old.binding.session_id == session["session_key"]
        assert old.source.revision == 1
        provider.revision = 2
        assert session["session_policy"].instructions == "FROZEN-FIXTURE-1"
    finally:
        dispose()
        if "sid" in locals():
            with server._sessions_lock:
                server._sessions.pop(sid, None)


def test_no_provider_returns_bounded_policy_error(monkeypatch):
    from tui_gateway import server

    monkeypatch.setattr(server, "_schedule_agent_build", lambda sid: None)
    result = server.handle_request({
        "id": "n0", "method": "session.create",
        "params": {"policy_selection": "opaque-fixture-selection"},
    })
    assert result["error"]["message"] == "unsupported_policy"


def test_real_agent_constructor_filters_offered_tools(tmp_path):
    from agent.session_policy import SessionPolicySnapshot
    from run_agent import AIAgent

    binding = {"session_id": "fixture-native-session", "owner_id": "fixture-owner",
               "profile_id": "default", "runtime_generation": "fixture-generation"}
    payload = {
        "version": 1,
        "source": {"agent_id": "fixture", "revision": 1},
        "instructions": "FROZEN-CONSTRUCTOR-MARKER",
        "model": {"provider": "custom", "model": "fixture-model", "reasoning": "low"},
        "allowed_tools": [], "rules": [],
    }
    snapshot = SessionPolicySnapshot.from_mapping(payload, binding=binding)
    agent = AIAgent(
        base_url="http://127.0.0.1:9/v1", api_key="fixture-only",
        provider="custom", model="fixture-model", session_id=binding["session_id"],
        session_policy=snapshot, ephemeral_system_prompt=snapshot.instructions,
        quiet_mode=True, skip_context_files=True, skip_memory=True,
    )
    try:
        assert agent.tools == []
        assert agent.valid_tool_names == set()
        assert agent.session_policy is snapshot
        assert agent.ephemeral_system_prompt == "FROZEN-CONSTRUCTOR-MARKER"
        from tools.mcp_tool import refresh_agent_mcp_tools
        assert refresh_agent_mcp_tools(agent) == set()
        assert agent.tools == []
        from agent.tool_executor import _run_agent_tool_execution_middleware
        marker = tmp_path / "forbidden"

        def execute(_args):
            marker.write_text("escaped")
            return "executed"

        result = _run_agent_tool_execution_middleware(
            agent, function_name="terminal", function_args={"command": "echo unsafe"},
            effective_task_id="fixture", tool_call_id="fixture-call", execute=execute,
        )
        assert result.blocked is True
        assert "policy" in result.result.lower()
        assert not marker.exists()
    finally:
        agent.close()


def test_native_resume_reconstructs_frozen_policy_without_provider():
    from tui_gateway import server
    from agent.session_policy import SessionPolicySnapshot

    binding = {"session_id": "persisted-session", "owner_id": "fixture-owner",
               "profile_id": "default", "runtime_generation": "old-generation"}
    payload = {"version": 1, "source": {"agent_id": "fixture", "revision": 1},
               "instructions": "FROZEN-REVISION-1",
               "model": {"provider": "openrouter", "model": "fixture-model", "reasoning": "low"},
               "allowed_tools": [], "rules": []}
    original = SessionPolicySnapshot.from_mapping(payload, binding=binding)
    row = {"model_config": {"native_session_policy": {
        "payload": original.to_mapping(), "owner_id": binding["owner_id"],
        "profile_id": binding["profile_id"],
    }}}
    restored = server._restore_session_policy(row, "persisted-session", "default")
    assert restored.instructions == "FROZEN-REVISION-1"
    assert restored.allowed_tools == ()
    assert restored.binding.runtime_generation == server._SESSION_POLICY_RUNTIME_GENERATION
    with pytest.raises(ValueError, match="profile"):
        server._restore_session_policy(row, "persisted-session", "other-profile")


def test_native_builder_rejects_stale_generation_and_cross_profile_before_runtime(monkeypatch):
    from tui_gateway import server
    from agent.session_policy import SessionPolicySnapshot

    monkeypatch.setattr(server, "_current_profile_name", lambda: "default")
    payload = {"version": 1, "source": {"agent_id": "fixture", "revision": 1},
               "instructions": "Fixture", "model": {"provider": "openrouter", "model": "fixture", "reasoning": "low"},
               "allowed_tools": [], "rules": []}
    for profile, generation, expected in (
        ("default", "old-process", "generation"),
        ("other-profile", server._SESSION_POLICY_RUNTIME_GENERATION, "cross-profile"),
    ):
        policy = SessionPolicySnapshot.from_mapping(payload, binding={
            "session_id": "fixture-session", "owner_id": "fixture-owner",
            "profile_id": profile, "runtime_generation": generation,
        })
        with pytest.raises(ValueError, match=expected):
            server._make_agent("ui-session", "fixture-session", session_policy=policy)


def test_native_policy_ask_uses_gateway_once_without_saved_grant():
    from tools.approval import (
        disable_session_yolo, enable_session_yolo,
        register_gateway_notify, request_mandatory_policy_approval,
        reset_current_session_key, resolve_gateway_approval,
        set_current_session_key, unregister_gateway_notify,
    )

    key = "fixture-policy-approval"
    choices = iter(["once", "deny", "session"])
    requests = []

    def notify(data):
        requests.append(data)
        assert data["allow_session"] is False
        assert data["allow_permanent"] is False
        assert data["choices"] == ["once", "deny"]
        resolve_gateway_approval(key, next(choices), request_id=data["request_id"])

    token = set_current_session_key(key)
    register_gateway_notify(key, notify)
    enable_session_yolo(key)
    try:
        assert request_mandatory_policy_approval("read_file", {"path": "inside"}, session_key=key)
        assert not request_mandatory_policy_approval("read_file", {"path": "inside"}, session_key=key)
        assert not request_mandatory_policy_approval("read_file", {"path": "inside"}, session_key=key)
        assert len(requests) == 3
        assert len({request["request_id"] for request in requests}) == 3
    finally:
        disable_session_yolo(key)
        unregister_gateway_notify(key)
        reset_current_session_key(token)


def test_native_policy_ask_without_gateway_listener_fails_closed():
    from tools.approval import request_mandatory_policy_approval

    assert not request_mandatory_policy_approval(
        "terminal", {"command": "printf fixture"}, session_key="absent-listener"
    )
