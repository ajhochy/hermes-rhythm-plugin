"""Opt-in native Hermes shared-policy acceptance through the real gateway turn.

Run with ``RHYTHM_SHARED_AGENTS_LIVE=1 scripts/run_tests.sh
tests/tui_gateway/test_shared_agent_policy_live.py -q``.  The provider is an
in-process authority fixture; the model is a loopback OpenAI-compatible HTTP
endpoint.  No OpenCode server, hosted model, or real user profile is involved.

This file is intentionally pending live Recon/Confirm in the coordinated Rhythm
smoke campaign.  A default test run collects it but starts no listener.
"""
from __future__ import annotations

import json
import os
import threading
import time
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("RHYTHM_SHARED_AGENTS_LIVE") != "1",
    reason="native shared-agent live lane requires RHYTHM_SHARED_AGENTS_LIVE=1",
)


class _PolicyProvider:
    def __init__(self, *, allowed_tools, instructions, revision=1, rules=()):
        self.allowed_tools = allowed_tools
        self.instructions = instructions
        self.revision = revision
        self.rules = list(rules)

    def resolve(self, selection, **context):
        if selection != "fixture-native-agent" or not context.get("session_id"):
            raise ValueError("invalid fixture selection")
        return ({
            "version": 1,
            "source": {"agent_id": "fixture-native-agent", "revision": self.revision},
            "instructions": self.instructions,
            "model": {
                "provider": "custom:rhythm-n0-loopback",
                "model": "rhythm-n0-fixture-model",
                "reasoning": "low",
            },
            "allowed_tools": self.allowed_tools,
            "rules": self.rules,
        }, "fixture-owner")


class _ModelHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        owner = self.server  # type: ignore[attr-defined]
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        size = int(self.headers.get("Content-Length", "0"))
        if not 0 < size < 256_000:
            self.send_error(413)
            return
        request = json.loads(self.rfile.read(size))
        is_title = any("You name chat sessions" in str(message.get("content", ""))
                       for message in request.get("messages", []))
        with owner.capture_lock:
            if is_title:
                owner.aux_requests.append(request)
                reply = [_chunk({"role": "assistant", "content": '{"title":"N0 fixture"}'}),
                         _chunk({}, "stop")]
            else:
                owner.requests.append(request)
                reply = owner.respond(request)
        if request.get("stream"):
            content = b"".join(
                b"data: " + json.dumps(chunk, separators=(",", ":")).encode() + b"\n\n"
                for chunk in reply
            ) + b"data: [DONE]\n\n"
            content_type = "text/event-stream"
        else:
            # The native path currently streams; a nonstream request remains
            # supported so this fixture reports a meaningful model response
            # if Hermes changes its transport without changing policy behavior.
            content = json.dumps(owner.nonstream_reply(request, is_title)).encode()
            content_type = "application/json"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, _format, *_args):
        return


def _chunk(delta, finish_reason=None):
    return {
        "id": "chatcmpl-native-n0", "object": "chat.completion.chunk",
        "created": 1, "model": "rhythm-n0-fixture-model",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


@pytest.fixture
def local_model():
    # Constructing/binding this listener is impossible in the default lane:
    # the module skip is evaluated before any fixture executes.
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ModelHandler)
    server.requests = []
    server.aux_requests = []
    server.capture_lock = threading.Lock()
    server.respond = lambda _request: [_chunk({"role": "assistant", "content": "native-ok"}), _chunk({}, "stop")]
    server.nonstream_reply = lambda _request, is_title: {
        "id": "chatcmpl-native-n0", "object": "chat.completion", "created": 1,
        "model": "rhythm-n0-fixture-model", "choices": [{"index": 0,
        "message": {"role": "assistant", "content":
                    '{"title":"N0 fixture"}' if is_title else "native-ok"},
        "finish_reason": "stop"}],
    }
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.fixture
def native_gateway(tmp_path, monkeypatch, local_model):
    # conftest sandboxes HERMES_HOME before import; pin this test to another
    # throwaway home and keep every mutable native working file inside it.
    home = tmp_path / "home"
    # Keep HERMES_HOME distinct from HOME/.hermes: the live-DB guard correctly
    # treats the latter as a production-shaped path even under a temp HOME.
    hermes_home = home / "fixture-hermes-state"
    hermes_home.mkdir(parents=True)
    working_files = {
        "config.yaml": "{}\n", ".env": "# synthetic fixture only\n",
        "auth.json": "{}\n", "MEMORY.md": "N0_MEMORY_SENTINEL\n",
        "USER.md": "N0_USER_SENTINEL\n",
    }
    for name, content in working_files.items():
        (hermes_home / name).write_text(content)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    from hermes_cli import runtime_provider
    from hermes_state import SessionDB
    from tui_gateway import server
    session_db = SessionDB(db_path=hermes_home / "state.db")

    # The provider resolver is the external credential/catalog boundary.
    # Everything after it, including AIAgent, HTTP, tools and session DB,
    # stays real.  The resolution is loopback-only and carries a fake key.
    def resolve_runtime_provider(*, requested, target_model):
        assert requested == "custom:rhythm-n0-loopback"
        assert target_model == "rhythm-n0-fixture-model"
        return {"provider": "custom", "base_url":
                f"http://127.0.0.1:{local_model.server_port}/v1",
                "api_key": "n0-fixture-only", "api_mode": "chat_completions"}

    monkeypatch.setattr(runtime_provider, "resolve_runtime_provider", resolve_runtime_provider)
    monkeypatch.setattr(server, "_get_db", lambda: session_db)
    monkeypatch.setattr(server, "_schedule_agent_build", lambda _sid: None)
    monkeypatch.setattr(server, "_schedule_session_cap_enforcement", lambda: None)
    monkeypatch.setattr(server, "_session_uses_compute_host", lambda *_a, **_kw: False)
    created = []
    try:
        yield server, created, hermes_home
    finally:
        for sid in created:
            session = server._sessions.pop(sid, None)
            if session is not None and session.get("agent") is not None:
                session["agent"].close()
        session_db.close()


