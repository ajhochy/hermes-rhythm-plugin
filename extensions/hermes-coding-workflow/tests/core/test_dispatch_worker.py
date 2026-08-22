from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from hermes_coding_workflow.contracts import PROFILES
from hermes_coding_workflow.service import ActorContext, WorkflowError, WorkflowService
from hermes_coding_workflow.store import RunStore


FAKE_CLAUDE = r'''#!/usr/bin/env python3
import json, os, sys
def main():
    if "ANTHROPIC_API_KEY" in os.environ or "ANTHROPIC_AUTH_TOKEN" in os.environ:
        sys.stderr.write("credential leaked\n")
        return 97
    marker = os.environ.get("FAKE_CLAUDE_MARKER")
    stdin_text = sys.stdin.read()
    if marker:
        with open(marker, "w") as fh:
            json.dump({
                "cwd": os.getcwd(),
                "argv": sys.argv[1:],
                "stdin": stdin_text,
                "hermes_profile": os.environ.get("HERMES_PROFILE"),
                "hermes_kanban_task": os.environ.get("HERMES_KANBAN_TASK"),
                "hermes_provider": os.environ.get("HERMES_PROVIDER"),
                "hermes_model": os.environ.get("HERMES_MODEL"),
            }, fh)
    print(json.dumps({"result": "ok"}))
    return int(os.environ.get("FAKE_CLAUDE_EXIT", "0"))
if __name__ == "__main__":
    raise SystemExit(main())
'''


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    git(root, "config", "user.email", "a@b.invalid")
    git(root, "config", "user.name", "t")
    (root / "app.txt").write_text("old\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "base")
    return root


@pytest.fixture()
def fake_claude(tmp_path: Path, monkeypatch) -> Path:
    path = tmp_path / "fake-claude"
    path.write_text(FAKE_CLAUDE)
    path.chmod(0o755)
    marker = tmp_path / "claude-marker.json"
    monkeypatch.setenv("HCW_CLAUDE_CLI", str(path))
    monkeypatch.setenv("FAKE_CLAUDE_MARKER", str(marker))
    monkeypatch.setenv("FAKE_CLAUDE_EXIT", "0")
    return marker


def stub_board(calls: list[tuple[str, ...]]):
    from hermes_coding_workflow.adapters import KanbanAdapter
    statuses: dict[str, str] = {}

    def run(argv, cwd):
        calls.append(tuple(argv))
        if "create" in argv:
            stage = argv[argv.index("create") + 1].split(": ")[-1]
            ident = "task-" + stage
            statuses[ident] = "todo"
            return subprocess.CompletedProcess(argv, 0, __import__("json").dumps({"id": ident}) if "--json" in argv else "", "")
        if "show" in argv:
            ident = argv[argv.index("show") + 1]
            return subprocess.CompletedProcess(argv, 0, __import__("json").dumps({"task": {"id": ident, "status": statuses.get(ident, "todo")}}), "")
        if "promote" in argv:
            statuses[argv[argv.index("promote") + 1]] = "ready"
            return subprocess.CompletedProcess(argv, 0, "", "")
        if "complete" in argv:
            statuses[argv[argv.index("complete") + 1]] = "done"
        return subprocess.CompletedProcess(argv, 0, "", "")

    return lambda repo_path: KanbanAdapter(repo_path, "hcw-test", run)


def payloads():
    command = [sys.executable, "-c", "import pathlib; raise SystemExit(0 if pathlib.Path('app.txt').read_text() == 'new\\n' else 1)"]
    design = {"observable_outcome": "new behavior", "requirements": [{"id": "R1", "description": "change app"}], "acceptance_criteria": ["green"], "approved": True}
    plan = {"tasks": [{"id": "one", "description": "change it", "paths": ["app.txt"], "test_command": command, "requirement_ids": ["R1"]}], "commands": {"red": {"argv": command, "requirement_ids": ["R1"]}, "green": {"argv": command, "requirement_ids": ["R1"]}, "full": {"argv": [sys.executable, "-c", "pass"], "requirement_ids": ["R1"]}, "security": {"argv": [sys.executable, "-c", "pass"], "requirement_ids": ["R1"]}, "live": {"argv": [sys.executable, "-c", "pass"], "requirement_ids": ["R1"]}}, "approved": True}
    return design, plan


def act(stage: str) -> ActorContext:
    return ActorContext(PROFILES[stage], "task-" + stage)


def ready(repo: Path):
    svc = WorkflowService(repo)
    run = svc.create_run("pkg", ["app.txt"], "run-1", "hcw-test", stub_board([])(repo))
    design, plan = payloads()
    svc.approve_design("run-1", act("design"), design)
    svc.approve_plan("run-1", act("plan"), plan)
    return svc, run


def wait_terminal(svc: WorkflowService, rid: str, stage: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = svc.worker_status(rid, stage)
        if record["state"] in {"succeeded", "failed"}:
            return record
        time.sleep(0.05)
    raise AssertionError(f"worker for stage {stage} never reached a terminal state: {svc.worker_status(rid, stage)}")


def activate_stage(repo: Path, stage: str, status: str) -> dict:
    store = RunStore(repo, "run-1")
    state = store.read()
    state["status"] = status
    state["stage_statuses"] = {
        name: ("active" if name == stage else "pending")
        for name in state["stage_statuses"]
    }
    store.write_json("run.json", state)
    return state


def test_red_check_cannot_transition_before_external_worker_succeeds(repo: Path) -> None:
    svc, _ = ready(repo)
    command = payloads()[1]["commands"]["red"]["argv"]

    with pytest.raises(WorkflowError, match="worker_not_succeeded"):
        svc.check("run-1", act("red"), "red", command)


def test_green_check_cannot_transition_before_external_worker_succeeds(repo: Path) -> None:
    svc, _ = ready(repo)
    activate_stage(repo, "green", "awaiting_green")
    command = payloads()[1]["commands"]["green"]["argv"]

    with pytest.raises(WorkflowError, match="worker_not_succeeded"):
        svc.check("run-1", act("green"), "green", command)


def test_green_commit_cannot_run_before_external_worker_succeeds(repo: Path) -> None:
    svc, _ = ready(repo)
    activate_stage(repo, "green", "awaiting_green")

    with pytest.raises(WorkflowError, match="worker_not_succeeded"):
        svc.commit("run-1", act("green"), "green candidate")


def test_quality_review_cannot_transition_before_external_worker_succeeds(repo: Path) -> None:
    svc, _ = ready(repo)
    state = activate_stage(repo, "quality-review", "awaiting_quality_review")
    reviewed_sha = git(Path(state["worktree_path"]), "rev-parse", "HEAD")
    payload = {"reviewed_sha": reviewed_sha, "decision": "approved", "findings": [], "dispositions": []}

    with pytest.raises(WorkflowError, match="worker_not_succeeded"):
        svc.review("run-1", act("quality-review"), payload)


def test_complete_cannot_transition_before_external_worker_succeeds(repo: Path) -> None:
    svc, _ = ready(repo)
    activate_stage(repo, "complete", "verified")

    with pytest.raises(WorkflowError, match="worker_not_succeeded"):
        svc.complete("run-1", act("complete"))


def test_dispatch_worker_rejects_stage_outside_the_claude_tier_map(repo: Path) -> None:
    svc, run = ready(repo)
    with pytest.raises(WorkflowError, match="unsupported_claude_stage"):
        svc.dispatch_worker("run-1", "design")


def test_dispatch_worker_rejects_inactive_stage(repo: Path) -> None:
    svc, run = ready(repo)
    with pytest.raises(WorkflowError, match="stage_not_active"):
        svc.dispatch_worker("run-1", "green")


def test_dispatch_worker_rejects_a_forged_task_id_not_matching_the_authoritative_create_intent(repo: Path) -> None:
    svc, run = ready(repo)
    store = RunStore(repo, "run-1")
    state = store.read()
    state["kanban_task_ids"]["red"] = "forged-task-id"
    state["dispatches"]["red"]["task_id"] = "forged-task-id"
    store.write_json("run.json", state)
    with pytest.raises(WorkflowError, match="dispatch_identity_mismatch"):
        svc.dispatch_worker("run-1", "red")


def test_dispatch_worker_rejects_a_dispatch_task_id_disagreeing_with_kanban_task_ids(repo: Path) -> None:
    svc, run = ready(repo)
    store = RunStore(repo, "run-1")
    state = store.read()
    state["dispatches"]["red"]["task_id"] = "forged-task-id"
    store.write_json("run.json", state)
    with pytest.raises(WorkflowError, match="dispatch_identity_mismatch"):
        svc.dispatch_worker("run-1", "red")


def test_plan_attached_stage_brief_hashes_are_persisted_in_authoritative_create_intent(repo: Path) -> None:
    ready(repo)
    store = RunStore(repo, "run-1")
    state = store.read()
    internal = store.read("internal.json")
    authoritative = internal["create_intent"]["brief_hashes"]
    for stage in ("red", "green", "quality-review", "complete"):
        assert authoritative[stage] == state["dispatches"][stage]["brief_hash"]


def test_dispatch_worker_rejects_forged_brief_hash_before_launch(repo: Path, monkeypatch) -> None:
    svc, _ = ready(repo)
    store = RunStore(repo, "run-1")
    state = store.read()
    state["dispatches"]["red"]["brief_hash"] = "b" * 64
    store.write_json("run.json", state)

    def must_not_launch(*args, **kwargs):
        raise AssertionError("subprocess launch reached before brief identity validation")

    monkeypatch.setattr("hermes_coding_workflow.service.subprocess.Popen", must_not_launch)
    with pytest.raises(WorkflowError, match="dispatch_identity_mismatch"):
        svc.dispatch_worker("run-1", "red")


def test_worker_runner_fails_terminally_when_plan_is_mutated_after_dispatch(repo: Path, fake_claude: Path) -> None:
    from hermes_coding_workflow import worker_runner
    svc, run = ready(repo)
    record = svc.dispatch_worker("run-1", "red")
    store = RunStore(repo, "run-1")
    with store.locked():
        pending = store.read_worker("red", 1, 1)
        pending = dict(pending)
        pending.update(pid=os.getpid(), state="queued")
        store.write_worker("red", 1, 1, pending)
    plan_path = repo / ".hermes" / "workflows" / "run-1" / "plan.json"
    plan = json.loads(plan_path.read_text())
    plan["content"]["tasks"][0]["description"] = "mutated after dispatch"
    plan_path.write_text(json.dumps(plan))
    rc = worker_runner.main(["worker_runner", str(repo), "run-1", "red", "1", "1"])
    assert rc == 1
    final = store.read_worker("red", 1, 1)
    assert final["state"] == "failed"
    assert final["note"] == "artifact_mutated"


@pytest.fixture()
def _inert_runner_process(monkeypatch):
    """Remove the queue-then-mutate regressions' reliance on real subprocess
    start-up timing.

    In production, `dispatch_worker` spawns a real, detached `worker_runner`
    OS process that races to acquire the run lock against anything else that
    also wants it. The three tests below additionally call `worker_runner.main`
    directly, in-process, to simulate that same detached runner finally
    getting scheduled after a concurrent mutation. Without this fixture, the
    *real* spawned process is also racing to acquire that same lock at the
    same time, and the test's assertions are only reliably correct because a
    freshly exec'd interpreter's start-up latency (tens of ms: process
    creation, site init, importing `hermes_coding_workflow`'s module graph)
    has so far always lost to the next few already-JIT-warm lines of this
    *test* process (microseconds) -- a 1-2 order of magnitude margin in
    practice, but not a guarantee under extreme scheduler contention.

    Replacing the spawned command with an inert placeholder that never
    imports `worker_runner` removes the race entirely: the real module is
    never started by anything but this test's own direct call, so there is
    no second process left that could ever acquire the lock first. This
    changes only what `dispatch_worker` spawns as its child process from this
    test's perspective; the reservation/validation/hashing logic `dispatch_worker`
    itself runs before spawning is completely unmodified.

    Only the exact `-m hermes_coding_workflow.worker_runner` launch is
    replaced. `subprocess.run` (used throughout `GitAdapter` for real `git`
    calls this fixture must not disturb) is implemented on top of
    `subprocess.Popen`, so a blanket patch would silently swallow every git
    invocation this same test still needs to make.
    """
    real_popen = subprocess.Popen
    placeholders: list[subprocess.Popen] = []

    def inert_popen(argv, **kwargs):
        if isinstance(argv, list) and argv[1:3] == ["-m", "hermes_coding_workflow.worker_runner"]:
            placeholder = real_popen([sys.executable, "-c", "import time; time.sleep(2)"], **kwargs)
            placeholders.append(placeholder)
            return placeholder
        return real_popen(argv, **kwargs)

    monkeypatch.setattr("hermes_coding_workflow.service.subprocess.Popen", inert_popen)
    yield
    for placeholder in placeholders:
        placeholder.kill()
        placeholder.wait(timeout=5)


def _steal_queued_ownership(store: RunStore, stage: str, attempt: int, worker_attempt: int) -> None:
    with store.locked():
        pending = store.read_worker(stage, attempt, worker_attempt)
        pending = dict(pending)
        pending.update(pid=os.getpid(), state="queued")
        store.write_worker(stage, attempt, worker_attempt, pending)


def _forbid_claude_launch(monkeypatch) -> None:
    """Block only the Claude CLI launch, not the real `git` calls
    `validate_controlled_worktree` makes first -- both go through the same
    shared `subprocess.run`, so an unconditional block would misfire on the
    git call and never actually prove the launch itself was skipped.
    """
    real_run = subprocess.run

    def guarded(cmd, *args, **kwargs):
        if isinstance(cmd, list) and cmd and cmd[0] == "git":
            return real_run(cmd, *args, **kwargs)
        raise AssertionError("Claude subprocess launched despite a stale/mismatched queued launch identity")

    monkeypatch.setattr("hermes_coding_workflow.worker_runner.subprocess.run", guarded)


def test_worker_runner_fails_terminally_when_stage_advances_after_dispatch_but_before_launch(
    repo: Path, fake_claude: Path, monkeypatch, _inert_runner_process
) -> None:
    from hermes_coding_workflow import worker_runner

    svc, run = ready(repo)
    svc.dispatch_worker("run-1", "red")
    store = RunStore(repo, "run-1")
    _steal_queued_ownership(store, "red", 1, 1)

    # Simulate another authorized lifecycle operation (a concurrent `check`)
    # advancing the run past `red` after `dispatch_worker` released the lock
    # but before this detached runner ever acquires it.
    state = store.read()
    state["stage_statuses"]["red"] = "completed"
    state["stage_statuses"]["green"] = "active"
    state["status"] = "awaiting_green"
    store.write_json("run.json", state)
    _forbid_claude_launch(monkeypatch)

    rc = worker_runner.main(["worker_runner", str(repo), "run-1", "red", "1", "1"])
    assert rc == 1
    final = store.read_worker("red", 1, 1)
    assert final["state"] == "failed"
    assert final["note"] == "launch_identity_mismatch"


def test_worker_runner_fails_terminally_when_run_attempt_advances_after_dispatch_but_before_launch(
    repo: Path, fake_claude: Path, monkeypatch, _inert_runner_process
) -> None:
    from hermes_coding_workflow import worker_runner

    svc, run = ready(repo)
    svc.dispatch_worker("run-1", "red")
    store = RunStore(repo, "run-1")
    _steal_queued_ownership(store, "red", 1, 1)

    # Simulate a concurrent `repair` moving the run to a fresh attempt. Red
    # is "active" again for the *new* attempt, so a check that only asked
    # "is the stage active" would wrongly let this stale attempt-1 worker
    # through -- the attempt number itself must also be revalidated.
    state = store.read()
    state["attempt"] = 2
    state["dispatches"] = {stage: {**info, "attempt": 2} for stage, info in state["dispatches"].items()}
    store.write_json("run.json", state)
    _forbid_claude_launch(monkeypatch)

    rc = worker_runner.main(["worker_runner", str(repo), "run-1", "red", "1", "1"])
    assert rc == 1
    final = store.read_worker("red", 1, 1)
    assert final["state"] == "failed"
    assert final["note"] == "launch_identity_mismatch"


def test_worker_runner_fails_terminally_when_internal_intent_disagrees_with_the_queued_brief_hash(
    repo: Path, fake_claude: Path, monkeypatch, _inert_runner_process
) -> None:
    from hermes_coding_workflow import worker_runner

    svc, run = ready(repo)
    svc.dispatch_worker("run-1", "red")
    store = RunStore(repo, "run-1")
    _steal_queued_ownership(store, "red", 1, 1)

    # Mutate only the durable authoritative intent's brief hash for this
    # stage: run.json's own dispatches/kanban_task_ids stay self-consistent
    # (so the record's own dispatch_sha256 still matches them), but the
    # durable orchestrator-written intent that `dispatch_worker` itself
    # checks before ever queuing a worker no longer agrees.
    internal = store.read("internal.json")
    internal["create_intent"]["brief_hashes"]["red"] = "f" * 64
    RunStore._atomic(store._path("internal.json"), internal)
    _forbid_claude_launch(monkeypatch)

    rc = worker_runner.main(["worker_runner", str(repo), "run-1", "red", "1", "1"])
    assert rc == 1
    final = store.read_worker("red", 1, 1)
    assert final["state"] == "failed"
    assert final["note"] == "launch_identity_mismatch"


def test_dispatch_worker_rejects_escaped_worktree(repo: Path, tmp_path: Path) -> None:
    svc, run = ready(repo)
    store = RunStore(repo, "run-1")
    state = store.read()
    state["worktree_path"] = str(tmp_path / "outside")
    (tmp_path / "outside").mkdir()
    store.write_json("run.json", state)
    with pytest.raises(WorkflowError, match="path_scope_violation"):
        svc.dispatch_worker("run-1", "red")


def test_dispatch_worker_launches_real_detached_subprocess_and_records_success(repo: Path, fake_claude: Path) -> None:
    svc, run = ready(repo)
    record = svc.dispatch_worker("run-1", "red")
    assert record["state"] == "queued"
    assert record["backend"] == "claude-code-cli"
    assert record["model"] == "claude-sonnet-4-6"
    assert record["pid"] is not None
    final = wait_terminal(svc, "run-1", "red")
    assert final["state"] == "succeeded"
    assert final["exit_code"] == 0
    marker = json.loads(fake_claude.read_text())
    assert marker["cwd"] == str(Path(run["worktree_path"]).resolve())
    assert marker["hermes_profile"] == "dev-contract"
    assert marker["hermes_kanban_task"] == run["kanban_task_ids"]["red"]
    assert marker["hermes_provider"] == "claude-code-cli"
    assert "--bare" not in marker["argv"]
    assert "--safe-mode" in marker["argv"]
    stdout_artifact = repo / final["stdout_path"]
    assert stdout_artifact.is_file()
    assert '"result": "ok"' in stdout_artifact.read_text()


def test_dispatch_worker_success_never_advances_hcw_stage_state(repo: Path, fake_claude: Path) -> None:
    svc, run = ready(repo)
    before = svc.show("run-1")
    assert before["status"] == "awaiting_red" and before["stage_statuses"]["red"] == "active"
    svc.dispatch_worker("run-1", "red")
    final = wait_terminal(svc, "run-1", "red")
    assert final["state"] == "succeeded"
    after = svc.show("run-1")
    assert after["status"] == "awaiting_red"
    assert after["stage_statuses"]["red"] == "active"
    assert after["revision"] == before["revision"]


def test_succeeded_external_worker_unlocks_the_authoritative_red_check(repo: Path, fake_claude: Path) -> None:
    svc, _ = ready(repo)
    svc.dispatch_worker("run-1", "red")
    assert wait_terminal(svc, "run-1", "red")["state"] == "succeeded"

    evidence = svc.check("run-1", act("red"), "red", payloads()[1]["commands"]["red"]["argv"])

    assert evidence["type"] == "red" and evidence["exit_code"] != 0
    assert svc.show("run-1")["status"] == "awaiting_green"


def test_dispatch_after_success_is_idempotent_and_does_not_launch_attempt_two(repo: Path, fake_claude: Path) -> None:
    svc, _ = ready(repo)
    svc.dispatch_worker("run-1", "red")
    first = wait_terminal(svc, "run-1", "red")

    repeated = svc.dispatch_worker("run-1", "red")

    assert repeated["id"] == first["id"]
    assert RunStore(repo, "run-1").latest_worker_attempt("red", 1) == 1


def test_explicit_retry_after_success_requires_a_failed_authoritative_gate(repo: Path, fake_claude: Path) -> None:
    svc, _ = ready(repo)
    activate_stage(repo, "green", "awaiting_green")
    svc.dispatch_worker("run-1", "green")
    first = wait_terminal(svc, "run-1", "green")

    with pytest.raises(WorkflowError, match="worker_retry_not_authorized"):
        svc.dispatch_worker("run-1", "green", retry_succeeded=True)
    with pytest.raises(WorkflowError, match="path_scope_violation"):
        svc.commit("run-1", act("green"), "candidate")
    retried = svc.dispatch_worker("run-1", "green", retry_succeeded=True)

    assert retried["state"] == "queued"
    assert retried["worker_attempt"] == 2
    assert retried["id"] != first["id"]
    assert wait_terminal(svc, "run-1", "green")["state"] == "succeeded"
    assert RunStore(repo, "run-1").latest_worker_attempt("green", 1) == 2
    with pytest.raises(WorkflowError, match="worker_retry_not_authorized"):
        svc.dispatch_worker("run-1", "green", retry_succeeded=True)


def test_authorized_retry_revalidates_the_succeeded_worker_artifacts(repo: Path, fake_claude: Path) -> None:
    svc, _ = ready(repo)
    activate_stage(repo, "green", "awaiting_green")
    svc.dispatch_worker("run-1", "green")
    final = wait_terminal(svc, "run-1", "green")
    with pytest.raises(WorkflowError, match="path_scope_violation"):
        svc.commit("run-1", act("green"), "candidate")
    (repo / final["stdout_path"]).write_text("tampered\n")

    with pytest.raises(WorkflowError, match="worker_not_succeeded"):
        svc.dispatch_worker("run-1", "green", retry_succeeded=True)


def test_explicit_retry_after_success_stops_at_the_worker_attempt_ceiling(repo: Path, fake_claude: Path) -> None:
    svc, _ = ready(repo)
    activate_stage(repo, "green", "awaiting_green")
    svc.dispatch_worker("run-1", "green")
    assert wait_terminal(svc, "run-1", "green")["state"] == "succeeded"
    for expected in (2, 3):
        with pytest.raises(WorkflowError, match="path_scope_violation"):
            svc.commit("run-1", act("green"), "candidate")
        assert svc.dispatch_worker("run-1", "green", retry_succeeded=True)["worker_attempt"] == expected
        assert wait_terminal(svc, "run-1", "green")["state"] == "succeeded"

    with pytest.raises(WorkflowError, match="path_scope_violation"):
        svc.commit("run-1", act("green"), "candidate")
    with pytest.raises(WorkflowError, match="worker_retry_exhausted"):
        svc.dispatch_worker("run-1", "green", retry_succeeded=True)


def test_failed_workers_also_stop_at_the_worker_attempt_ceiling(repo: Path, fake_claude: Path, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_CLAUDE_EXIT", "3")
    svc, _ = ready(repo)
    for expected in (1, 2, 3):
        assert svc.dispatch_worker("run-1", "red")["worker_attempt"] == expected
        assert wait_terminal(svc, "run-1", "red")["state"] == "failed"

    with pytest.raises(WorkflowError, match="worker_retry_exhausted"):
        svc.dispatch_worker("run-1", "red")


def test_tampered_success_artifact_relocks_the_authoritative_transition(repo: Path, fake_claude: Path) -> None:
    svc, _ = ready(repo)
    svc.dispatch_worker("run-1", "red")
    final = wait_terminal(svc, "run-1", "red")
    (repo / final["stdout_path"]).write_text("tampered\n")

    with pytest.raises(WorkflowError, match="worker_not_succeeded"):
        svc.check("run-1", act("red"), "red", payloads()[1]["commands"]["red"]["argv"])


def test_tampered_authoritative_intent_relocks_a_succeeded_worker_transition(repo: Path, fake_claude: Path) -> None:
    svc, _ = ready(repo)
    svc.dispatch_worker("run-1", "red")
    assert wait_terminal(svc, "run-1", "red")["state"] == "succeeded"
    store = RunStore(repo, "run-1")
    internal = store.read("internal.json")
    internal["create_intent"]["brief_hashes"]["red"] = "f" * 64
    RunStore._atomic(store._path("internal.json"), internal)

    with pytest.raises(WorkflowError, match="worker_not_succeeded"):
        svc.check("run-1", act("red"), "red", payloads()[1]["commands"]["red"]["argv"])


def test_dispatch_worker_records_failure_from_nonzero_exit(repo: Path, fake_claude: Path, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_CLAUDE_EXIT", "3")
    svc, run = ready(repo)
    svc.dispatch_worker("run-1", "red")
    final = wait_terminal(svc, "run-1", "red")
    assert final["state"] == "failed"
    assert final["exit_code"] == 3


def test_dispatch_worker_rejects_duplicate_live_dispatch(repo: Path, fake_claude: Path, monkeypatch) -> None:
    # Make the fake claude block so the first dispatch stays "running".
    blocker = FAKE_CLAUDE.replace("return int(os.environ.get(\"FAKE_CLAUDE_EXIT\", \"0\"))", "import time; time.sleep(5); return 0")
    fake_path = Path(os.environ["HCW_CLAUDE_CLI"])
    fake_path.write_text(blocker)
    fake_path.chmod(0o755)
    svc, run = ready(repo)
    svc.dispatch_worker("run-1", "red")
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and svc.worker_status("run-1", "red")["state"] != "running":
        time.sleep(0.02)
    assert svc.worker_status("run-1", "red")["state"] == "running"
    with pytest.raises(WorkflowError, match="worker_dispatch_in_progress"):
        svc.dispatch_worker("run-1", "red")


def test_dispatch_worker_rejects_a_preexisting_symlink_at_the_runner_log_path(repo: Path, fake_claude: Path, tmp_path: Path) -> None:
    svc, run = ready(repo)
    victim = tmp_path / "victim-runner-log.txt"
    victim.write_text("do not touch me")
    store = RunStore(repo, "run-1")
    log_path = store.worker_dir() / "red-1-1.runner-log"
    log_path.symlink_to(victim)
    with pytest.raises(WorkflowError):
        svc.dispatch_worker("run-1", "red")
    assert victim.read_text() == "do not touch me"
    assert log_path.is_symlink()


def test_dispatch_worker_worker_runner_rejects_preexisting_symlinks_at_stdout_and_stderr_artifact_paths(
    repo: Path, fake_claude: Path, tmp_path: Path
) -> None:
    svc, run = ready(repo)
    store = RunStore(repo, "run-1")
    artifacts = store.root / "artifacts"
    artifacts.mkdir(exist_ok=True)
    stdout_victim = tmp_path / "victim-stdout.txt"
    stderr_victim = tmp_path / "victim-stderr.txt"
    stdout_victim.write_text("do not touch stdout victim")
    stderr_victim.write_text("do not touch stderr victim")
    (artifacts / "worker-red-1-1-stdout.log").symlink_to(stdout_victim)
    (artifacts / "worker-red-1-1-stderr.log").symlink_to(stderr_victim)

    svc.dispatch_worker("run-1", "red")
    final = wait_terminal(svc, "run-1", "red")

    assert final["state"] == "failed"
    assert final["note"] == "path_scope_violation"
    assert stdout_victim.read_text() == "do not touch stdout victim"
    assert stderr_victim.read_text() == "do not touch stderr victim"
    assert (artifacts / "worker-red-1-1-stdout.log").is_symlink()
    assert (artifacts / "worker-red-1-1-stderr.log").is_symlink()


def test_dispatch_worker_recovers_from_a_stale_pid_record(repo: Path, fake_claude: Path) -> None:
    svc, run = ready(repo)
    store = RunStore(repo, "run-1")
    stale = {
        "schema_version": "hcw/v1", "kind": "worker", "id": "worker-run-1-red-1-1",
        "created_at": "2026-08-19T00:00:00Z", "updated_at": "2026-08-19T00:00:00Z",
        "run_id": "run-1", "stage": "red", "task_id": run["kanban_task_ids"]["red"],
        "profile": "dev-contract", "backend": "claude-code-cli", "model": "claude-sonnet-4-6",
        "attempt": 1, "worker_attempt": 1, "brief_hash": run["dispatches"]["red"]["brief_hash"],
        "worktree_path": run["worktree_path"], "pid": 999999999, "state": "running",
        "stdout_path": None, "stderr_path": None, "stdout_sha256": None, "stderr_sha256": None,
        "design_sha256": None, "plan_sha256": None, "dispatch_sha256": None,
        "process_identity": None, "exit_code": None, "note": None,
    }
    store.write_worker("red", 1, 1, stale)
    record = svc.dispatch_worker("run-1", "red")
    assert record["worker_attempt"] == 2
    final = wait_terminal(svc, "run-1", "red")
    assert final["state"] == "succeeded"
    reclaimed = store.read_worker("red", 1, 1)
    assert reclaimed["state"] == "failed" and reclaimed["note"] == "stale_process_lost"
