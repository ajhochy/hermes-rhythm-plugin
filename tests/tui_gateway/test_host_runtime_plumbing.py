from __future__ import annotations

import importlib
import io
import threading

from tui_gateway.compute_host import ComputeHost


TOKEN = "C" * 43
ORIGIN = "http://127.0.0.1:7362"


def test_hp_3_compute_host_installs_capability_frame_without_serving_identity():
    """Regression caught: the compute child receives no bridge authority."""
    import agent.host_capabilities as host_capabilities
    from tui_gateway.host_supervisor import _host_capabilities_frame

    host_capabilities = importlib.reload(host_capabilities)
    host_capabilities.install_from_parent(
        {"rhythm_bridge": {"token": TOKEN, "origin": ORIGIN}}
    )
    frame = _host_capabilities_frame()
    host_capabilities = importlib.reload(host_capabilities)
    host = ComputeHost(stdout=io.StringIO(), heartbeat_secs=0)

    host.handle_frame(frame)

    assert host_capabilities.get("rhythm_bridge") == host_capabilities.HostCapability(TOKEN, ORIGIN)
    assert host_capabilities.is_serving_process() is False


def test_hp_6_policy_entry_is_opaque_and_turn_gate_runs_before_prompt(monkeypatch):
    """Regression caught: compute transfer drops future policy keys or runs revoked work."""
    from tui_gateway import server

    host = ComputeHost(stdout=io.StringIO(), heartbeat_secs=0)
    opaque_entry = {
        "payload": {
            "version": 1,
            "source": {"agent_id": "shared-agent", "revision": 7},
            "instructions": "Keep the frozen policy.",
            "model": {"provider": "fixture", "model": "fixture", "reasoning": "none"},
            "allowed_tools": ["read_file"],
            "rules": [],
        },
        "owner_id": "owner",
        "profile_id": "default",
        "unknown_entry_key": "preserve-me",
    }
    captured = {}

    class Agent:
        pass

    def make_agent(*_args, **kwargs):
        captured["snapshot"] = kwargs["session_policy"]
        return Agent()

    def init_session(sid, key, agent, history, **kwargs):
        server._sessions[sid] = {
            "agent": agent,
            "session_key": key,
            "history": history,
            "history_lock": threading.Lock(),
            "running": False,
            "last_active": 0.0,
            "transport": kwargs.get("transport"),
            "session_policy": captured["snapshot"],
        }

    monkeypatch.setattr(server, "_make_agent", make_agent)
    monkeypatch.setattr(server, "_transfer_db_to_agent", lambda _agent, _db: False)
    monkeypatch.setattr(server, "_init_session", init_session)
    server._sessions.pop("sid", None)
    try:
        restored_session = host._ensure_server_session(
            server,
            {
                "sid": "sid",
                "session_key": "lineage",
                "native_session_policy": opaque_entry,
            },
        )
        assert captured["snapshot"].instructions == "Keep the frozen policy."
        assert restored_session["native_session_policy_entry"] == opaque_entry
    finally:
        server._sessions.pop("sid", None)

    order = []
    session = {
        "history_lock": threading.Lock(),
        "running": False,
        "last_active": 0.0,
        "session_key": "lineage",
        "history": [],
        "agent": object(),
    }
    monkeypatch.setattr(host, "_ensure_server_session", lambda _server, _frame: session)
    monkeypatch.setattr(server, "session_policy_turn_gate", lambda value: order.append(("gate", value)), raising=False)
    monkeypatch.setattr(server, "_start_inflight_turn", lambda *_args: None)
    monkeypatch.setattr(server, "_ensure_session_db_row", lambda *_args: None)
    monkeypatch.setattr(server, "_persist_branch_seed", lambda *_args: None)
    monkeypatch.setattr(server, "_run_prompt_submit", lambda *_args, **_kwargs: order.append(("submit", session)))
    monkeypatch.setattr(server, "_session_info", lambda *_args: {})
    monkeypatch.setattr(server, "_clear_inflight_turn", lambda *_args: None)

    host._run_real_turn({"sid": "sid", "request_id": "request", "prompt": "hello"})

    assert [item[0] for item in order] == ["gate", "submit"]
