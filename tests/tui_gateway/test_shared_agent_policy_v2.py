"""Gateway-facing acceptance tests for the SA-v1 revision-2 policy lifecycle."""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.session_policy import (
    SessionPolicySnapshot,
    UnsupportedPolicy,
    register_session_policy_provider,
)


def _payload(root: Path, *, instructions="V2-INSTRUCTIONS", reasoning="high"):
    return {
        "version": 2,
        "source": {"agent_id": "fixture-v2", "revision": 4, "reference": "projection-v2"},
        "instructions": instructions,
        "model": {"provider": "openrouter", "model": "fixture-model", "reasoning": reasoning},
        "allowed_tools": ["read_file"],
        "tool_effects": {},
        "paths": {"root": str(root), "boundary": [str(root)], "external": "deny", "protected": []},
        "rules": [{"tool": "read_file", "argument": "path", "pattern": "*", "effect": "allow"}],
        "taint_gate": {"sources": ["read_file"], "gated": []},
        "launch": {"kind": "interactive", "cwd": str(root)},
    }


def _binding(session_id="lineage-root"):
    return {"session_id": session_id, "owner_id": "owner-v2", "profile_id": "default", "runtime_generation": "generation-v2"}


class Provider:
    def __init__(self, root: Path):
        self.root = root
        self.resolve_calls = []
        self.restore_calls = []
        self.check_calls = []
        self.resolve_error = None
        self.restore_error = None
        self.check_error = None

    def resolve(self, selection, **context):
        self.resolve_calls.append((selection, context))
        if self.resolve_error:
            raise self.resolve_error
        return _payload(self.root), "owner-v2"

    def restore(self, reference, **context):
        self.restore_calls.append((reference, context))
        if self.restore_error:
            raise self.restore_error
        return _payload(self.root, instructions="SERVER-AUTHORITATIVE"), "owner-v2"

    def check(self, reference, **context):
        self.check_calls.append((reference, context))
        if self.check_error:
            raise self.check_error


def _install_session(server, snapshot, sid="v2-session"):
    server._sessions[sid] = {
        "session_policy": snapshot,
        "session_key": snapshot.binding.session_id,
        "profile_home": None,
        "history_lock": __import__("threading").Lock(),
        "history": [],
        "running": False,
        "agent": None,
        "cwd": snapshot.launch.cwd,
    }
    return sid


def test_n1_ac7_blocks_skill_dispatch_completion_and_replay(tmp_path, monkeypatch):
    """N1-AC7: no gateway skill surface can inject skill content into v2."""
    from tui_gateway import server

    snapshot = SessionPolicySnapshot.from_mapping(_payload(tmp_path), binding={
        **_binding(), "runtime_generation": server._SESSION_POLICY_RUNTIME_GENERATION,
    })
    sid = _install_session(server, snapshot)
    monkeypatch.setattr("agent.skill_commands.get_skill_commands", lambda: {"/fixture-skill": {"name": "fixture-skill"}})
    monkeypatch.setattr("agent.skill_commands.scan_skill_commands", lambda: {"/fixture-skill": {"name": "fixture-skill"}})
    monkeypatch.setattr("agent.skill_commands.build_skill_invocation_message", lambda *a, **k: "SECRET SKILL BODY")
    try:
        dispatched = server.handle_request({"id": "d", "method": "command.dispatch", "params": {"session_id": sid, "name": "fixture-skill", "arg": ""}})
        completed = server.handle_request({"id": "c", "method": "complete.slash", "params": {"session_id": sid, "text": "/fixture"}})
        assert dispatched["error"]["message"] == "unsupported_policy:skill_not_allowed"
        assert all(item.get("kind") != "skill" for item in completed["result"]["items"])
        assert server._expand_skill_invocation_for_replay("/fixture-skill", snapshot.binding.session_id) == "/fixture-skill"
    finally:
        server._sessions.pop(sid, None)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (UnsupportedPolicy("projection_revoked"), "unsupported_policy:projection_revoked"),
        (RuntimeError("sensitive provider details"), "unsupported_policy:provider_failed"),
    ],
)
def test_n1_ac9_surfaces_only_bounded_provider_codes(tmp_path, monkeypatch, error, expected):
    """N1-AC9: provider exceptions cannot leak through the session.create error."""
    from tui_gateway import server

    provider = Provider(tmp_path)
    provider.resolve_error = error
    dispose = register_session_policy_provider(provider)
    monkeypatch.setattr(server, "_schedule_agent_build", lambda _sid: None)
    try:
        response = server.handle_request({"id": "create", "method": "session.create", "params": {"policy_selection": "fixture"}})
        assert response["error"]["message"] == expected
    finally:
        dispose()


def test_n1_ac9_builder_binding_failure_uses_closed_code(tmp_path, monkeypatch):
    from tui_gateway import server

    snapshot = SessionPolicySnapshot.from_mapping(_payload(tmp_path), binding={
        **_binding(), "runtime_generation": server._SESSION_POLICY_RUNTIME_GENERATION,
    })
    monkeypatch.setattr(server, "_current_profile_name", lambda: "default")
    with pytest.raises(UnsupportedPolicy) as exc:
        server._make_agent(
            "ui-session",
            "different-lineage",
            session_policy=snapshot,
        )
    assert exc.value.code == "binding_mismatch"


