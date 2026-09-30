"""A failed authoritative check must leave diagnosable evidence.

`check` ran the planned command with `capture_output=True` and then raised
`unexpected_check_exit` while DISCARDING both streams, so a stage that fails
its own gate produced no record of why. Observed live on run t_9054a72c: the
verify stage failed `npm run test` three times with nothing to inspect, while
the identical command passed by hand -- an environment difference that the
captured output would have named immediately.

Requirement: capture the typed failure AND authoritative evidence. This
records the exit code and bounded stdout/stderr tails; it does not change
whether the check passes.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from hermes_coding_workflow.service import WorkflowError, WorkflowService


def git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(cwd), *args], text=True,
                          capture_output=True, check=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git("init", cwd=root)
    git("config", "user.email", "a@b.invalid", cwd=root)
    git("config", "user.name", "t", cwd=root)
    (root / "app.txt").write_text("old\n")
    git("add", ".", cwd=root)
    git("commit", "-m", "base", cwd=root)
    return root


def test_record_check_failure_writes_bounded_diagnostics(repo: Path) -> None:
    svc = WorkflowService(repo)
    store_dir = repo / ".hermes" / "workflows" / "run-1"
    store_dir.mkdir(parents=True)
    svc._record_check_failure(
        svc._store("run-1"),
        run_id="run-1", attempt=1, typ="full",
        argv=["npm", "run", "test"], returncode=2,
        stdout="o" * 10_000, stderr="e" * 10_000,
        reason="unexpected_check_exit",
    )
    path = store_dir / "check-failures.jsonl"
    assert path.exists()
    rows = [json.loads(l) for l in path.read_text().splitlines()]
    assert len(rows) == 1
    row = rows[0]
    assert row["type"] == "full"
    assert row["argv"] == ["npm", "run", "test"]
    assert row["exit_code"] == 2
    assert row["reason"] == "unexpected_check_exit"
    assert row["attempt"] == 1
    # Bounded: a runaway log must not be persisted whole.
    assert 0 < len(row["stdout_tail"]) <= 4096
    assert 0 < len(row["stderr_tail"]) <= 4096
    assert row["stdout_tail"].endswith("o")


def test_record_check_failure_appends_and_never_raises(repo: Path) -> None:
    svc = WorkflowService(repo)
    (repo / ".hermes" / "workflows" / "run-2").mkdir(parents=True)
    s = svc._store("run-2")
    for i in range(3):
        svc._record_check_failure(
            s, run_id="run-2", attempt=1, typ="live",
            argv=["x"], returncode=1, stdout="", stderr="boom",
            reason="unexpected_check_exit",
        )
    path = repo / ".hermes" / "workflows" / "run-2" / "check-failures.jsonl"
    assert len(path.read_text().splitlines()) == 3
    # Unwritable store must be swallowed: diagnostics never break a check.
    svc._record_check_failure(
        svc._store("no-such-run"), run_id="no-such-run", attempt=1,
        typ="full", argv=["x"], returncode=1, stdout="", stderr="",
        reason="unexpected_check_exit",
    )