def _working_hashes(home):
    return {name: sha256((home / name).read_bytes()).hexdigest()
            for name in ("config.yaml", ".env", "auth.json", "MEMORY.md", "USER.md")}


def _create(server, created, *, selection="fixture-native-agent"):
    created_response = server.handle_request({
        "id": "n0-create", "method": "session.create",
        "params": {"policy_selection": selection, "cwd": str(Path.cwd()),
                   "title": "N0 fixture session"},
    })
    assert "error" not in created_response, created_response
    sid = created_response["result"]["session_id"]
    created.append(sid)
    return sid


def _submit(server, sid, text="Use the fixture model now", *, expect_agent=True):
    response = server.handle_request({
        "id": "n0-prompt", "method": "prompt.submit",
        "params": {"session_id": sid, "text": text},
    })
    assert response.get("result", {}).get("status") == "streaming", response
    thread = server._sessions[sid].get("_run_thread")
    assert thread is not None
    thread.join(timeout=30)
    # prompt.submit's first thread can return after starting a second worker
    # for the model turn.  Keep the model listener alive until the gateway's
    # actual running flag settles, or a false connection-refused result wins.
    deadline = time.monotonic() + 30
    while server._sessions[sid].get("running") and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not thread.is_alive() and not server._sessions[sid].get("running"), (
        "native Hermes turn exceeded 30 seconds"
    )
    if expect_agent:
        assert server._sessions[sid]["agent"].__class__.__name__ == "AIAgent"
    return sid


def _create_and_submit(server, created, text="Use the fixture model now"):
    return _submit(server, _create(server, created), text)


def _offered_tools(request):
    return {item.get("function", {}).get("name", item.get("name"))
            for item in request.get("tools") or []}


def test_native_shared_agent_uses_real_hermes_policy(native_gateway, local_model, tmp_path):
    """N0-AC1: a native tool result and frozen instruction reach the model."""
    from hermes_cli.plugins import register_session_policy_provider

    server, created, home = native_gateway
    before = _working_hashes(home)
    nonce = "N0_NATIVE_NONCE_" + tmp_path.name
    source = tmp_path / "allowed.txt"
    source.write_text(nonce)
    instructions = "N0_FROZEN_INSTRUCTIONS_" + tmp_path.name
    provider = _PolicyProvider(allowed_tools=["read_file"], instructions=instructions)

    def scripted(request):
        if len(local_model.requests) == 1:
            call = {"index": 0, "id": "call-read-n0", "type": "function",
                    "function": {"name": "read_file", "arguments": json.dumps({"path": str(source)})}}
            return [_chunk({"role": "assistant", "tool_calls": [call]}), _chunk({}, "tool_calls")]
        return [_chunk({"role": "assistant", "content": "native-tool-complete"}), _chunk({}, "stop")]

    local_model.respond = scripted
    dispose = register_session_policy_provider(provider)
    try:
        _create_and_submit(server, created)
    finally:
        dispose()
    assert len(local_model.requests) >= 2, local_model.requests
    first, second = local_model.requests[:2]
    assert first["model"] == "rhythm-n0-fixture-model"
    assert first.get("reasoning_effort") == "low"
    assert instructions in json.dumps(first.get("messages"))
    assert _offered_tools(first) == {"read_file"}
    assert nonce in json.dumps(second.get("messages")), "real native read_file result never reached model"
    assert "native-tool-complete" in json.dumps(server._sessions[created[0]].get("history"))
    assert _working_hashes(home) == before


