from __future__ import annotations

import json
from pathlib import Path

from hermes_coding_workflow import cli


def test_check_strips_exactly_one_command_separator(monkeypatch, tmp_path: Path) -> None:
    seen = {}
    class Service:
        def __init__(self, repo): pass
        def reconcile(self, run_id): return {"id": run_id}
        def check(self, run_id, actor, kind, argv, timeout):
            seen["argv"] = argv; return {"ok": True}
    monkeypatch.setattr(cli, "WorkflowService", Service)
    monkeypatch.setattr(cli, "_repo_and_run", lambda repo, run_id: (repo, run_id))
    monkeypatch.setattr(cli.ActorContext, "from_env", classmethod(lambda cls: object()))
    assert cli.main(["check", str(tmp_path), "run-1", "red", "--", "python", "-c", "raise SystemExit(1)"]) == 0
    assert seen["argv"] == ["python", "-c", "raise SystemExit(1)"]


def test_check_parses_timeout_before_type_without_polluting_planned_argv(monkeypatch, tmp_path: Path) -> None:
    seen = {}
    class Service:
        def __init__(self, repo): pass
        def reconcile(self, run_id): return {"id": run_id}
        def check(self, run_id, actor, kind, argv, timeout):
            seen.update(kind=kind, argv=argv, timeout=timeout); return {"ok": True}
    monkeypatch.setattr(cli, "WorkflowService", Service)
    monkeypatch.setattr(cli, "_repo_and_run", lambda repo, run_id: (repo, run_id))
    monkeypatch.setattr(cli.ActorContext, "from_env", classmethod(lambda cls: object()))
    assert cli.main(["check", str(tmp_path), "run-1", "--timeout", "600", "red", "--", "python", "-c", "raise SystemExit(1)"]) == 0
    assert seen == {"kind": "red", "argv": ["python", "-c", "raise SystemExit(1)"], "timeout": 600}
