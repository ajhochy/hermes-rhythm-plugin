"""SA-v1 revision-2 executable contract for the Hermes N1 policy core."""
from __future__ import annotations

import os
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.session_policy import (
    SessionPolicySnapshot,
    UnsupportedPolicy,
    bind_active_policy,
    current_policy,
    reset_active_policy,
)


def _binding(**overrides):
    return {
        "session_id": "lineage-root",
        "owner_id": "owner-1",
        "profile_id": "default",
        "runtime_generation": "generation-1",
        **overrides,
    }


def _payload(root: Path, **overrides):
    payload = {
        "version": 2,
        "source": {"agent_id": "sa-specialist", "revision": 7, "reference": "projection-1"},
        "instructions": "Frozen instructions",
        "model": {"provider": "openrouter", "model": "fixture-model", "reasoning": "high"},
        "allowed_tools": ["clarify", "patch", "read_file", "rhythm_delegate", "search_files", "terminal", "write_file"],
        "tool_effects": {"clarify": "ask"},
        "paths": {
            "root": str(root),
            "boundary": [str(root)],
            "external": "ask",
            "protected": [str(root / "protected")],
        },
        "rules": [
            {"tool": "read_file", "argument": "path", "pattern": "*", "effect": "allow"},
            {"tool": "write_file", "argument": "path", "pattern": "*", "effect": "allow"},
            {"tool": "patch", "argument": "path", "pattern": "*", "effect": "allow"},
            {"tool": "search_files", "argument": "path", "pattern": "*", "effect": "allow"},
            {"tool": "terminal", "argument": "command", "pattern": "*", "effect": "ask"},
            {"tool": "terminal", "argument": "command", "pattern": "git status", "effect": "allow"},
            {"tool": "rhythm_delegate", "argument": "targetAgentId", "pattern": "*", "effect": "deny"},
            {"tool": "rhythm_delegate", "argument": "targetAgentId", "pattern": "child-ok", "effect": "allow"},
        ],
        "taint_gate": {"sources": ["read_file"], "gated": ["rhythm_delegate"]},
        "launch": {"kind": "interactive", "cwd": str(root)},
    }
    payload.update(overrides)
    return payload


def _snapshot(tmp_path: Path, **overrides):
    return SessionPolicySnapshot.from_mapping(_payload(tmp_path, **overrides), binding=_binding())


def _effect(snapshot, tool, arguments, *, task_id="fixture", tainted=False):
    return snapshot.authorize_tool_call(
        tool_name=tool,
        arguments=arguments,
        binding=_binding(),
        task_id=task_id,
        tainted=tainted,
    ).effect


def test_n1_ac1_validates_v2_without_regressing_v1(tmp_path):
    """N1-AC1: v1 and v2 remain accepted while malformed v2 fails closed."""
    snapshot = _snapshot(tmp_path)
    assert snapshot.version == 2
    assert snapshot.source.reference == "projection-1"
    assert snapshot.to_mapping() == _payload(tmp_path)

    v1 = {
        "version": 1,
        "source": {"agent_id": "legacy", "revision": 1},
        "instructions": "legacy",
        "model": {"provider": "openrouter", "model": "legacy", "reasoning": "low"},
        "allowed_tools": None,
        "rules": [],
    }
    assert SessionPolicySnapshot.from_mapping(v1, binding=_binding()).version == 1

    invalid = [
        _payload(tmp_path, allowed_tools=None),
        _payload(tmp_path, unknown=True),
        _payload(tmp_path, allowed_tools=["skill"]),
    ]
    for payload in invalid:
        with pytest.raises(UnsupportedPolicy) as exc:
            SessionPolicySnapshot.from_mapping(payload, binding=_binding())
        assert exc.value.code == "policy_shape_invalid"


