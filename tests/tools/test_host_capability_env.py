from __future__ import annotations

from tools.code_execution_tool import _scrub_child_env
from tools.environments.local import build_subprocess_env


TOKEN = "B" * 43
CAPABILITY_ENV = {
    "HERMES_HOST_CAPABILITIES_FILE": "/tmp/synthetic-capability-file",
    "HERMES_HOST_CAPABILITY_TEST": TOKEN,
    "SAFE_VALUE": "kept",
}


def _assert_scrubbed(env):
    assert env.get("SAFE_VALUE") == "kept"
    assert TOKEN not in env.values()
    assert not any(name.startswith("HERMES_HOST_CAPABILIT") for name in env)


def test_hp_2_all_child_environment_builders_scrub_host_capabilities(monkeypatch):
    """Regression caught: a model-controlled child inherits the bridge bearer."""
    from tui_gateway.host_supervisor import _compute_host_child_env

    _assert_scrubbed(build_subprocess_env(base=CAPABILITY_ENV, scrub_secrets=True))
    _assert_scrubbed(
        build_subprocess_env(
            base=CAPABILITY_ENV,
            scrub_secrets=False,
            inherit_profile_home=False,
        )
    )
    _assert_scrubbed(
        _scrub_child_env(
            CAPABILITY_ENV,
            is_passthrough=lambda _name: True,
            is_windows=False,
        )
    )

    monkeypatch.setenv("HERMES_HOST_CAPABILITIES_FILE", CAPABILITY_ENV["HERMES_HOST_CAPABILITIES_FILE"])
    monkeypatch.setenv("HERMES_HOST_CAPABILITY_TEST", TOKEN)
    monkeypatch.setenv("SAFE_VALUE", "kept")
    monkeypatch.setenv("HASS_TOKEN", "standalone-runtime-token")
    monkeypatch.setenv("HOME", "/tmp/standalone-runtime-home")
    compute_env = _compute_host_child_env()
    _assert_scrubbed(compute_env)
    assert compute_env["HASS_TOKEN"] == "standalone-runtime-token"
    assert compute_env["HOME"] == "/tmp/standalone-runtime-home"


def test_hp_2_dashboard_pty_env_uses_the_scrubbed_factory(monkeypatch):
    """Regression caught: the dashboard PTY reintroduces the handoff path."""
    from hermes_cli import web_server

    monkeypatch.setenv("HERMES_HOST_CAPABILITIES_FILE", "/tmp/synthetic-capability-file")
    monkeypatch.setenv("HERMES_HOST_CAPABILITY_TEST", TOKEN)
    _argv, _cwd, env = web_server._resolve_chat_argv()
    assert env is not None
    assert not any(name.startswith("HERMES_HOST_CAPABILIT") for name in env)
    assert TOKEN not in env.values()
