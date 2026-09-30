"""HCW must never bootstrap a run inside another run's attempt worktree.

The runaway-recursion incident produced 49 cards nested at least five
worktrees deep and a workspace with EIGHT nested `.worktrees` segments,
because nothing stopped an HCW stage worker from calling `create_run` while
its own cwd was an HCW-controlled attempt worktree.

Identity here is structural: every attempt worktree carries
`.hermes/hcw-run.json` (the run locator HCW itself writes), and the
controlled path convention is `<repo>/.worktrees/hcw-<run>-<attempt>`.
Nothing is inferred from titles.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from hermes_coding_workflow.contracts import STAGES
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


class _FakeBoard:
    """Records every card creation so a test can prove NONE happened."""

    def __init__(self, board: str = "default") -> None:
        self.board = board
        self.home = None
        self.created: list[str] = []
        self.blocked: list[str] = []
        self.last_briefs: dict[str, dict] = {}

    def ensure_board(self):
        return {"board": self.board}

    def graph(self, run_id, branch, workspace, profiles, **kw):
        made = {}
        for i, stage in enumerate(STAGES):
            tid = f"t_fake{i}"
            self.created.append(tid)
            self.last_briefs[stage] = {"body": "{}", "sha256": "0" * 64}
            made[stage] = tid
        return made

    def comment(self, task_id, body):
        return "0" * 64

    def complete(self, task_id, stage):
        return None

    def block(self, task_id, reason, kind="capability"):
        self.blocked.append(task_id)
        return None

    def delete(self, task_id):
        return None


def _attempt_worktree(repo: Path, run_id: str = "outer", attempt: int = 1) -> Path:
    """Materialise a real HCW-shaped attempt worktree under ``repo``."""
    wt = repo / ".worktrees" / f"hcw-{run_id}-{attempt}"
    git("worktree", "add", "-b", f"hcw/{run_id}/attempt-{attempt}", str(wt),
        "HEAD", cwd=repo)
    loc = wt / ".hermes" / "hcw-run.json"
    loc.parent.mkdir(parents=True, exist_ok=True)
    loc.write_text(json.dumps({
        "schema_version": "hcw/v1", "run_id": run_id,
        "repo_root": str(repo), "worktree_path": str(wt.resolve()),
    }, sort_keys=True) + "\n")
    git("add", "-A", cwd=wt)
    git("-c", "user.email=a@b.invalid", "-c", "user.name=t",
        "commit", "-m", "locator", cwd=wt)
    return wt


def test_create_run_refuses_inside_an_hcw_attempt_worktree(repo: Path) -> None:
    """Matrix 4: an HCW stage cannot bootstrap another HCW run."""
    inner = _attempt_worktree(repo)
    board = _FakeBoard()
    svc = WorkflowService(inner)
    with pytest.raises(WorkflowError) as excinfo:
        svc.create_run("pkg", ["app.txt"], "inner", "default", kanban=board)
    assert excinfo.value.code == "nested_workflow_forbidden"
    assert board.created == [], "no cards may be created"
    assert not (inner / ".worktrees").exists(), "no worktree may be created"


def test_create_run_refuses_when_the_repo_path_nests_worktrees_too_deep(
    repo: Path, tmp_path: Path,
) -> None:
    """Matrix 9: depth violations fail before filesystem or board mutation."""
    deep = repo / ".worktrees" / "hcw-a-1" / ".worktrees" / "hcw-b-1"
    deep.mkdir(parents=True)
    git("init", cwd=deep)
    git("config", "user.email", "a@b.invalid", cwd=deep)
    git("config", "user.name", "t", cwd=deep)
    (deep / "app.txt").write_text("x\n")
    git("add", ".", cwd=deep)
    git("commit", "-m", "b", cwd=deep)
    board = _FakeBoard()
    svc = WorkflowService(deep)
    with pytest.raises(WorkflowError) as excinfo:
        svc.create_run("pkg", ["app.txt"], "inner2", "default", kanban=board)
    assert excinfo.value.code == "workflow_depth_exceeded"
    assert board.created == []


def test_create_run_still_works_from_a_normal_repo(repo: Path) -> None:
    """Matrix 14: an ordinary run is unaffected by the guards."""
    board = _FakeBoard()
    svc = WorkflowService(repo)
    run = svc.create_run("pkg", ["app.txt"], "ok-run", "default", kanban=board)
    assert run["id"] == "ok-run"
    assert set(run["kanban_task_ids"]) == set(STAGES)
    assert (repo / ".worktrees" / "hcw-ok-run-1").is_dir()


def test_exact_replay_of_create_run_converges_on_one_graph(repo: Path) -> None:
    """Matrix 5: an existing root/run replay is idempotent."""
    board = _FakeBoard()
    svc = WorkflowService(repo)
    first = svc.create_run("pkg", ["app.txt"], "idem", "default", kanban=board)
    made = len(board.created)
    svc2 = WorkflowService(repo)
    with pytest.raises(WorkflowError) as excinfo:
        svc2.create_run("pkg", ["app.txt"], "idem", "default", kanban=board)
    assert excinfo.value.code == "run_exists"
    assert len(board.created) == made, "replay must not create more cards"
    assert first["kanban_task_ids"]


def test_conflicting_replay_creates_no_new_cards_or_worktrees(repo: Path) -> None:
    """Matrix 6: a CONFLICTING replay fails closed with no new artifacts."""
    board = _FakeBoard()
    svc = WorkflowService(repo)
    svc.create_run("pkg", ["app.txt"], "conflict", "default", kanban=board)
    made = len(board.created)
    worktrees_before = sorted(p.name for p in (repo / ".worktrees").iterdir())
    with pytest.raises(WorkflowError):
        # Same run id, DIFFERENT scope -> conflicting intent.
        WorkflowService(repo).create_run(
            "pkg", ["other.txt"], "conflict", "default", kanban=board,
        )
    assert len(board.created) == made
    assert sorted(p.name for p in (repo / ".worktrees").iterdir()) == worktrees_before


def test_stage_cards_are_stamped_with_workflow_provenance(repo: Path) -> None:
    """Requirement 3: identity travels as structured provenance, so the
    Kanban decomposer can refuse a stage without parsing its title."""
    from hermes_coding_workflow.adapters import KanbanAdapter

    calls: list[tuple] = []

    def runner(argv, cwd):
        calls.append(tuple(argv))
        return subprocess.CompletedProcess(
            list(argv), 0, stdout=json.dumps({"id": f"t_{len(calls)}"}), stderr="",
        )

    adapter = KanbanAdapter(repo, "default", runner=runner)
    adapter.graph("run-9", "hcw/run-9/attempt-1", repo / ".worktrees" / "hcw-run-9-1",
                  {s: "dev-x" for s in STAGES}, attempt=1, scope=["app.txt"],
                  goal="do a thing")
    creates = [c for c in calls if "create" in c]
    assert len(creates) == len(STAGES)
    for argv in creates:
        assert "--provenance" in argv, argv
        payload = json.loads(argv[argv.index("--provenance") + 1])
        assert payload["origin"] == "workflow"
        assert payload["run_id"] == "run-9"
        assert payload["attempt"] == 1
        assert payload["stage"] in STAGES


# --------------------------------------------------------------------------
# Bounded same-run repair (matrix 7 / 8)
# --------------------------------------------------------------------------

def test_repair_ceiling_blocks_one_root_without_fanning_out(repo: Path) -> None:
    """Matrix 8: once the repair ceiling is reached HCW must block ONE card on
    the canonical run and refuse to build another attempt graph."""
    from hermes_coding_workflow.contracts import MAX_ATTEMPTS

    board = _FakeBoard()
    svc = WorkflowService(repo)
    run = svc.create_run("pkg", ["app.txt"], "ceil", "default", kanban=board)
    made = len(board.created)

    store = svc._store("ceil")
    with store.locked():
        current = store.read()
        base = current["base_sha"]
        current["attempt_history"] = [
            {"attempt": n, "worktree_path": str(repo / ".worktrees" / f"hcw-ceil-{n}"),
             "head_sha": base, "attempt_base_sha": base}
            for n in range(1, MAX_ATTEMPTS)
        ]
        current["attempt"] = MAX_ATTEMPTS
        current["attempt_base_sha"] = base
        store.write_json("run.json", current)

    with pytest.raises(WorkflowError) as excinfo:
        svc._assert_repair_budget(store.read(), board)
    assert excinfo.value.code == "repair_ceiling_reached"
    # Exactly one card blocked, zero new cards.
    assert len(board.created) == made
    assert board.blocked == [run["kanban_task_ids"]["design"]]
    assert store.read()["status"] == "blocked_setup"


def test_repair_budget_allows_attempts_below_the_ceiling(repo: Path) -> None:
    """Matrix 7: a typed stage failure below the ceiling still repairs the
    SAME run rather than blocking or forking."""
    board = _FakeBoard()
    svc = WorkflowService(repo)
    svc.create_run("pkg", ["app.txt"], "under", "default", kanban=board)
    store = svc._store("under")
    svc._assert_repair_budget(store.read(), board)  # must not raise
    assert board.blocked == []
