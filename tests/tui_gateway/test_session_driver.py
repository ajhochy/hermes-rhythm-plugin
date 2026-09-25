from __future__ import annotations

from tui_gateway import server


def test_hp_5_driver_lifecycle_events_and_eviction_exemption(monkeypatch):
    """Regression caught: headless worker sessions lose events or are evicted while open."""
    from tui_gateway.session_driver import create_session, is_driver_transport

    calls = []
    events = []

    def handle(request):
        calls.append((request["method"], dict(request.get("params") or {})))
        method = request["method"]
        if method == "session.create":
            return {
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": {"session_id": "driver-sid", "stored_session_id": "lineage-root"},
            }
        return {"jsonrpc": "2.0", "id": request["id"], "result": {"ok": True}}

    monkeypatch.setattr(server, "handle_request", handle)
    session = create_session({"title": "job"}, on_event=events.append)
    assert is_driver_transport(session.transport)
    session.transport.write(
        {
            "jsonrpc": "2.0",
            "method": "event",
            "params": {
                "type": "message.complete",
                "session_id": "driver-sid",
                "payload": {"text": "done"},
            },
        }
    )
    session.submit("hello")
    session.interrupt()
    session.respond_approval("approval-1", "deny")

    assert events == [
        {"type": "message.complete", "session_id": "driver-sid", "text": "done"}
    ]
    assert server._transport_is_dead(session.transport) is False
    assert server._session_is_lru_evictable(
        session.sid,
        {
            "running": False,
            "last_active": 0,
            "transport": session.transport,
        },
    ) is False
    session.close()
    assert [method for method, _params in calls] == [
        "session.create",
        "prompt.submit",
        "session.interrupt",
        "approval.respond",
        "session.close",
    ]


def test_hp_5_driver_errors_preserve_real_gateway_policy_codes(monkeypatch):
    """Regression caught: the gateway's policy code is replaced by JSON-RPC 4000."""
    from tui_gateway.session_driver import DriverError, create_session

    original = server._methods["session.create"]
    server._methods["session.create"] = lambda request_id, _params: server._err(
        request_id,
        4000,
        "unsupported_policy:lease_invalid",
    )

    try:
        try:
            create_session({}, on_event=lambda _event: None)
        except DriverError as exc:
            assert exc.code == "lease_invalid"
        else:  # pragma: no cover - assertion clarity
            raise AssertionError("DriverError was not raised")
    finally:
        server._methods["session.create"] = original
