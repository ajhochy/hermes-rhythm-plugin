from __future__ import annotations

import json
from pathlib import Path

from hermes_coding_workflow import cli


def test_dispatch_worker_command_bypasses_actor_env_like_show(monkeypatch, tmp_path: Path) -> None:
    seen = {}

    class Service:
        def __init__(self, repo): pass
        def reconcile(self, run_id): return {"id": run_id}
        def dispatch_worker(self, run_id, stage, *, retry_succeeded=False):
            seen["args"] = (run_id, stage, retry_succeeded)
            return {"state": "queued", "stage": stage}

    monkeypatch.setattr(cli, "WorkflowService", Service)
    monkeypatch.setattr(cli, "_repo_and_run", lambda repo, run_id: (repo, run_id))
    monkeypatch.delenv("HERMES_PROFILE", raising=False)
    monkeypatch.delenv("HERMES_KANBAN_TASK", raising=False)
    assert cli.main(["dispatch-worker", str(tmp_path), "run-1", "red"]) == 0
    assert seen["args"] == ("run-1", "red", False)
    assert cli.main(["dispatch-worker", str(tmp_path), "run-1", "red", "--retry-succeeded"]) == 0
    assert seen["args"] == ("run-1", "red", True)


def test_amend_scope_command_passes_revision_head_and_reason(monkeypatch, tmp_path: Path) -> None:
    seen = {}
    class Service:
        def __init__(self, repo): pass
        def reconcile(self, run_id): return {"id": run_id}
        def amend_scope(self, run_id, actor, added_scope, *, reason, expected_revision, expected_head):
            seen["args"] = (run_id, actor.profile, actor.task_id, added_scope, reason, expected_revision, expected_head)
            return {"scope": added_scope}
    monkeypatch.setattr(cli, "WorkflowService", Service)
    monkeypatch.setattr(cli, "_repo_and_run", lambda repo, run_id: (repo, run_id))
    monkeypatch.setenv("HERMES_PROFILE", "dev-builder");monkeypatch.setenv("HERMES_KANBAN_TASK", "task-green")
    assert cli.main(["amend-scope",str(tmp_path),"run-1","--add-scope","plugins/github_intake/**","--reason","approved","--expected-revision","7","--expected-head","a"*40]) == 0
    assert seen["args"] == ("run-1","dev-builder","task-green",["plugins/github_intake/**"],"approved",7,"a"*40)


def test_worker_status_command_reports_terminal_state(monkeypatch, tmp_path: Path, capsys) -> None:
    class Service:
        def __init__(self, repo): pass
        def worker_status(self, run_id, stage):
            return {"run_id": run_id, "stage": stage, "state": "succeeded", "exit_code": 0}

    monkeypatch.setattr(cli, "WorkflowService", Service)
    monkeypatch.setattr(cli, "_repo_and_run", lambda repo, run_id: (repo, run_id))
    assert cli.main(["worker-status", str(tmp_path), "run-1", "red"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out == {"run_id": "run-1", "stage": "red", "state": "succeeded", "exit_code": 0}


def test_dispatch_worker_command_reports_workflow_errors_as_json_error(monkeypatch, tmp_path: Path, capsys) -> None:
    from hermes_coding_workflow.service import WorkflowError

    class Service:
        def __init__(self, repo): pass
        def dispatch_worker(self, run_id, stage, *, retry_succeeded=False):
            raise WorkflowError("unsupported_claude_stage")

    monkeypatch.setattr(cli, "WorkflowService", Service)
    monkeypatch.setattr(cli, "_repo_and_run", lambda repo, run_id: (repo, run_id))
    assert cli.main(["dispatch-worker", str(tmp_path), "run-1", "design"]) == 2
    out = json.loads(capsys.readouterr().out)
    assert out == {"error": "unsupported_claude_stage"}