def test_empty_tool_allowlist_does_not_inherit(native_gateway, local_model, tmp_path):
    """N0-AC2: [] offers zero tools and refuses a forged terminal call."""
    from hermes_cli.plugins import register_session_policy_provider

    server, created, home = native_gateway
    before = _working_hashes(home)
    marker = tmp_path / "must-not-exist"
    provider = _PolicyProvider(allowed_tools=[], instructions="N0_DENY_ALL")

    def scripted(request):
        if len(local_model.requests) == 1:
            call = {"index": 0, "id": "call-terminal-n0", "type": "function",
                    "function": {"name": "terminal", "arguments": json.dumps({
                        "command": f"touch {marker}"})}}
            return [_chunk({"role": "assistant", "tool_calls": [call]}), _chunk({}, "tool_calls")]
        return [_chunk({"role": "assistant", "content": "denial-seen"}), _chunk({}, "stop")]

    local_model.respond = scripted
    dispose = register_session_policy_provider(provider)
    try:
        _create_and_submit(server, created)
    finally:
        dispose()
    assert local_model.requests, "native AIAgent never contacted loopback model"
    assert _offered_tools(local_model.requests[0]) == set()
    assert not marker.exists(), "terminal side effect escaped [] deny-all"
    assert len(local_model.requests) >= 2, "forged tool result was not reported to model"
    tool_results = [message for message in local_model.requests[1].get("messages", [])
                    if message.get("role") == "tool"
                    and message.get("tool_call_id") == "call-terminal-n0"]
    assert len(tool_results) == 1, "forged call must receive its own denial result"
    denial = str(tool_results[0].get("content", "")).lower()
    # An unoffered tool may be rejected by the native catalog before policy
    # dispatch. Inspect that actual result, not the prompt/cwd (which can
    # coincidentally contain the word 'policy'). Neither path may execute it.
    assert "policy" in denial or "does not exist" in denial, denial
    assert _working_hashes(home) == before


def _read_script(path):
    def respond(request):
        if not any(message.get("role") == "tool" for message in request.get("messages", [])):
            call = {"index": 0, "id": "call-read-n0", "type": "function",
                    "function": {"name": "read_file", "arguments": json.dumps({"path": str(path)})}}
            return [_chunk({"role": "assistant", "tool_calls": [call]}), _chunk({}, "tool_calls")]
        return [_chunk({"role": "assistant", "content": "tool-result-received"}), _chunk({}, "stop")]
    return respond


def _rule(pattern, effect):
    return {"tool": "read_file", "argument": "path", "pattern": str(pattern),
            "effect": effect}


def test_allowed_tool_and_ordered_patterns_enforced(native_gateway, local_model, tmp_path):
    """N0-AC3: later path allowance wins; a later deny and symlink escape fail."""
    from hermes_cli.plugins import register_session_policy_provider

    server, created, home = native_gateway
    before = _working_hashes(home)
    safe = tmp_path / "safe"
    safe.mkdir()
    allowed = safe / "inside.txt"
    allowed.write_text("N0_ALLOWED_CONTENT")
    outside = tmp_path / "outside.txt"
    outside.write_text("N0_FORBIDDEN_CONTENT")
    escape = safe / "escape.txt"
    escape.symlink_to(outside)
    provider = _PolicyProvider(
        allowed_tools=["read_file"], instructions="N0_ORDERED_RULES",
        rules=[_rule(tmp_path / "*", "deny"), _rule(safe / "*", "allow")],
    )
    local_model.respond = _read_script(allowed)
    dispose = register_session_policy_provider(provider)
    try:
        _create_and_submit(server, created)
        assert "N0_ALLOWED_CONTENT" in json.dumps(local_model.requests[-1]["messages"])
        local_model.requests.clear()
        provider.rules = [_rule(safe / "*", "allow"), _rule(tmp_path / "*", "deny")]
        provider.revision = 2
        _create_and_submit(server, created)
        denied = json.dumps(local_model.requests[-1]["messages"])
        assert "N0_ALLOWED_CONTENT" not in denied
        assert "policy" in denied.lower()
        local_model.requests.clear()
        provider.rules = [_rule(tmp_path / "*", "deny"), _rule(safe / "*", "allow")]
        provider.revision = 3
        local_model.respond = _read_script(escape)
        _create_and_submit(server, created)
        escaped = json.dumps(local_model.requests[-1]["messages"])
        assert "N0_FORBIDDEN_CONTENT" not in escaped
        assert "policy" in escaped.lower()
        assert _working_hashes(home) == before
    finally:
        dispose()


