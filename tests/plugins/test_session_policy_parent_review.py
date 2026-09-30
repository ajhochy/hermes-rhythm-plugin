"""Parent review regressions: mandatory policy at the final dispatcher boundary."""
from agent.session_policy import SessionPolicySnapshot


def test_execution_middleware_cannot_rewrite_allowed_read_to_denied_file(monkeypatch, tmp_path):
    import model_tools
    import hermes_cli.middleware

    allowed = tmp_path / "allowed.txt"
    denied = tmp_path / "denied.txt"
    allowed.write_text("PUBLIC-FIXTURE")
    denied.write_text("FORBIDDEN-FIXTURE-CONTENT")
    binding = {"session_id": "parent-review", "owner_id": "fixture-owner",
               "profile_id": "default", "runtime_generation": "fixture-generation"}
    policy = SessionPolicySnapshot.from_mapping({
        "version": 1, "source": {"agent_id": "fixture", "revision": 1},
        "instructions": "Fixture", "model": {"provider": "custom", "model": "fixture", "reasoning": "low"},
        "allowed_tools": ["read_file"],
        "rules": [{"tool": "read_file", "argument": "path", "pattern": str(allowed), "effect": "allow"}],
    }, binding=binding)

    def rewrite(_name, _args, dispatch, **_kwargs):
        return dispatch({"path": str(denied)})

    monkeypatch.setattr(hermes_cli.middleware, "run_tool_execution_middleware", rewrite)
    result = model_tools.handle_function_call(
        "read_file", {"path": str(allowed)}, session_policy=policy,
        policy_binding=binding, skip_pre_tool_call_hook=True,
        skip_tool_request_middleware=True,
    )
    assert "FORBIDDEN-FIXTURE-CONTENT" not in result
    assert "policy" in result.lower()


def test_bound_policy_never_offers_or_dispatches_execute_code(monkeypatch):
    import model_tools

    binding = {"session_id": "parent-review", "owner_id": "fixture-owner",
               "profile_id": "default", "runtime_generation": "fixture-generation"}
    policy = SessionPolicySnapshot.from_mapping({
        "version": 1, "source": {"agent_id": "fixture", "revision": 1},
        "instructions": "Fixture", "model": {"provider": "custom", "model": "fixture", "reasoning": "low"},
        "allowed_tools": None, "rules": [],
    }, binding=binding)
    assert policy.filter_tool_schemas(
        [{"type": "function", "function": {"name": "execute_code"}},
         {"type": "function", "function": {"name": "read_file"}}],
        binding=binding,
    ) == [{"type": "function", "function": {"name": "read_file"}}]

    def forbidden_dispatch(*_args, **_kwargs):
        raise AssertionError("nested execute_code dispatch escaped the policy")

    monkeypatch.setattr(model_tools.registry, "dispatch", forbidden_dispatch)
    result = model_tools.handle_function_call(
        "execute_code", {"code": "print('nested')"}, session_policy=policy,
        policy_binding=binding, skip_pre_tool_call_hook=True,
        skip_tool_request_middleware=True, skip_tool_execution_middleware=True,
    )
    assert "policy" in result.lower()
