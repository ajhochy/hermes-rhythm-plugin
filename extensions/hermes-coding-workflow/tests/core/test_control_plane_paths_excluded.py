"""HCW's own control-plane files must not read as product mutations.

`_stage_payload_write_allowed` MANDATES that a JSON-consuming stage write its
approval payload to exactly `<worktree>/.hermes/hcw-inputs/<name>` -- there is
no other legal location. But `GitAdapter.paths()` excluded only
`.hermes/workflows/` and `.hermes/hcw-run.json`, so the files the design and
plan stages are REQUIRED to write showed up as out-of-scope mutations and the
RED gate failed every run with `red_mutation_violation`.

Observed live on run t_59196e0e: RED authored a genuinely failing spec inside
scope, yet `hcw check ... red` exited 2 because
`.hermes/hcw-inputs/approved-design.input.json` and
`approved-plan.input.json` were untracked and unmatched by the run scope.

This is not a relaxation of the mutation guard: the payload path, its name,
and its symlink-freeness are all still enforced by the plugin. It only stops
HCW's own control plane from being mistaken for product code.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hermes_coding_workflow.adapters import GitAdapter


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


def _write(root: Path, rel: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{}\n")


def test_stage_payload_inputs_are_not_reported_as_mutations(repo: Path) -> None:
    _write(repo, ".hermes/hcw-inputs/approved-design.input.json")
    _write(repo, ".hermes/hcw-inputs/approved-plan.input.json")
    g = GitAdapter(repo)
    assert g.paths(g.head()) == set()
    assert not g.dirty()


def test_existing_control_plane_exclusions_still_hold(repo: Path) -> None:
    _write(repo, ".hermes/workflows/run-1/run.json")
    _write(repo, ".hermes/hcw-run.json")
    g = GitAdapter(repo)
    assert g.paths(g.head()) == set()


def test_product_changes_are_still_reported(repo: Path) -> None:
    """The guard must not go blind: real edits still surface."""
    _write(repo, ".hermes/hcw-inputs/approved-plan.input.json")
    (repo / "app.txt").write_text("changed\n")
    (repo / "new.js").write_text("x\n")
    g = GitAdapter(repo)
    assert g.paths(g.head()) == {"app.txt", "new.js"}
    assert g.dirty()


def test_a_hermes_file_outside_the_control_plane_is_still_reported(repo: Path) -> None:
    """Only the two known control-plane locations are exempt."""
    _write(repo, ".hermes/something-else.json")
    g = GitAdapter(repo)
    assert g.paths(g.head()) == {".hermes/something-else.json"}
