"""Executable N0 contract for a generic, frozen native session policy.

The public seam proposed by this contract is ``agent.session_policy`` with
``SessionPolicySnapshot.from_mapping(payload, binding=trusted_binding)``. The tests intentionally call
that runtime seam; they do not inspect source text. A missing module is a
product RED, while a missing transitive dependency is allowed to surface as an
environment/collection error instead of being mislabeled as missing wiring.
"""
from __future__ import annotations

import importlib
from dataclasses import FrozenInstanceError
from typing import Any

import pytest


def _snapshot_type():
    try:
        module = importlib.import_module("agent.session_policy")
    except ModuleNotFoundError as exc:
        if exc.name == "agent.session_policy":
            pytest.fail(
                "PRODUCT RED: N0 generic session-policy runtime module is not wired",
                pytrace=False,
            )
        raise
    snapshot_type = getattr(module, "SessionPolicySnapshot", None)
    assert snapshot_type is not None, (
        "PRODUCT RED: agent.session_policy must expose SessionPolicySnapshot"
    )
    return snapshot_type


def _payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": 1,
        "source": {"agent_id": "shared-agent-n0-specialist", "revision": 7},
        "instructions": "FROZEN-N0-INSTRUCTION-7",
        "model": {"provider": "openai-compatible", "model": "fixture-model", "reasoning": "low"},
        "allowed_tools": ["terminal", "read_file"],
        "rules": [],
    }
    payload.update(overrides)
    return payload


def _binding(**overrides: str) -> dict[str, str]:
    return {
        "session_id": "native-session-A",
        "owner_id": "owner-A",
        "profile_id": "profile-A",
        "runtime_generation": "generation-A",
        **overrides,
    }


def _decision(snapshot, tool: str, arguments: dict[str, Any], **kwargs):
    decision = snapshot.authorize_tool_call(
        tool_name=tool,
        arguments=arguments,
        binding=kwargs.pop("binding", _binding()),
        **kwargs,
    )
    return decision


def test_n0_ac2_empty_allowlist_is_deny_all_and_none_inherits():
    """Catches [] being normalized to None and inheriting native tools."""
    snapshot_type = _snapshot_type()
    empty = snapshot_type.from_mapping(_payload(allowed_tools=[]), binding=_binding())
    inherited = snapshot_type.from_mapping(_payload(allowed_tools=None), binding=_binding())
    native = [{"name": "terminal"}, {"name": "read_file"}]

    assert empty.filter_tool_schemas(native, binding=_binding()) == []
    assert {tool["name"] for tool in inherited.filter_tool_schemas(native, binding=_binding())} == {
        "terminal",
        "read_file",
    }
    denied = _decision(empty, "terminal", {"command": "touch forbidden"})
    assert denied.effect == "deny"


def test_n0_ac3_allowlist_and_ordered_argument_rules_are_enforced():
    """Catches unordered/globally merged rules that accidentally allow a denied command."""
    snapshot_type = _snapshot_type()
    rules = [
        {"tool": "terminal", "argument": "command", "pattern": "*", "effect": "deny"},
        {
            "tool": "terminal",
            "argument": "command",
            "pattern": "printf SAFE-N0",
            "effect": "allow",
        },
    ]
    snapshot = snapshot_type.from_mapping(_payload(allowed_tools=["terminal", "read_file"], rules=rules), binding=_binding())
    assert snapshot.filter_tool_schemas(
        [{"name": "terminal"}, {"name": "read_file"}, {"name": "browser"}],
        binding=_binding(),
    ) == [{"name": "terminal"}, {"name": "read_file"}]
    assert _decision(snapshot, "terminal", {"command": "printf SAFE-N0"}).effect == "allow"
    assert _decision(snapshot, "terminal", {"command": "touch DENIED-N0"}).effect == "deny"

    reversed_snapshot = snapshot_type.from_mapping(_payload(rules=list(reversed(rules))), binding=_binding())
    assert _decision(reversed_snapshot, "terminal", {"command": "printf SAFE-N0"}).effect == "deny"