def test_n1_ac10_passes_realpath_cwd_only_when_explicit(tmp_path, monkeypatch):
    """N1-AC10: implicit launch cwd is not authority sent to the provider."""
    from tui_gateway import server

    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    provider = Provider(real)
    dispose = register_session_policy_provider(provider)
    monkeypatch.setattr(server, "_schedule_agent_build", lambda _sid: None)
    made = []
    try:
        for params in ({"policy_selection": "fixture"}, {"policy_selection": "fixture", "cwd": str(alias)}):
            response = server.handle_request({"id": "create", "method": "session.create", "params": params})
            assert "error" not in response, response
            made.append(response["result"]["session_id"])
        assert provider.resolve_calls[0][1]["cwd"] is None
        assert provider.resolve_calls[1][1]["cwd"] == str(real)
    finally:
        dispose()
        for sid in made:
            server._sessions.pop(sid, None)


def test_n1_ac11_nullable_fields_and_runtime_mismatch(tmp_path, monkeypatch):
    """N1-AC11: null prompt/reasoning inherit, while auth fallback is refused."""
    from tui_gateway import server

    payload = _payload(tmp_path, instructions=None, reasoning=None)
    snapshot = SessionPolicySnapshot.from_mapping(payload, binding={
        **_binding(), "runtime_generation": server._SESSION_POLICY_RUNTIME_GENERATION,
    })
    assert snapshot.instructions is None
    assert snapshot.model.reasoning is None

    bad = _payload(tmp_path, reasoning="definitely-invalid")
    with pytest.raises(UnsupportedPolicy) as exc:
        SessionPolicySnapshot.from_mapping(bad, binding=_binding())
    assert exc.value.code == "reasoning_invalid"

    monkeypatch.setattr(server, "_current_profile_name", lambda: "default")
    monkeypatch.setattr(server, "_resolve_runtime_with_fallback", lambda _kw: SimpleNamespace(
        runtime={"provider": "other", "base_url": "http://127.0.0.1:9", "api_key": "x"},
        used_fallback=True,
        selected_model="fallback-model",
    ))
    with pytest.raises(UnsupportedPolicy) as exc:
        server._make_agent("sid", "lineage-root", session_policy=snapshot)
    assert exc.value.code == "provider_runtime_mismatch"


def test_n1_ac13_restore_uses_provider_copy_and_turn_gate_rechecks(tmp_path, monkeypatch):
    """N1-AC13: disk is non-authoritative and revocation is checked each turn."""
    from tui_gateway import server

    provider = Provider(tmp_path)
    dispose = register_session_policy_provider(provider)
    tampered = _payload(tmp_path, instructions="TAMPERED-DISK-COPY")
    row = {"model_config": {"native_session_policy": {
        "payload": tampered,
        "owner_id": "owner-v2",
        "profile_id": "default",
        "lineage_root": "lineage-root",
        "tainted": True,
    }}}
    try:
        restored = server._restore_session_policy(row, "lineage-root", "default")
        assert restored.instructions == "SERVER-AUTHORITATIVE"
        assert restored.restored_tainted is True
        assert provider.restore_calls == [("projection-v2", {"lineage_root": "lineage-root", "profile_id": "default"})]
        session = {"session_policy": restored, "session_key": "lineage-root"}
        server.session_policy_turn_gate(session)
        assert provider.check_calls[-1][0] == "projection-v2"
        provider.check_error = UnsupportedPolicy("projection_revoked")
        with pytest.raises(UnsupportedPolicy) as exc:
            server.session_policy_turn_gate(session)
        assert exc.value.code == "projection_revoked"
        provider.restore_error = RuntimeError("sensitive provider details")
        with pytest.raises(UnsupportedPolicy) as exc:
            server._restore_session_policy(row, "lineage-root", "default")
        assert exc.value.code == "provider_failed"
    finally:
        dispose()


def test_n1_ac14_taint_is_part_of_v2_persistence_entry(tmp_path):
    from tui_gateway import server

    snapshot = SessionPolicySnapshot.from_mapping(_payload(tmp_path), binding={
        **_binding(), "runtime_generation": server._SESSION_POLICY_RUNTIME_GENERATION,
    })
    entry = server._native_session_policy_entry(snapshot, tainted=True)
    assert entry["lineage_root"] == "lineage-root"
    assert entry["tainted"] is True


def test_n1_ac15_v2_batches_execute_in_model_order(tmp_path):
    """N1-AC15: a v2 batch never enters the concurrent executor."""
    from run_agent import AIAgent

    snapshot = SessionPolicySnapshot.from_mapping(_payload(tmp_path), binding=_binding())
    seen = []
    agent = object.__new__(AIAgent)
    agent.session_policy = snapshot
    agent._executing_tools = False
    agent._execute_tool_calls_sequential = lambda msg, *_a: seen.extend(tc.function.name for tc in msg.tool_calls)
    agent._execute_tool_calls_concurrent = lambda *_a: seen.append("CONCURRENT")
    calls = [SimpleNamespace(function=SimpleNamespace(name=name)) for name in ("read_file", "read_file")]
    agent._execute_tool_calls(SimpleNamespace(tool_calls=calls), [], "fixture")
    assert seen == ["read_file", "read_file"]