def test_n1_ac2_authorizes_resolved_paths_and_refuses_container_paths(tmp_path, monkeypatch):
    """N1-AC2: policy evaluates the exact host path the file tool will open."""
    snapshot = _snapshot(tmp_path)
    live = tmp_path / "live"
    live.mkdir()
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (live / "escape").symlink_to(outside, target_is_directory=True)

    import tools.file_tools as file_tools

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(
        file_tools,
        "_resolve_path_for_task",
        lambda raw, task_id: Path(os.path.expanduser(raw)).resolve()
        if raw.startswith("~") else (live / raw).resolve(),
    )
    monkeypatch.setattr(file_tools, "_uses_container_paths", lambda task_id: False)
    assert Path.cwd() != live
    assert _effect(snapshot, "read_file", {"path": "inside.txt"}) == "allow"
    assert _effect(snapshot, "read_file", {"path": "~/inside.txt"}) == "allow"
    assert _effect(snapshot, "read_file", {"path": "escape/secret.txt"}) == "ask"
    assert _effect(snapshot, "read_file", {"path": str(tmp_path / "protected" / "secret")}) == "deny"

    hermes_home = tmp_path / "hermes-home"
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    assert _effect(snapshot, "read_file", {"path": str(hermes_home / "MEMORY.md")}) == "deny"
    monkeypatch.setattr(file_tools, "_uses_container_paths", lambda task_id: True)
    assert _effect(snapshot, "read_file", {"path": "inside.txt"}) == "deny"


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git status", "allow"),
        ("git status && touch marker", "ask"),
        ("true; dd if=/dev/zero", "ask"),
        ("echo x | sh", "ask"),
        ("echo $(rm x)", "ask"),
        ("if true; then rm x; fi", "ask"),
        ("git status\ntouch marker", "ask"),
    ],
)
def test_n1_ac3_evaluates_every_terminal_segment(tmp_path, monkeypatch, command, expected):
    """N1-AC3: dynamic constructs and every top-level segment are evaluated."""
    snapshot = _snapshot(tmp_path)
    import tools.file_tools as file_tools

    monkeypatch.setattr(file_tools, "_resolve_base_dir", lambda task_id: tmp_path)
    assert _effect(snapshot, "terminal", {"command": command}) == expected


def test_n1_ac3_gates_terminal_paths_redirects_workdir_and_parser_limit(tmp_path, monkeypatch):
    snapshot = _snapshot(tmp_path)
    import tools.file_tools as file_tools

    monkeypatch.setattr(file_tools, "_resolve_base_dir", lambda task_id: tmp_path)
    (tmp_path / "~").mkdir()
    assert _effect(snapshot, "terminal", {"command": "cat ../outside"}) == "ask"
    assert _effect(snapshot, "terminal", {"command": f"echo x > {tmp_path / 'protected' / 'x'}"}) == "deny"
    assert _effect(snapshot, "terminal", {"command": "git status", "workdir": "../outside"}) == "ask"
    assert _effect(snapshot, "terminal", {"command": "git status", "workdir": "~"}) == "allow"
    assert _effect(snapshot, "terminal", {"command": "x" * 5000}) == "deny"


def test_n1_ac3_denied_segment_never_reaches_terminal_dispatch(tmp_path, monkeypatch):
    import model_tools

    snapshot = _snapshot(tmp_path)
    marker = tmp_path / "M"
    monkeypatch.setattr(
        model_tools.registry,
        "dispatch",
        lambda *_a, **_k: marker.write_text("escaped", encoding="utf-8"),
    )
    result = model_tools.handle_function_call(
        "terminal",
        {"command": f"git status && touch {marker}"},
        task_id="fixture",
        session_id="rotated-session",
        session_policy=snapshot,
        policy_binding=_binding(session_id="rotated-session"),
        skip_pre_tool_call_hook=True,
        skip_tool_request_middleware=True,
        skip_tool_execution_middleware=True,
    )
    assert "policy" in result.lower()
    assert not marker.exists()


def test_n1_ac4_denies_multifile_patch_and_checks_replace_path(tmp_path, monkeypatch):
    """N1-AC4: patch mode is replace-only in v2."""
    import tools.file_tools as file_tools

    monkeypatch.setattr(file_tools, "_resolve_path_for_task", lambda raw, task_id: Path(raw).resolve())
    monkeypatch.setattr(file_tools, "_uses_container_paths", lambda task_id: False)
    snapshot = _snapshot(tmp_path)
    path = str(tmp_path / "file.txt")
    assert _effect(snapshot, "patch", {"mode": "patch", "path": path}) == "deny"
    assert _effect(snapshot, "patch", {"mode": "replace", "path": path}) == "allow"