def test_n0_ac3_rhythm_scalar_wildcard_parity_for_terminal():
    """Rhythm's scalar wildcard has optional trailing args and literal brackets."""
    snapshot_type = _snapshot_type()
    cases = (
        ("ls *", "ls", "pwd"),
        ("echo [x]", "echo [x]", "echo x"),
        (r"dir\file", "dir/file", "dir-other-file"),
        ("alpha*omega", "alpha\nomega", "alpha\nother"),
    )
    for pattern, matching, nonmatching in cases:
        snapshot = snapshot_type.from_mapping(
            _payload(rules=[{"tool": "terminal", "argument": "command",
                             "pattern": pattern, "effect": "allow"}]),
            binding=_binding(),
        )
        assert _decision(snapshot, "terminal", {"command": matching}).effect == "allow"
        assert _decision(snapshot, "terminal", {"command": nonmatching}).effect == "deny"
        if pattern == "ls *":
            assert _decision(snapshot, "terminal", {"command": "ls -la"}).effect == "allow"


def test_n0_ac3_global_path_wildcard_last_deny_and_symlink_confinement(tmp_path):
    """A final '*' denies every absolute path while realpath blocks symlink escape."""
    snapshot_type = _snapshot_type()
    safe = tmp_path / "safe"
    safe.mkdir()
    inside = safe / "inside.txt"
    inside.write_text("safe")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    escape = safe / "escape.txt"
    escape.symlink_to(outside)
    anchored = {"tool": "read_file", "argument": "path",
                "pattern": str(safe / "*"), "effect": "allow"}
    global_deny = {"tool": "read_file", "argument": "path",
                   "pattern": "*", "effect": "deny"}
    final_deny = snapshot_type.from_mapping(
        _payload(rules=[anchored, global_deny]), binding=_binding())
    assert _decision(final_deny, "read_file", {"path": str(inside)}).effect == "deny"
    final_allow = snapshot_type.from_mapping(
        _payload(rules=[global_deny, anchored]), binding=_binding())
    assert _decision(final_allow, "read_file", {"path": str(inside)}).effect == "allow"
    assert _decision(final_allow, "read_file", {"path": str(escape)}).effect == "deny"


def test_n0_ac3_ambiguous_path_globs_refuse_before_session_start(tmp_path):
    """Unprovable path globs fail closed instead of lexical matching."""
    snapshot_type = _snapshot_type()
    for pattern in (
        "relative/*", str(tmp_path / "middle*" / "file.txt"),
        str(tmp_path / "file?.txt"), str(tmp_path / "safe" / "**"),
    ):
        with pytest.raises(Exception, match="unsupported|invalid|pattern"):
            snapshot_type.from_mapping(
                _payload(rules=[{"tool": "read_file", "argument": "path",
                                 "pattern": pattern, "effect": "allow"}]),
                binding=_binding(),
            )


def test_n0_path_rule_rejects_existing_symlink_anchor(tmp_path):
    """A symlinked rule anchor can be retargeted after selection; refuse it."""
    snapshot_type = _snapshot_type()
    first = tmp_path / "first"
    first.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(first, target_is_directory=True)
    with pytest.raises(Exception, match="unsupported|invalid|symlink|pattern"):
        snapshot_type.from_mapping(
            _payload(rules=[{"tool": "read_file", "argument": "path",
                             "pattern": str(alias / "*"), "effect": "allow"}]),
            binding=_binding(),
        )
    file_alias = tmp_path / "file-alias.txt"
    file_alias.symlink_to(first / "target.txt")
    with pytest.raises(Exception, match="unsupported|invalid|symlink|pattern"):
        snapshot_type.from_mapping(
            _payload(rules=[{"tool": "read_file", "argument": "path",
                             "pattern": str(file_alias), "effect": "allow"}]),
            binding=_binding(),
        )


def test_n0_path_rule_retarget_after_snapshot_cannot_move_authority(tmp_path):
    """A frozen rule cannot follow an anchor replaced with a symlink."""
    snapshot_type = _snapshot_type()
    anchor = tmp_path / "anchor"
    anchor.mkdir()
    original = anchor / "original.txt"
    original.write_text("original")
    outside = tmp_path / "outside"
    outside.mkdir()
    moved = outside / "moved.txt"
    moved.write_text("moved")
    snapshot = snapshot_type.from_mapping(
        _payload(rules=[{"tool": "read_file", "argument": "path",
                         "pattern": str(anchor / "*"), "effect": "allow"}]),
        binding=_binding(),
    )
    assert _decision(snapshot, "read_file", {"path": str(original)}).effect == "allow"
    assert snapshot.to_mapping()["rules"][0]["pattern"] == str(anchor / "*")

    anchor.rename(tmp_path / "old-anchor")
    anchor.symlink_to(outside, target_is_directory=True)
    try:
        moved_decision = _decision(snapshot, "read_file", {"path": str(anchor / "moved.txt")})
    except Exception as exc:
        assert "unsupported" in str(exc).lower() or "symlink" in str(exc).lower()
    else:
        assert moved_decision.effect == "deny"
    # Durable replay of the raw rule must also fail closed when its anchor is
    # now a symlink, instead of silently granting the new target on resume.
    with pytest.raises(Exception, match="unsupported|invalid|symlink|pattern"):
        snapshot_type.from_mapping(snapshot.to_mapping(), binding=_binding())