def test_global_last_deny_wildcard_covers_absolute_path(native_gateway, local_model, tmp_path):
    """N0-AC3 RED: a final '*' must override an earlier specific path allow."""
    from hermes_cli.plugins import register_session_policy_provider

    server, created, _home = native_gateway
    target = tmp_path / "global-wildcard.txt"
    target.write_text("N0_GLOBAL_DENY_CONTENT")
    provider = _PolicyProvider(
        allowed_tools=["read_file"], instructions="N0_GLOBAL_WILDCARD",
        rules=[_rule(target, "allow"), _rule("*", "deny")],
    )
    local_model.respond = _read_script(target)
    dispose = register_session_policy_provider(provider)
    try:
        _create_and_submit(server, created)
        result = json.dumps(local_model.requests[-1]["messages"])
        assert "N0_GLOBAL_DENY_CONTENT" not in result
        assert "policy" in result.lower()
    finally:
        dispose()


def test_policy_ask_uses_native_approval(native_gateway, local_model, tmp_path):
    """N0-AC4: gateway deny and one-shot approval affect actual tool output."""
    from hermes_cli.plugins import register_session_policy_provider
    from tools.approval import list_gateway_approvals

    server, created, _home = native_gateway
    target = tmp_path / "ask.txt"
    target.write_text("N0_APPROVED_CONTENT")
    local_model.respond = _read_script(target)
    provider = _PolicyProvider(allowed_tools=["read_file"], instructions="N0_ASK",
                               rules=[_rule(tmp_path / "*", "ask")])
    dispose = register_session_policy_provider(provider)
    try:
        for choice, should_read in (("deny", False), ("once", True)):
            local_model.requests.clear()
            sid = _create(server, created)
            key = server._sessions[sid]["session_key"]
            turn_errors = []

            def run_turn():
                try:
                    _submit(server, sid)
                except Exception as exc:
                    turn_errors.append(exc)

            turn = threading.Thread(target=run_turn, daemon=True)
            turn.start()
            deadline = time.monotonic() + 12
            approvals = []
            while time.monotonic() < deadline:
                approvals = list_gateway_approvals(key)
                if approvals:
                    break
                time.sleep(0.02)
            assert len(approvals) == 1, "native approval request was not queued"
            assert approvals[0]["choices"] == ["once", "deny"]
            response = server.handle_request({
                "id": "approval", "method": "approval.respond",
                "params": {"session_id": sid, "request_id": approvals[0]["request_id"],
                           "choice": choice},
            })
            assert response.get("result", {}).get("resolved") == 1, response
            turn.join(timeout=30)
            assert not turn.is_alive(), "approval response did not settle the native turn"
            assert not turn_errors, turn_errors
            result = json.dumps(local_model.requests[-1]["messages"])
            assert ("N0_APPROVED_CONTENT" in result) is should_read
    finally:
        dispose()


def test_resolver_and_agent_executor_failure_fail_closed(native_gateway, local_model, tmp_path, monkeypatch):
    """N0-AC5: bad resolution and agent-path evaluator failures block reads."""
    from agent.session_policy import SessionPolicySnapshot, UnsupportedPolicy
    from hermes_cli.plugins import register_session_policy_provider

    server, created, _home = native_gateway
    target = tmp_path / "must-not-read.txt"
    target.write_text("N0_PROTECTED_CONTENT")
    provider = _PolicyProvider(allowed_tools=["read_file"], instructions="N0_FAIL_CLOSED")
    dispose = register_session_policy_provider(provider)
    try:
        invalid = server.handle_request({"id": "invalid", "method": "session.create",
                                         "params": {"policy_selection": "unknown-binding"}})
        assert invalid["error"]["message"] == "unsupported_policy"
        assert not local_model.requests

        def fail_evaluator(_self, **_kwargs):
            raise UnsupportedPolicy("synthetic policy evaluator failure")

        monkeypatch.setattr(SessionPolicySnapshot, "authorize_tool_call", fail_evaluator)
        local_model.respond = _read_script(target)
        _create_and_submit(server, created)
        assert "N0_PROTECTED_CONTENT" not in json.dumps(local_model.requests[-1]["messages"])
    finally:
        dispose()