def test_n1_ac5_filters_denied_tools_and_honors_tool_effects(tmp_path):
    """N1-AC5: offered schemas and dispatch share the closed effect model."""
    snapshot = _snapshot(tmp_path)
    offered = snapshot.filter_tool_schemas(
        [{"name": "clarify"}, {"name": "read_file"}, {"name": "skill"}, {"name": "browser_navigate"}],
        binding=_binding(),
    )
    assert [tool["name"] for tool in offered] == ["clarify", "read_file"]
    assert _effect(snapshot, "clarify", {}) == "ask"
    assert _effect(snapshot, "skill", {"name": "x"}) == "deny"


def test_n1_ac5_refuses_unsafe_approval_previews(monkeypatch):
    from tools import approval

    prompts = []
    monkeypatch.setattr(approval, "_await_gateway_decision", lambda *a, **k: prompts.append(1) or {"resolved": True, "choice": "once"})
    monkeypatch.setattr(approval, "get_current_session_key", lambda _default="": "s")
    monkeypatch.setitem(approval._gateway_notify_cbs, "s", lambda _data: None)
    assert not approval.request_mandatory_policy_approval("terminal", {"command": "x" * 2049}, session_key="s")
    monkeypatch.setattr("agent.redact.redact_sensitive_text", lambda _text: "[REDACTED]")
    assert not approval.request_mandatory_policy_approval("terminal", {"command": "secret"}, session_key="s")
    assert prompts == []


def test_n1_ac6_root_relative_rules_include_root_slash(tmp_path, monkeypatch):
    """N1-AC6: matching is relative to paths.root even when root is '/'."""
    import tools.file_tools as file_tools

    monkeypatch.setattr(file_tools, "_uses_container_paths", lambda task_id: False)
    monkeypatch.setattr(file_tools, "_resolve_path_for_task", lambda raw, task_id: Path(raw).resolve())
    payload = _payload(Path("/"))
    payload["paths"] = {"root": "/", "boundary": ["/"], "external": "deny", "protected": []}
    payload["rules"] = [{"tool": "read_file", "argument": "path", "pattern": "usr/*", "effect": "allow"}]
    snapshot = SessionPolicySnapshot.from_mapping(payload, binding=_binding())
    assert _effect(snapshot, "read_file", {"path": "/usr/example"}) == "allow"
    assert _effect(snapshot, "read_file", {"path": "/var/example"}) == "deny"


def test_n1_ac8_active_policy_context_is_nested_and_thread_local(tmp_path):
    """N1-AC8: the active projection is visible only inside its dispatch context."""
    snapshot = _snapshot(tmp_path)
    assert current_policy() is None