def test_n0_command_trailing_newline_is_deliberately_stricter_than_rhythm():
    """JS ``$`` can match before a final newline; N0 refuses that broadening."""
    snapshot_type = _snapshot_type()
    snapshot = snapshot_type.from_mapping(
        _payload(rules=[{"tool": "terminal", "argument": "command",
                         "pattern": "echo ok", "effect": "allow"}]),
        binding=_binding(),
    )
    assert _decision(snapshot, "terminal", {"command": "echo ok\n"}).effect == "deny"


def test_n0_ac4_ask_remains_an_approval_decision():
    """Catches ask being flattened to allow or deny before native approval can handle it."""
    snapshot_type = _snapshot_type()
    snapshot = snapshot_type.from_mapping(
        _payload(
            rules=[
                {"tool": "read_file", "argument": "path", "pattern": "*", "effect": "ask"}
            ]
        )
    , binding=_binding())
    decision = _decision(snapshot, "read_file", {"path": "inside.txt"})
    assert decision.effect == "ask"
    assert decision.requires_approval is True


def test_n0_ac5_fail_closed_and_final_arguments_are_rechecked():
    """Catches fail-soft evaluator errors and plugin-mutated arguments bypassing the policy."""
    snapshot_type = _snapshot_type()
    snapshot = snapshot_type.from_mapping(
        _payload(
            rules=[
                {"tool": "terminal", "argument": "command", "pattern": "*", "effect": "deny"},
                {
                    "tool": "terminal",
                    "argument": "command",
                    "pattern": "printf SAFE-N0",
                    "effect": "allow",
                },
            ]
        )
    , binding=_binding())
    proposed = {"command": "printf SAFE-N0"}
    final = {"command": "touch MUTATED-N0"}
    decision = _decision(snapshot, "terminal", proposed, final_arguments=final)
    assert decision.effect == "deny"

    with pytest.raises(Exception, match="policy|binding|snapshot|invalid"):
        snapshot.authorize_tool_call(
            tool_name="terminal",
            arguments={"command": "touch FAIL-CLOSED-N0"},
            binding={"session_id": "native-session-A"},
        )


def test_n0_ac6_session_snapshot_is_immutable_after_provider_revision_changes():
    """Catches old sessions consulting a mutable provider after their first turn."""
    snapshot_type = _snapshot_type()
    old = snapshot_type.from_mapping(_payload(), binding=_binding())
    newer = snapshot_type.from_mapping(
        _payload(
            source={"agent_id": "shared-agent-n0-specialist", "revision": 8},
            instructions="FROZEN-N0-INSTRUCTION-8",
            allowed_tools=["read_file"],
        )
    , binding=_binding())

    assert old.source.revision == 7
    assert old.instructions == "FROZEN-N0-INSTRUCTION-7"
    assert old.allowed_tools == ("terminal", "read_file")
    assert newer.source.revision == 8
    assert newer.allowed_tools == ("read_file",)
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        old.instructions = "MUTATED"


def test_n0_ac7_policy_is_bound_and_unsupported_shapes_are_rejected():
    """Catches cross-session/profile reuse and lossy fallback for unknown policy data."""
    snapshot_type = _snapshot_type()
    snapshot = snapshot_type.from_mapping(_payload(), binding=_binding())
    assert _decision(snapshot, "terminal", {"command": "echo ok"}).effect == "allow"

    with pytest.raises(Exception, match="binding|session|owner|profile|generation"):
        snapshot.authorize_tool_call(
            tool_name="terminal",
            arguments={"command": "echo cross-bound"},
            binding=_binding(session_id="native-session-B"),
        )
    for payload in (
        _payload(version=999),
        _payload(unknown_critical="must-not-be-dropped"),
        _payload(rules=[{"tool": "terminal", "effect": "silently-weaken"}]),
    ):
        with pytest.raises(Exception, match="unsupported|unknown|invalid|policy|version"):
            snapshot_type.from_mapping(payload, binding=_binding())