def test_policy_snapshot_survives_edit_and_native_resume(native_gateway, local_model):
    """N0-AC6: live and DB-resumed sessions retain v1; new session sees v2."""
    from hermes_cli.plugins import register_session_policy_provider

    server, created, home = native_gateway
    before = _working_hashes(home)
    provider = _PolicyProvider(allowed_tools=[], instructions="N0_FROZEN_V1", revision=1)
    dispose = register_session_policy_provider(provider)
    try:
        old_sid = _create_and_submit(server, created)
        assert "N0_FROZEN_V1" in json.dumps(local_model.requests[-1]["messages"])
        provider.revision = 2
        provider.instructions = "N0_FROZEN_V2"
        local_model.requests.clear()
        _submit(server, old_sid, "Continue old session")
        assert "N0_FROZEN_V1" in json.dumps(local_model.requests[-1]["messages"])
        assert "N0_FROZEN_V2" not in json.dumps(local_model.requests[-1]["messages"])
        local_model.requests.clear()
        _create_and_submit(server, created)
        assert "N0_FROZEN_V2" in json.dumps(local_model.requests[-1]["messages"])

        stored = server._sessions[old_sid]["session_key"]
        old = server._sessions.pop(old_sid)
        old["agent"].close()
        resumed = server.handle_request({"id": "resume", "method": "session.resume",
                                         "params": {"session_id": stored}})
        assert "error" not in resumed, resumed
        resumed_sid = resumed["result"]["session_id"]
        created.append(resumed_sid)
        local_model.requests.clear()
        _submit(server, resumed_sid, "Continue restored session")
        assert "N0_FROZEN_V1" in json.dumps(local_model.requests[-1]["messages"])
        assert "N0_FROZEN_V2" not in json.dumps(local_model.requests[-1]["messages"])
        assert _working_hashes(home) == before
    finally:
        dispose()


def test_policy_replay_and_oversize_input_fail_before_model(native_gateway, local_model):
    """N0-AC7: cross-session replay and oversize policy stop before model use."""
    from hermes_cli.plugins import register_session_policy_provider

    server, created, _home = native_gateway
    provider = _PolicyProvider(allowed_tools=[], instructions="N0_BOUND")
    dispose = register_session_policy_provider(provider)
    try:
        first = _create(server, created)
        second = _create(server, created)
        server._sessions[second]["session_policy"] = server._sessions[first]["session_policy"]
        _submit(server, second, expect_agent=False)
        assert not local_model.requests, "cross-session policy reached model"
        provider.revision = 3
        provider.instructions = "x" * 65537
        invalid = server.handle_request({"id": "oversize", "method": "session.create",
                                         "params": {"policy_selection": "fixture-native-agent"}})
        assert invalid["error"]["message"] == "unsupported_policy"
        assert not local_model.requests
    finally:
        dispose()


def test_unbound_native_session_keeps_tool_schemas(native_gateway, local_model, monkeypatch):
    """N0-AC8: provider registration does not strip ordinary native tools."""
    from types import SimpleNamespace
    from hermes_cli.plugins import register_session_policy_provider

    server, created, _home = native_gateway
    runtime = {"provider": "custom", "base_url":
               f"http://127.0.0.1:{local_model.server_port}/v1",
               "api_key": "n0-fixture-only", "api_mode": "chat_completions"}
    monkeypatch.setattr(server, "_resolve_startup_runtime",
                        lambda: ("rhythm-n0-fixture-model", "custom:rhythm-n0-loopback"))
    monkeypatch.setattr(server, "_resolve_runtime_with_fallback",
                        lambda _kwargs: SimpleNamespace(runtime=runtime, used_fallback=False))
    provider = _PolicyProvider(allowed_tools=[], instructions="N0_SHOULD_NOT_APPEAR")
    dispose = register_session_policy_provider(provider)
    try:
        response = server.handle_request({"id": "native", "method": "session.create",
                                          "params": {"title": "ordinary fixture", "cwd": str(Path.cwd())}})
        assert "error" not in response, response
        sid = response["result"]["session_id"]
        created.append(sid)
        _submit(server, sid)
        assert local_model.requests
        assert _offered_tools(local_model.requests[0]), "ordinary native tools were stripped"
        assert "N0_SHOULD_NOT_APPEAR" not in json.dumps(local_model.requests[0]["messages"])
    finally:
        dispose()
