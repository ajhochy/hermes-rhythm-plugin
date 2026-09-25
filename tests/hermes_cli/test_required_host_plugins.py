from __future__ import annotations

from hermes_cli.plugins import LoadedPlugin, PluginManager, PluginManifest


def _manifest(name: str, source: str) -> PluginManifest:
    return PluginManifest(
        name=name,
        key=name,
        source=source,
        path=f"/{source}/{name}",
    )


def test_hp_4_required_host_plugins_load_bundled_only(monkeypatch, tmp_path):
    """Regression caught: the host requirement loads user code or needs config writes."""
    bundled = _manifest("rhythm", "bundled")
    user_only = _manifest("user-only", "user")
    loaded = []
    manager = PluginManager(scope_key=str(tmp_path))
    monkeypatch.setenv("HERMES_HOST_REQUIRED_PLUGINS", "rhythm,user-only")
    monkeypatch.setattr(manager, "_collect_directory_manifests", lambda: [bundled, user_only])
    monkeypatch.setattr(manager, "_scan_entry_points", lambda: [])
    monkeypatch.setattr(manager, "_warn_python_dependencies", lambda _manifest: None)
    monkeypatch.setattr(manager, "_validate_plugin_config_schema", lambda _manifest: None)

    def load(manifest):
        loaded.append((manifest.name, manifest.source))
        manager._plugins[manifest.key] = LoadedPlugin(manifest=manifest, enabled=True)

    monkeypatch.setattr(manager, "_load_plugin", load)
    monkeypatch.setattr("hermes_cli.plugins._get_disabled_plugins", lambda: set())
    monkeypatch.setattr("hermes_cli.plugins._get_enabled_plugins", lambda: None)

    manager.discover_and_load()

    assert loaded == [("rhythm", "bundled")]


def test_hp_4_serve_startup_initializes_capabilities_before_discovery(monkeypatch):
    """Regression caught: plugins discover before the one-shot handoff is consumed."""
    from hermes_cli import web_server

    order = []
    monkeypatch.setattr("agent.host_capabilities.load_from_handoff", lambda: order.append("load"))
    monkeypatch.setattr("agent.host_capabilities.mark_serving_process", lambda: order.append("mark"))
    monkeypatch.setattr("hermes_cli.plugins.discover_plugins", lambda: order.append("discover"))
    monkeypatch.setenv("HERMES_HOST_REQUIRED_PLUGINS", "rhythm")

    web_server._initialize_host_runtime()

    assert order == ["load", "mark", "discover"]


def test_hp_4_cmd_dashboard_initializes_capabilities_before_plugins_and_mcp(monkeypatch):
    """Regression caught: the real serve path discovers extensions before its handoff."""
    from types import SimpleNamespace

    from hermes_cli import main, mcp_startup, plugins, resource_limits, web_server

    order = []
    monkeypatch.setenv("HERMES_DESKTOP", "1")
    monkeypatch.setenv("HERMES_SERVE_HEADLESS", "0")
    monkeypatch.setattr("agent.host_capabilities.load_from_handoff", lambda: order.append("load"))
    monkeypatch.setattr("agent.host_capabilities.mark_serving_process", lambda: order.append("mark"))
    monkeypatch.setattr(resource_limits, "apply_nofile_soft_limit", lambda: None)
    monkeypatch.setattr(main, "_sync_bundled_skills_quietly", lambda: None)
    monkeypatch.setattr(main, "_maybe_setup_dashboard_auth_interactively", lambda _args: None)
    monkeypatch.setattr(plugins, "discover_plugins", lambda: order.append("discover"))
    monkeypatch.setattr(mcp_startup, "start_background_mcp_discovery", lambda **_kwargs: order.append("mcp"))
    monkeypatch.setattr(web_server, "start_server", lambda **_kwargs: order.append("server"))

    main.cmd_dashboard(SimpleNamespace(
        status=False,
        stop=False,
        headless_backend=True,
        ssh_owner_nonce=None,
        ssh_session_token_file=None,
        host="127.0.0.1",
        port=7360,
        no_open=True,
        insecure=False,
        open_profile="",
        isolated=True,
        skip_build=False,
    ))

    assert order == ["load", "mark", "discover", "mcp", "server"]
