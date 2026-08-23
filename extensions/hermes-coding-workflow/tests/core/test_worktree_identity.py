from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hermes_coding_workflow.safety import validate_controlled_worktree


def git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(cwd), *args], text=True, capture_output=True, check=True)


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


def test_validate_controlled_worktree_accepts_a_real_git_worktree_on_the_expected_branch(repo: Path) -> None:
    worktree = repo / ".worktrees" / "hcw-run-1-1"
    git("worktree", "add", "-b", "hcw/run-1/attempt-1", str(worktree), "HEAD", cwd=repo)
    resolved = validate_controlled_worktree(repo, str(worktree), run_id="run-1", attempt=1, expected_branch="hcw/run-1/attempt-1")
    assert resolved == worktree.resolve()


def test_validate_controlled_worktree_rejects_a_plain_directory_never_registered_with_git(repo: Path) -> None:
    worktree = repo / ".worktrees" / "hcw-run-1-1"
    worktree.mkdir(parents=True)
    with pytest.raises(ValueError, match="worktree_not_registered"):
        validate_controlled_worktree(repo, str(worktree), run_id="run-1", attempt=1, expected_branch="hcw/run-1/attempt-1")


def test_validate_controlled_worktree_rejects_a_real_worktree_on_the_wrong_branch(repo: Path) -> None:
    worktree = repo / ".worktrees" / "hcw-run-1-1"
    git("worktree", "add", "-b", "some-other-branch", str(worktree), "HEAD", cwd=repo)
    with pytest.raises(ValueError, match="worktree_branch_mismatch"):
        validate_controlled_worktree(repo, str(worktree), run_id="run-1", attempt=1, expected_branch="hcw/run-1/attempt-1")


def test_validate_controlled_worktree_rejects_a_registered_worktree_under_the_wrong_hcw_name(repo: Path) -> None:
    worktree = repo / ".worktrees" / "hcw-run-1-1"
    git("worktree", "add", "-b", "hcw/run-1/attempt-1", str(worktree), "HEAD", cwd=repo)
    with pytest.raises(ValueError, match="worktree_identity_mismatch"):
        validate_controlled_worktree(repo, str(worktree), run_id="run-2", attempt=1, expected_branch="hcw/run-1/attempt-1")


def test_validate_controlled_worktree_still_rejects_escaped_and_symlinked_paths(repo: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(ValueError, match="path_scope_violation"):
        validate_controlled_worktree(repo, str(outside), run_id="run-1", attempt=1, expected_branch="hcw/run-1/attempt-1")
