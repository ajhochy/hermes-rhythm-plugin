"""Regressions for the Kanban runaway-recursion incident.

The observed failure topology was:

    user root -> auto-decompose -> child assigned to the HCW orchestrator
      -> HCW creates its stage graph -> a stage blocks -> block-loop routes
      it to `triage` -> auto-decompose eats the STAGE -> another HCW run
      inside the first one -> repeat.

285 cards, 84 active, 9 concurrent workers, 8 nested `.worktrees`
segments. Every test here pins one link in that chain.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_cli import kanban_db as kb
from hermes_cli import kanban_decompose as decomp


@pytest.fixture
def kanban_home(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    kb.init_db()
    return home


def _mk(conn, **kw):
    kw.setdefault("title", "t")

    if kw.pop("triage", True):
        kw["triage"] = True
    return kb.create_task(conn, **kw)


# --------------------------------------------------------------------------
# 1-3, 6: decomposition eligibility is provenance-based
# --------------------------------------------------------------------------

def test_plain_user_root_is_decompose_eligible(kanban_home):
    """Matrix 1: a normal user root can still be decomposed once."""
    with kb.connect_closing() as conn:
        tid = _mk(conn, title="Add a thing")
        ok, reason = kb.decompose_eligibility(conn, tid)
    assert ok, reason


def test_decomposer_child_is_not_eligible(kanban_home):
    """Matrix 2: an auto-decomposer child cannot be decomposed."""
    with kb.connect_closing() as conn:
        root = _mk(conn, title="root")
        child = _mk(
            conn, title="child",
            provenance=kb.encode_provenance(origin="decomposer", root_id=root),
        )
        ok, reason = kb.decompose_eligibility(conn, child)
    assert not ok
    assert reason == "decomposer_child"


def test_workflow_stage_is_not_eligible(kanban_home):
    """Matrix 3: an HCW-generated stage card cannot be decomposed."""
    with kb.connect_closing() as conn:
        stage = _mk(
            conn, title="Write failing tests: x",
            provenance=kb.encode_provenance(
                origin="workflow", run_id="r_1", stage="red",
                attempt=1, package_id="t_c118913c",
            ),
        )
        ok, reason = kb.decompose_eligibility(conn, stage)
    assert not ok
    assert reason == "workflow_stage"


def test_hcw_idempotency_key_alone_blocks_decomposition(kanban_home):
    """Belt-and-braces: a stage card created by an older HCW runtime that
    predates provenance plumbing is still recognised by its namespaced
    idempotency key. Identity comes from structure, never the title."""
    with kb.connect_closing() as conn:
        stage = _mk(
            conn, title="Implement: whatever",
            idempotency_key="hcw:r_1:attempt-1:green",
        )
        ok, reason = kb.decompose_eligibility(conn, stage)
    assert not ok
    assert reason == "workflow_stage"


def test_task_inside_workflow_worktree_is_not_eligible(kanban_home, tmp_path):
    wt = tmp_path / "repo" / ".worktrees" / "hcw-r_1-1"
    with kb.connect_closing() as conn:
        tid = _mk(
            conn, title="something",
            workspace_kind="worktree", workspace_path=str(wt),
        )
        ok, reason = kb.decompose_eligibility(conn, tid)
    assert not ok
    assert reason == "inside_workflow_worktree"


def test_block_looped_task_is_not_eligible(kanban_home):
    """A card routed to triage by `block_loop_detected` is there for a HUMAN
    decision. Decomposing it is the exact bug that turned one blocked stage
    into a new workflow."""
    with kb.connect_closing() as conn:
        tid = _mk(conn, title="root")
        with kb.write_txn(conn):
            kb._append_event(conn, tid, "block_loop_detected", {"reason": "x"})
        ok, reason = kb.decompose_eligibility(conn, tid)
    assert not ok
    assert reason == "block_loop_routed"


def test_already_decomposed_task_is_not_eligible(kanban_home):
    with kb.connect_closing() as conn:
        root = _mk(conn, title="root")
        child = _mk(conn, title="child")
        kb.link_tasks(conn, root, child)
        ok, reason = kb.decompose_eligibility(conn, root)
    assert not ok
    assert reason == "already_decomposed"


def test_list_triage_ids_for_decompose_filters_ineligible(kanban_home):
    """The gateway auto-decompose tick must consume a FILTERED list, not
    every row in the triage column."""
    with kb.connect_closing() as conn:
        user_root = _mk(conn, title="user root")
        _mk(conn, title="stage", idempotency_key="hcw:r_1:attempt-1:red")
        _mk(conn, title="child",
            provenance=kb.encode_provenance(origin="decomposer", root_id=user_root))
    assert decomp.list_decomposable_ids() == [user_root]


def test_decomposer_stamps_child_provenance(kanban_home):
    with kb.connect_closing() as conn:
        root = _mk(conn, title="root")
        kids = kb.decompose_triage_task(
            conn, root, root_assignee="orch",
            children=[{"title": "a", "parents": []}, {"title": "b", "parents": []}],
        )
    assert kids and len(kids) == 2
    with kb.connect_closing() as conn:
        for kid in kids:
            prov = kb.task_provenance(conn, kid)
            assert prov.get("origin") == "decomposer"
            assert prov.get("root_id") == root


# --------------------------------------------------------------------------
# 4/9: bounded workflow depth, enforced before any board mutation
# --------------------------------------------------------------------------

def test_workspace_depth_violation_rejected_before_board_mutation(kanban_home, tmp_path):
    """Matrix 9: depth violations fail before filesystem or board writes."""
    deep = tmp_path / "repo"
    for i in range(3):
        deep = deep / ".worktrees" / f"hcw-r{i}-1"
    with kb.connect_closing() as conn:
        before = len(kb.list_tasks(conn, limit=1000))
        with pytest.raises(ValueError, match="workspace_depth_exceeded"):
            kb.create_task(
                conn, title="too deep", workspace_kind="worktree",
                workspace_path=str(deep),
            )
        assert len(kb.list_tasks(conn, limit=1000)) == before


def test_single_controlled_worktree_depth_is_allowed(kanban_home, tmp_path):
    ok_path = tmp_path / "repo" / ".worktrees" / "hcw-r_1-1"
    with kb.connect_closing() as conn:
        tid = kb.create_task(
            conn, title="fine", workspace_kind="worktree",
            workspace_path=str(ok_path),
        )
    assert tid


# --------------------------------------------------------------------------
# 11: archive/cancel must not release descendants
# --------------------------------------------------------------------------

def test_archived_parent_does_not_release_child(kanban_home):
    """Matrix 11: partial archive cannot cause unexpected dispatch."""
    with kb.connect_closing() as conn:
        parent = kb.create_task(conn, title="parent")
        child = kb.create_task(conn, title="child", parents=[parent],
                              )
        assert kb.get_task(conn, child).status == "todo"
        kb.archive_task(conn, parent)
    with kb.connect_closing() as conn:
        kb.recompute_ready(conn)
        assert kb.get_task(conn, child).status == "todo"
        assert not kb._parents_satisfied(conn, child)


def test_cancel_subtree_archives_full_descendant_closure(kanban_home):
    with kb.connect_closing() as conn:
        root = kb.create_task(conn, title="root")
        mid = kb.create_task(conn, title="mid", parents=[root])
        leaf = kb.create_task(conn, title="leaf", parents=[mid])
        n = kb.cancel_subtree(conn, root, reason="smoke cleanup")
    assert n == 3
    with kb.connect_closing() as conn:
        for tid in (root, mid, leaf):
            assert kb.get_task(conn, tid).status == "archived"


# --------------------------------------------------------------------------
# 6/10: concurrency caps are schema-backed, not "accepted but ignored"
# --------------------------------------------------------------------------

def test_concurrency_and_promotion_keys_are_registered_in_the_schema():
    """`hermes config get` echoing a key is not proof it is enforced. Both of
    these are documented and read at runtime but were absent from the
    defaults schema, so config.yaml accepted them with an
    'unrecognized key' warning."""
    from hermes_cli.config_defaults import DEFAULT_CONFIG

    kanban = DEFAULT_CONFIG["kanban"]
    assert "max_in_progress" in kanban
    assert "auto_promote_children" in kanban


def _home_with_profiles(monkeypatch, *profiles):
    import os, sys, tempfile
    home = tempfile.mkdtemp(prefix="kanban_recursion_guard_")
    for prof in (*profiles, "default"):
        os.makedirs(os.path.join(home, "profiles", prof), exist_ok=True)
    monkeypatch.setenv("HERMES_HOME", home)
    for mod in list(sys.modules):
        if mod.startswith("hermes_cli") or mod.startswith("hermes_state") or mod == "hermes_constants":
            del sys.modules[mod]
    from hermes_cli import kanban_db
    return kanban_db


def test_global_cap_is_enforced_atomically_across_dispatch(monkeypatch):
    """Matrix 10 (global): with max_in_progress=2, one tick spawns at most
    two, and a SECOND tick while those two are still running spawns none.
    Real spawns (not dry_run) so the running-count read is the same one the
    live dispatcher does."""
    kbx = _home_with_profiles(monkeypatch, "alpha", "beta", "gamma")
    with kbx.connect_closing() as conn:
        kbx.create_board(slug="default", name="Test")
        for prof in ("alpha", "beta", "gamma"):
            for i in range(3):
                kbx.create_task(conn, title=f"{prof}{i}", assignee=prof)
    with kbx.connect_closing() as conn:
        first = kbx.dispatch_once(conn, spawn_fn=lambda *a, **k: 4321,
                                  max_in_progress=2)
    assert len(first.spawned) == 2, first
    with kbx.connect_closing() as conn:
        running = [t for t in kbx.list_tasks(conn, limit=1000)
                   if t.status == "running"]
        assert len(running) == 2
        second = kbx.dispatch_once(conn, spawn_fn=lambda *a, **k: 4322,
                                   max_in_progress=2)
    assert second.spawned == [], second
    with kbx.connect_closing() as conn:
        running = [t for t in kbx.list_tasks(conn, limit=1000)
                   if t.status == "running"]
    assert len(running) == 2


def test_per_profile_cap_composes_with_global_cap(monkeypatch):
    """Matrix 10 (per-profile): global 2 + per-profile 1 -> exactly two
    spawns, on two DIFFERENT profiles."""
    kbx = _home_with_profiles(monkeypatch, "alpha", "beta")
    with kbx.connect_closing() as conn:
        kbx.create_board(slug="default", name="Test")
        for i in range(4):
            kbx.create_task(conn, title=f"a{i}", assignee="alpha")
        for i in range(4):
            kbx.create_task(conn, title=f"b{i}", assignee="beta")
    with kbx.connect_closing() as conn:
        res = kbx.dispatch_once(
            conn, spawn_fn=lambda *a, **k: 5555,
            max_in_progress=2, max_in_progress_per_profile=1,
        )
    assignees = sorted(s[1] for s in res.spawned)
    assert assignees == ["alpha", "beta"], res


# --------------------------------------------------------------------------
# 12: semantic board diagnostics
# --------------------------------------------------------------------------

def test_diagnostics_flags_stage_that_owns_a_workflow_run(kanban_home):
    with kb.connect_closing() as conn:
        stage = _mk(conn, title="stage",
                    provenance=kb.encode_provenance(
                        origin="workflow", run_id="r_1", stage="red", attempt=1))
        nested = _mk(conn, title="nested root",
                     provenance=kb.encode_provenance(
                         origin="workflow", run_id="r_2", stage="design",
                         attempt=1, parent_run="r_1"))
        kb.link_tasks(conn, stage, nested)
        found = kb.board_diagnostics(conn)
    kinds = {d.kind for d in found}
    assert "workflow_recursion" in kinds
    hit = next(d for d in found if d.kind == "workflow_recursion")
    assert stage in hit.detail or stage in (hit.task_ids or [])


def test_diagnostics_flags_duplicate_canonical_roots(kanban_home):
    with kb.connect_closing() as conn:
        kb.create_task(conn, title="r1", idempotency_key="e2e:thing:v1",
                      )
        # Simulate the pre-fix duplicate-root state: same canonical key,
        # two live roots.
        with kb.write_txn(conn):
            conn.execute(
                "INSERT INTO tasks (id,title,status,created_at,workspace_kind,"
                "idempotency_key) VALUES ('t_dupe','r2','ready',1,'scratch',"
                "'e2e:thing:v1')"
            )
        found = kb.board_diagnostics(conn)
    assert "duplicate_canonical_root" in {d.kind for d in found}


def test_diagnostics_flags_excessive_workflow_depth(kanban_home, tmp_path):
    deep = tmp_path / "repo"
    for i in range(3):
        deep = deep / ".worktrees" / f"hcw-r{i}-1"
    with kb.connect_closing() as conn:
        with kb.write_txn(conn):
            conn.execute(
                "INSERT INTO tasks (id,title,status,created_at,workspace_kind,"
                "workspace_path) VALUES ('t_deep','d','ready',1,'worktree',?)",
                (str(deep),),
            )
        found = kb.board_diagnostics(conn)
    assert "workspace_depth_exceeded" in {d.kind for d in found}


def test_diagnostics_flags_decomposed_blocked_stage(kanban_home):
    with kb.connect_closing() as conn:
        stage = _mk(conn, title="stage",
                    provenance=kb.encode_provenance(
                        origin="workflow", run_id="r_1", stage="red", attempt=1))
        kid = _mk(conn, title="kid",
                  provenance=kb.encode_provenance(origin="decomposer", root_id=stage))
        kb.link_tasks(conn, stage, kid)
        found = kb.board_diagnostics(conn)
    assert "decomposed_workflow_stage" in {d.kind for d in found}


def test_diagnostics_flags_orphaned_descendants_of_archived_parent(kanban_home):
    with kb.connect_closing() as conn:
        parent = kb.create_task(conn, title="p")
        child = kb.create_task(conn, title="c", parents=[parent],
                              )
        with kb.write_txn(conn):
            conn.execute("UPDATE tasks SET status='archived' WHERE id=?", (parent,))
            conn.execute("UPDATE tasks SET status='ready' WHERE id=?", (child,))
        found = kb.board_diagnostics(conn)
    assert "orphaned_gated_descendant" in {d.kind for d in found}


def test_diagnostics_flags_stage_workspace_mismatch(kanban_home, tmp_path):
    """A stage whose workspace does not match its run's authoritative
    worktree is identity contamination — the t_5a65dde9 shape."""
    with kb.connect_closing() as conn:
        a = _mk(conn, title="red", workspace_kind="worktree",
                workspace_path=str(tmp_path / "repo" / ".worktrees" / "hcw-r_1-1"),
                provenance=kb.encode_provenance(
                    origin="workflow", run_id="r_1", stage="red", attempt=1))
        b = _mk(conn, title="green", workspace_kind="worktree",
                workspace_path=str(tmp_path / "other" / ".worktrees" / "hcw-r_1-1"),
                provenance=kb.encode_provenance(
                    origin="workflow", run_id="r_1", stage="green", attempt=1))
        found = kb.board_diagnostics(conn)
    assert "workflow_workspace_mismatch" in {d.kind for d in found}
    assert a and b
