"""Acceptance contracts RP-7 and RP-8 for the Rhythm delegation worker."""

from __future__ import annotations

import json
import threading


def _job():
    return {
        "jobId": "00000000-0000-4000-8000-000000000001",
        "targetAgentId": "agent-2",
        "targetLabel": "Specialist",
        "targetRevision": 4,
        "prompt": "Do the work",
        "context": "Context",
        "cwd": "/work/project",
        "depth": 1,
        "chainId": "chain-1",
        "leaseToken": "B" * 43,
        "leaseExpiresAt": "later",
    }


def test_rp_7_worker_claim_run_approval_cancel_and_crash(monkeypatch):
    """Regression: a claimed job is duplicated or an approval is auto-allowed."""
    from plugins.rhythm import delegation_worker

    reports = []
    holder = {}

    class Client:
        def call(self, op, **kwargs):
            if op == "delegation.report":
                reports.append(kwargs["body"])
                return {"state": kwargs["body"]["phase"], "cancelRequested": False, "leaseExpiresAt": "later"}
            raise AssertionError(op)

    class Session:
        session_key = "child-lineage"
        sid = "child-sid"

        def submit(self, text):
            assert text == "Context\n\nDo the work"
            holder["on_event"]({"type": "tool.complete"})
            holder["on_event"]({"type": "approval.request", "request_id": "approval-1"})
            holder["on_event"]({"type": "message.complete", "text": "finished"})

        def respond_approval(self, request_id, choice):
            holder.setdefault("approvals", []).append((request_id, choice))

        def interrupt(self):
            holder["interrupted"] = True

        def close(self):
            holder["closed"] = True

    def create_session(params, *, on_event, timeout=30.0):
        holder["params"] = params
        holder["on_event"] = on_event
        return Session()

    worker = delegation_worker.DelegationWorker(client=Client(), session_factory=create_session)
    worker.run_claim(_job())
    assert holder["params"]["policy_selection"] == "rhythm-job:v1:00000000-0000-4000-8000-000000000001"
    assert holder["approvals"] == [("approval-1", "deny")]
    assert holder["closed"] is True
    assert reports[0]["phase"] == "running"
    assert any(report.get("progress", {}).get("latestKind") == "approval_denied" for report in reports)
    assert reports[-1]["phase"] == "succeeded"
    assert reports[-1]["resultText"] == "finished"
    assert reports[-1]["childSessionKey"] == "child-lineage"

    create_count = 0

    def crash(*_args, **_kwargs):
        nonlocal create_count
        create_count += 1
        raise RuntimeError("driver crashed")

    reports.clear()
    delegation_worker.DelegationWorker(client=Client(), session_factory=crash).run_claim(_job())
    assert create_count == 1
    assert reports[-1]["phase"] == "failed"

    from tui_gateway.session_driver import DriverError

    reports.clear()

    def policy_refusal(*_args, **_kwargs):
        raise DriverError("unsupported_policy:lease_invalid", code="lease_invalid")

    delegation_worker.DelegationWorker(
        client=Client(), session_factory=policy_refusal
    ).run_claim(_job())
    assert reports[-1]["errorCode"] == "lease_invalid"

    class CancelClient:
        def call(self, op, **kwargs):
            assert op == "delegation.report"
            reports.append(kwargs["body"])
            return {"state": "cancelled", "cancelRequested": kwargs["body"]["phase"] == "running", "leaseExpiresAt": "later"}

    holder.clear()
    reports.clear()
    delegation_worker.DelegationWorker(client=CancelClient(), session_factory=create_session).run_claim(_job())
    assert holder["interrupted"] is True
    assert holder["closed"] is True
    assert reports[-1]["phase"] == "cancelled"


