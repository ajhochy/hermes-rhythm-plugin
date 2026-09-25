"""Acceptance contracts RP-7 and RP-8 for the Rhythm delegation worker."""

from __future__ import annotations

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

    create_count = 0

    def crash(*_args, **_kwargs):
        nonlocal create_count
        create_count += 1
        raise RuntimeError("driver crashed")

    reports.clear()
    delegation_worker.DelegationWorker(client=Client(), session_factory=crash).run_claim(_job())
    assert create_count == 1
    assert reports[-1]["phase"] == "failed"

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