def test_n0_ac8_unbound_native_session_has_no_shared_policy_authority():
    """Catches registration changing ordinary native defaults or granting implicit tools."""
    snapshot_type = _snapshot_type()
    native_tools = [{"name": "terminal"}, {"name": "read_file"}]
    assert snapshot_type.native_tool_schemas(native_tools) == native_tools
    assert snapshot_type.native_tool_schemas(native_tools) is not native_tools



def test_n0_ac7_binding_is_constructor_authority_and_payload_is_copied():
    snapshot_type = _snapshot_type()
    payload = _payload()
    original = _binding()
    snapshot = snapshot_type.from_mapping(payload, binding=original)
    payload["source"]["revision"] = 99
    payload["allowed_tools"].clear()
    original["owner_id"] = "tampered"
    assert snapshot.source.revision == 7
    assert snapshot.allowed_tools == ("terminal", "read_file")
    assert _decision(snapshot, "terminal", {"command": "echo ok"}).effect == "allow"
    for override in (
        {"session_id": "other"}, {"owner_id": "other"},
        {"profile_id": "other"}, {"runtime_generation": "other"},
    ):
        with pytest.raises(Exception, match="binding|session|owner|profile|generation"):
            _decision(snapshot, "terminal", {"command": "echo denied"}, binding=_binding(**override))
    with pytest.raises(Exception, match="binding|session|owner|profile|generation"):
        snapshot_type.from_mapping(_payload(), binding={"session_id": "A"})


def test_n0_direct_native_dispatch_denies_before_terminal_side_effect(tmp_path):
    """Drive the real dispatcher with a forbidden terminal operation."""
    from model_tools import handle_function_call

    marker = tmp_path / "forbidden"
    snapshot = _snapshot_type().from_mapping(
        _payload(allowed_tools=[]), binding=_binding()
    )
    result = handle_function_call(
        "terminal", {"command": f"touch {marker}"},
        session_policy=snapshot, policy_binding=_binding(),
        skip_pre_tool_call_hook=True,
    )
    assert "policy" in result.lower()
    assert not marker.exists()


def test_n0_direct_dispatch_fails_closed_on_wrong_binding(tmp_path):
    from model_tools import handle_function_call

    marker = tmp_path / "forbidden"
    snapshot = _snapshot_type().from_mapping(
        _payload(allowed_tools=["terminal"]), binding=_binding()
    )
    result = handle_function_call(
        "terminal", {"command": f"touch {marker}"},
        session_policy=snapshot,
        policy_binding=_binding(profile_id="wrong"),
        skip_pre_tool_call_hook=True,
    )
    assert "policy" in result.lower()
    assert not marker.exists()


def test_n0_file_rules_resolve_traversal_and_symlinks(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("fixture")
    (root / "link.txt").symlink_to(outside)
    snapshot = _snapshot_type().from_mapping(
        _payload(allowed_tools=["read_file"], rules=[
            {"tool": "read_file", "argument": "path",
             "pattern": str(root / "*"), "effect": "allow"}
        ]), binding=_binding(),
    )
    assert _decision(snapshot, "read_file", {"path": str(root / "good.txt")}).effect == "allow"
    assert _decision(snapshot, "read_file", {"path": str(outside)}).effect == "deny"
    assert _decision(snapshot, "read_file", {"path": str(root / ".." / "outside.txt")}).effect == "deny"
    assert _decision(snapshot, "read_file", {"path": str(root / "link.txt")}).effect == "deny"


def test_n0_direct_dispatch_ask_requires_fresh_native_callback(tmp_path):
    from model_tools import handle_function_call

    target = tmp_path / "inside.txt"
    target.write_text("APPROVED-NONCE-N0")
    snapshot = _snapshot_type().from_mapping(
        _payload(allowed_tools=["read_file"], rules=[
            {"tool": "read_file", "argument": "path", "pattern": str(tmp_path / "*"), "effect": "ask"}
        ]), binding=_binding(),
    )
    answers = iter([True, False])
    calls = []

    def approve(tool, arguments):
        calls.append((tool, arguments["path"]))
        return next(answers)

    kwargs = {"session_policy": snapshot, "policy_binding": _binding(),
              "policy_approval_callback": approve, "skip_pre_tool_call_hook": True}
    first = handle_function_call("read_file", {"path": str(target)}, **kwargs)
    second = handle_function_call("read_file", {"path": str(target)}, **kwargs)
    assert "APPROVED-NONCE-N0" in first
    assert "policy approval" in second.lower()
    assert len(calls) == 2