def test_review_worker_bounds_terminal_report_and_keeps_recovery_session_key():
    """review:delegation_worker.py:173/178: terminal recovery fits the bridge contract."""
    from plugins.rhythm import delegation_worker

    reports = []
    oversized = ('escape "\\\n' + "界") * 20_000

    class Client:
        def call(self, op, **kwargs):
            assert op == "delegation.report"
            body = kwargs["body"]
            assert len(json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= 65_536
            reports.append(body)
            return {
                "state": "unknown" if body["phase"] == "running" else body["phase"],
                "cancelRequested": False,
                "leaseExpiresAt": "later",
            }

    class Session:
        session_key = "child-lineage"

        def close(self):
            pass

    def factory(_params, *, on_event, timeout=30.0):
        return SessionWithCallback(on_event)

    class SessionWithCallback(Session):
        def __init__(self, callback):
            self._callback = callback

        def submit(self, _text):
            self._callback({"type": "message.complete", "status": "complete", "text": oversized})

    delegation_worker.DelegationWorker(client=Client(), session_factory=factory).run_claim(_job())
    terminal = reports[-1]
    assert terminal["phase"] == "succeeded"
    assert terminal["childSessionKey"] == "child-lineage"
    assert len(terminal["resultText"]) <= 16_384
    assert terminal["resultText"].endswith("[truncated]")

    reports.clear()
    oversized = "x" * 16_384
    delegation_worker.DelegationWorker(client=Client(), session_factory=factory).run_claim(_job())
    boundary = reports[-1]
    assert boundary["phase"] == "succeeded"
    assert boundary["resultText"] == oversized
    assert not boundary["resultText"].endswith("[truncated]")


def test_review_worker_maps_interrupted_completion_to_cancelled():
    """review:delegation_worker.py:219: partial interrupted output is not success."""
    from plugins.rhythm import delegation_worker

    reports = []

    class Client:
        def call(self, op, **kwargs):
            reports.append(kwargs["body"])
            return {"state": kwargs["body"]["phase"], "cancelRequested": False}

    class Session:
        session_key = "child-lineage"

        def __init__(self, callback):
            self._callback = callback

        def submit(self, _text):
            self._callback({"type": "message.complete", "status": "interrupted", "text": "partial"})

        def close(self):
            pass

    def factory(_params, *, on_event, timeout=30.0):
        return Session(on_event)

    delegation_worker.DelegationWorker(client=Client(), session_factory=factory).run_claim(_job())
    assert reports[-1]["phase"] == "cancelled"
    assert reports[-1]["childSessionKey"] == "child-lineage"


def test_review_worker_retries_terminal_report_during_bridge_recovery(monkeypatch):
    """review:delegation_worker.py:173: a transient outage cannot discard the result."""
    from plugins.rhythm import delegation_worker
    from plugins.rhythm.agent_bridge import BridgeError

    reports = []
    terminal_attempts = 0
    monkeypatch.setattr(
        delegation_worker,
        "_TERMINAL_REPORT_BACKOFF_SECONDS",
        (0, 0),
        raising=False,
    )

    class Client:
        def call(self, op, **kwargs):
            nonlocal terminal_attempts
            assert op == "delegation.report"
            body = kwargs["body"]
            reports.append(body)
            if body["phase"] == "succeeded":
                terminal_attempts += 1
                if terminal_attempts == 1:
                    raise BridgeError("bridge_unavailable")
                if terminal_attempts == 2:
                    raise BridgeError("bridge_capability_unknown")
            return {
                "state": "unknown" if body["phase"] == "running" else body["phase"],
                "cancelRequested": False,
            }

    class Session:
        session_key = "child-lineage"

        def __init__(self, callback):
            self._callback = callback

        def submit(self, _text):
            self._callback({"type": "message.complete", "status": "complete", "text": "recovered"})

        def close(self):
            pass

    def factory(_params, *, on_event, timeout=30.0):
        return Session(on_event)

    delegation_worker.DelegationWorker(client=Client(), session_factory=factory).run_claim(_job())
    terminal_reports = [report for report in reports if report["phase"] == "succeeded"]
    assert terminal_attempts == 3
    assert len(terminal_reports) == 3
    assert all(report["childSessionKey"] == "child-lineage" for report in terminal_reports)
    assert all(report["resultText"] == "recovered" for report in terminal_reports)


def test_rp_8_worker_start_conditions_singleton_and_report_cadence(monkeypatch):
    """Regression: compute processes start claimers or serving starts duplicates."""
    from agent.host_capabilities import HostCapability
    from plugins.rhythm import delegation_worker

    delegation_worker._reset_worker_for_tests()
    started = []
    monkeypatch.setattr(delegation_worker.host_capabilities, "is_serving_process", lambda: False)
    monkeypatch.setattr(delegation_worker.host_capabilities, "get", lambda _name: HostCapability("C" * 43, "http://127.0.0.1:7452"))
    monkeypatch.setattr(delegation_worker.DelegationWorker, "start", lambda self: started.append(self))
    assert delegation_worker.start_delegation_worker() is None
    assert started == []

    monkeypatch.setattr(delegation_worker.host_capabilities, "is_serving_process", lambda: True)
    first = delegation_worker.start_delegation_worker()
    second = delegation_worker.start_delegation_worker()
    assert first is second
    assert len(started) == 1

    assert delegation_worker.RUNTIME_REPORT_INTERVAL_SECONDS == 300
    assert delegation_worker.PROGRESS_INTERVAL_SECONDS <= 20
    assert delegation_worker.MAX_CONCURRENT_JOBS == 2

    claims = []

    class EmptyClient:
        def call(self, op, **kwargs):
            if op == "runtime.report":
                return {}
            assert op == "delegation.claim"
            claims.append(kwargs["body"])
            loop_worker.stop()
            return {}

    monkeypatch.setattr(delegation_worker, "_runtime_report", lambda: {"providers": []})
    loop_worker = delegation_worker.DelegationWorker(client=EmptyClient())
    loop_worker._loop()
    assert claims == [{"waitMs": 20_000}]
