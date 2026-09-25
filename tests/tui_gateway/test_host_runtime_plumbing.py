from __future__ import annotations

import importlib
import io
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
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


def test_review_compute_host_discovers_rhythm_before_v2_restore(tmp_path):
    """review:tui_gateway/compute_host.py:582: a fresh isolated host restores v2."""
    root = str(tmp_path.resolve())
    snapshot = {
        "version": 2,
        "source": {
            "agent_id": "shared-agent",
            "revision": 7,
            "reference": "projection-v2",
        },
        "instructions": "Frozen policy",
        "model": {"provider": "openrouter", "model": "fixture", "reasoning": None},
        "allowed_tools": [],
        "tool_effects": {},
        "paths": {"root": root, "boundary": [root], "external": "deny", "protected": []},
        "rules": [],
        "taint_gate": {"sources": [], "gated": []},
        "launch": {"kind": "interactive", "cwd": root},
    }

    class ProjectionHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.path == "/agent-bridge/v1/projections/projection-v2/check"
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length))
            assert body == {"sessionKey": "lineage", "includeSnapshot": True}
            payload = json.dumps({
                "ok": True,
                "ownerId": "owner",
                "snapshot": snapshot,
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):
            pass

    stub = ThreadingHTTPServer(("127.0.0.1", 0), ProjectionHandler)
    thread = threading.Thread(target=stub.serve_forever, daemon=True)
    thread.start()
    repo = Path(__file__).resolve().parents[2]
    home = tmp_path / "child-home"
    hermes_home = tmp_path / "child-hermes-home"
    home.mkdir()
    hermes_home.mkdir()
    origin = f"http://127.0.0.1:{stub.server_address[1]}"
    entry = {
        "payload": snapshot,
        "owner_id": "owner",
        "profile_id": "default",
        "lineage_root": "lineage",
        "tainted": True,
    }
    probe = f"""
import io
from agent import host_capabilities
host_capabilities.install_from_parent({{"rhythm_bridge": {{"token": {('C' * 43)!r}, "origin": {origin!r}}}}})
from tui_gateway.compute_host import ComputeHost
from tui_gateway import server
captured = {{}}
class Agent:
    pass
def make_agent(*_args, **kwargs):
    captured["policy"] = kwargs["session_policy"]
    return Agent()
def init_session(sid, key, agent, history, **_kwargs):
    server._sessions[sid] = {{
        "agent": agent, "session_key": key, "history": history,
        "history_lock": __import__("threading").Lock(), "running": False,
    }}
server._make_agent = make_agent
server._transfer_db_to_agent = lambda _agent, _db: False
server._init_session = init_session
host = ComputeHost(stdout=io.StringIO(), heartbeat_secs=0)
try:
    host._ensure_server_session(server, {{
        "sid": "fresh-v2", "session_key": "lineage",
        "native_session_policy": {entry!r},
    }})
    assert captured["policy"].version == 2
    assert captured["policy"].restored_tainted is True
finally:
    server._sessions.pop("fresh-v2", None)
    host.close()
"""
    env = dict(os.environ)
    env.update({
        "HOME": str(home),
        "HERMES_HOME": str(hermes_home),
        "HERMES_HOST_REQUIRED_PLUGINS": "rhythm",
        "PYTHONPATH": str(repo) + os.pathsep + env.get("PYTHONPATH", ""),
    })
    try:
        result = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
    finally:
        stub.shutdown()
        stub.server_close()
        thread.join(timeout=2)
    assert result.returncode == 0, result.stderr


def test_review_compute_host_taint_round_trip_survives_next_host_frame(tmp_path, monkeypatch):
    """review:tui_gateway/server.py:1842: use the real host turn.end producer."""
    from types import SimpleNamespace

    from agent.session_policy import SessionPolicySnapshot
    from tui_gateway import server

    root = str(tmp_path.resolve())
    snapshot = SessionPolicySnapshot.from_mapping({
        "version": 2,
        "source": {"agent_id": "shared-agent", "revision": 7, "reference": "projection-v2"},
        "instructions": "Frozen policy",
        "model": {"provider": "openrouter", "model": "fixture", "reasoning": None},
        "allowed_tools": [],
        "tool_effects": {},
        "paths": {"root": root, "boundary": [root], "external": "deny", "protected": []},
        "rules": [],
        "taint_gate": {"sources": [], "gated": []},
        "launch": {"kind": "interactive", "cwd": root},
    }, binding={
        "session_id": "lineage",
        "owner_id": "owner",
        "profile_id": "default",
        "runtime_generation": server._SESSION_POLICY_RUNTIME_GENERATION,
    })
    host = ComputeHost(stdout=io.StringIO(), heartbeat_secs=0)
    emitted = []
    host.emit = emitted.append
    host_session = {
        "agent": SimpleNamespace(session_policy_tainted=True),
        "session_policy": snapshot,
        "session_key": "lineage",
        "history": [],
        "history_lock": threading.Lock(),
        "history_version": 3,
        "running": False,
        "cwd": root,
    }
    monkeypatch.setattr(host, "_ensure_server_session", lambda _server, _frame: host_session)
    monkeypatch.setattr(server, "session_policy_turn_gate", lambda _session: None)
    monkeypatch.setattr(server, "_start_inflight_turn", lambda *_args: None)
    monkeypatch.setattr(server, "_ensure_session_db_row", lambda *_args: None)
    monkeypatch.setattr(server, "_persist_branch_seed", lambda *_args: None)
    monkeypatch.setattr(server, "_run_prompt_submit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_session_info", lambda *_args: {})
    monkeypatch.setattr(server, "_clear_inflight_turn", lambda *_args: None)
    try:
        host._run_real_turn({"sid": "sid", "request_id": "turn", "prompt": "hello"})
    finally:
        host.close()
    frame = next(item for item in emitted if item["type"] == "turn.end")
    assert frame["policy_tainted"] is True

    persisted = []
    parent = {
        "agent": None,
        "session_policy": snapshot,
        "session_key": "lineage",
        "history": [],
        "history_lock": threading.Lock(),
        "history_version": 3,
        "policy_tainted": False,
        "cwd": root,
    }
    monkeypatch.setattr(server, "_persist_policy_session_entry", lambda value: persisted.append(value))
    server._apply_compute_host_metadata_mirror(parent, frame)
    assert parent["policy_tainted"] is True
    assert persisted == [parent]
    respawn = server._compute_host_turn_frame("next", "sid", parent, "again")
    assert respawn["native_session_policy"]["tainted"] is True