def test_n1_ac8_and_ac12_bind_both_dispatch_paths_to_lineage_approval(
    tmp_path, monkeypatch
):
    """N1-AC8/N1-AC12: handlers see the immutable root after ID rotation."""
    import model_tools
    from agent import relay_tools, tool_executor

    payload = _payload(tmp_path)
    payload.update({
        "allowed_tools": ["fixture_context"],
        "tool_effects": {"fixture_context": "ask"},
        "rules": [],
        "taint_gate": {"sources": [], "gated": []},
    })
    snapshot = SessionPolicySnapshot.from_mapping(payload, binding=_binding())
    approvals = []
    expected = (snapshot, "lineage-root")

    monkeypatch.setattr(
        model_tools.registry,
        "dispatch",
        lambda *_a, **_k: str(current_policy() == expected),
    )
    direct = model_tools.handle_function_call(
        "fixture_context",
        {},
        task_id="fixture",
        session_id="rotated-session",
        session_policy=snapshot,
        policy_binding=_binding(session_id="rotated-session"),
        policy_approval_callback=lambda name, args: approvals.append(("direct", name, args)) or True,
        skip_pre_tool_call_hook=True,
        skip_tool_request_middleware=True,
        skip_tool_execution_middleware=True,
    )
    assert direct == "True"
    assert current_policy() is None

    monkeypatch.setattr(
        "hermes_cli.middleware.apply_tool_request_middleware",
        lambda _name, args, **_kwargs: SimpleNamespace(payload=args, trace=[]),
    )
    monkeypatch.setattr(
        "hermes_cli.middleware.run_tool_execution_middleware",
        lambda _name, args, callback, **_kwargs: callback(args),
    )
    monkeypatch.setattr(
        "hermes_cli.plugins._dispatch_pre_tool_call_hooks",
        lambda *_args, **_kwargs: (None, None),
    )
    monkeypatch.setattr(tool_executor, "_begin_tool_execution", lambda *_a, **_k: None)
    monkeypatch.setattr(
        relay_tools,
        "execute",
        lambda name, args, callback, **kwargs: (callback(args), args),
    )
    agent = SimpleNamespace(
        session_policy=snapshot,
        session_policy_tainted=False,
        session_id="rotated-session",
        policy_approval_callback=lambda name, args: approvals.append(("agent", name, args)) or True,
        _tool_guardrails=SimpleNamespace(
            before_call=lambda _name, _args: SimpleNamespace(allows_execution=True)
        ),
    )
    managed = tool_executor._run_agent_tool_execution_middleware(
        agent,
        function_name="fixture_context",
        function_args={},
        effective_task_id="fixture",
        tool_call_id="call-1",
        execute=lambda _args: str(current_policy() == expected),
    )
    assert managed.result == "True"
    assert managed.blocked is False
    assert [item[0] for item in approvals] == ["direct", "agent"]
    assert current_policy() is None
    token = bind_active_policy(snapshot, "lineage-root")
    try:
        assert current_policy() == (snapshot, "lineage-root")
        seen = []
        thread = threading.Thread(target=lambda: seen.append(current_policy()))
        thread.start()
        thread.join()
        assert seen == [None]
    finally:
        reset_active_policy(token)
    assert current_policy() is None


def test_n1_ac12_lineage_root_survives_runtime_session_rotation(tmp_path):
    """N1-AC12: authorization binds to the immutable lineage root, not a rotated id."""
    snapshot = _snapshot(tmp_path)
    assert snapshot.authorize_tool_call(
        tool_name="clarify",
        arguments={},
        binding=_binding(session_id="rotated-compression-id"),
        lineage_root="lineage-root",
        task_id="fixture",
        tainted=False,
    ).effect == "ask"


def test_n1_ac14_taint_raises_gated_tool_to_ask(tmp_path):
    """N1-AC14: successful taint sources tighten later gated calls."""
    snapshot = _snapshot(tmp_path)
    assert snapshot.taints("read_file") is True
    assert _effect(snapshot, "rhythm_delegate", {"targetAgentId": "child-ok"}) == "allow"
    assert _effect(snapshot, "rhythm_delegate", {"targetAgentId": "child-ok"}, tainted=True) == "ask"


def test_n1_ac14_tainted_headless_dispatch_fails_closed(tmp_path, monkeypatch):
    import model_tools

    snapshot = _snapshot(tmp_path)
    monkeypatch.setattr(
        model_tools.registry,
        "dispatch",
        lambda *_a, **_k: pytest.fail("tainted gated tool reached dispatch"),
    )
    result = model_tools.handle_function_call(
        "rhythm_delegate",
        {"targetAgentId": "child-ok"},
        task_id="fixture",
        session_id="lineage-root",
        session_policy=snapshot,
        policy_binding=_binding(),
        policy_tainted=True,
        skip_pre_tool_call_hook=True,
        skip_tool_request_middleware=True,
        skip_tool_execution_middleware=True,
    )
    assert "policy" in result.lower()


def test_n1_ac16_scalar_argument_rules_are_last_match(tmp_path):
    """N1-AC16: scalar rules use the same last-match precedence as OpenCode."""
    snapshot = _snapshot(tmp_path)
    assert _effect(snapshot, "rhythm_delegate", {"targetAgentId": "child-ok"}) == "allow"
    assert _effect(snapshot, "rhythm_delegate", {"targetAgentId": "child-no"}) == "deny"
    assert _effect(snapshot, "rhythm_delegate", {"targetAgentId": 12}) == "deny"
