"""H3 — the dispatcher actually launches the configured worker command.

H1/H2 added the config key and the helpers; nothing called them. This pins the
wiring in `_default_spawn` plus the dispatch-time cross-model gate.

Two invariants:
  1. A card whose assignee has a `worker_command` is launched with THAT argv,
     in the card's workspace, with the same HERMES_KANBAN_* env a Hermes worker
     gets — because write-back goes through the `hermes kanban` CLI, which
     resolves the board from that env.
  2. A `stage=review` card is NOT spawned when its host matches the
     `stage=implement` parent it reviews. That is the cross-model invariant; it
     has to hold at DISPATCH, not merely be reported afterwards, or a
     self-review runs before anyone sees the diagnostic.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hermes_cli import kanban_db as kb


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / ".hermes"
    for prof in ("codex-builder", "opus-reviewer", "opus-orchestrator", "default"):
        (h / "profiles" / prof).mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HERMES_HOME", str(h))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    kb.init_db()
    (tmp_path / "ws").mkdir()
    return h


@pytest.fixture
def spawned(monkeypatch):
    """Capture Popen calls instead of launching anything."""
    calls = []

    class _P:
        pid = 4242

    def fake_popen(argv, **kw):
        calls.append({"argv": list(argv), "cwd": kw.get("cwd"), "env": kw.get("env") or {}})
        return _P()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    return calls


CMDS = {
    "codex-builder": ["/opt/homebrew/bin/codex", "exec", "-s", "workspace-write",
                      "-C", "{workspace}", "--", "kanban task {task_id}"],
    "opus-reviewer": ["/usr/local/bin/claude", "-p", "review {task_id}"],
    "opus-orchestrator": ["/usr/local/bin/claude", "-p", "orchestrate {task_id}"],
}


def _cfg(monkeypatch, table=None):
    monkeypatch.setattr(kb, "_load_kanban_config",
                        lambda: {"worker_command": table if table is not None else CMDS})


def test_configured_assignee_launches_that_command(home, spawned, monkeypatch, tmp_path):
    _cfg(monkeypatch)
    with kb.connect_closing() as conn:
        tid = kb.create_task(conn, title="build", assignee="codex-builder",
                             workspace_kind="dir", workspace_path=str(tmp_path / "ws"))
        task = kb.get_task(conn, tid)
    pid = kb._default_spawn(task, str(tmp_path / "ws"), board="default")
    assert pid == 4242
    assert len(spawned) == 1
    argv = spawned[0]["argv"]
    assert argv[0] == "/opt/homebrew/bin/codex"
    assert "-s" in argv and "workspace-write" in argv
    assert str(tmp_path / "ws") in argv           # {workspace} substituted
    assert f"kanban task {tid}" in argv           # {task_id} substituted
    assert "chat" not in argv                     # NOT the hermes worker


def test_worker_env_and_cwd_are_preserved_for_cli_writeback(home, spawned, monkeypatch, tmp_path):
    """Write-back is `hermes kanban ...`, which resolves the board from env."""
    _cfg(monkeypatch)
    with kb.connect_closing() as conn:
        tid = kb.create_task(conn, title="build", assignee="codex-builder",
                             workspace_kind="dir", workspace_path=str(tmp_path / "ws"))
        task = kb.get_task(conn, tid)
    kb._default_spawn(task, str(tmp_path / "ws"), board="default")
    env = spawned[0]["env"]
    assert env["HERMES_KANBAN_TASK"] == tid
    assert env["HERMES_KANBAN_BOARD"] == "default"
    assert env["HERMES_KANBAN_DB"]
    assert env["HERMES_KANBAN_WORKSPACE"] == str(tmp_path / "ws")
    assert spawned[0]["cwd"] == str(tmp_path / "ws")


def test_unconfigured_assignee_still_uses_the_hermes_worker(home, spawned, monkeypatch, tmp_path):
    _cfg(monkeypatch, {"codex-builder": ["codex", "exec"]})
    with kb.connect_closing() as conn:
        tid = kb.create_task(conn, title="x", assignee="default",
                             workspace_kind="dir", workspace_path=str(tmp_path / "ws"))
        task = kb.get_task(conn, tid)
    kb._default_spawn(task, str(tmp_path / "ws"), board="default")
    argv = spawned[0]["argv"]
    assert "chat" in argv and "-p" in argv
    assert "codex" not in argv[0]


def test_malformed_override_falls_back_to_the_hermes_worker(home, spawned, monkeypatch, tmp_path):
    _cfg(monkeypatch, {"codex-builder": []})
    with kb.connect_closing() as conn:
        tid = kb.create_task(conn, title="x", assignee="codex-builder",
                             workspace_kind="dir", workspace_path=str(tmp_path / "ws"))
        task = kb.get_task(conn, tid)
    kb._default_spawn(task, str(tmp_path / "ws"), board="default")
    assert "chat" in spawned[0]["argv"]


# --------------------------------------------------------------------------
# the cross-model gate, enforced AT DISPATCH
# --------------------------------------------------------------------------

def _pair(conn, impl_assignee, rev_assignee):
    impl = kb.create_task(
        conn, title="implement", assignee=impl_assignee,
        provenance=kb.encode_provenance(origin="decomposer", root_id="r", stage="implement"))
    with kb.write_txn(conn):
        conn.execute("UPDATE tasks SET status='done' WHERE id=?", (impl,))
    rev = kb.create_task(
        conn, title="review", assignee=rev_assignee, parents=[impl],
        provenance=kb.encode_provenance(origin="decomposer", root_id="r", stage="review"))
    return impl, rev


def test_dispatch_refuses_a_same_host_review(home, monkeypatch):
    """opus-reviewer reviewing opus-orchestrator's work = same host = refuse."""
    _cfg(monkeypatch)
    with kb.connect_closing() as conn:
        impl, rev = _pair(conn, "opus-orchestrator", "opus-reviewer")
    with kb.connect_closing() as conn:
        kb.recompute_ready(conn)
        res = kb.dispatch_once(conn, spawn_fn=lambda *a, **k: 999)
    assert rev in getattr(res, "skipped_cross_model", []), res
    with kb.connect_closing() as conn:
        assert kb.get_task(conn, rev).status != "running"


def test_dispatch_allows_a_genuine_cross_model_review(home, monkeypatch):
    _cfg(monkeypatch)
    with kb.connect_closing() as conn:
        impl, rev = _pair(conn, "codex-builder", "opus-reviewer")
    with kb.connect_closing() as conn:
        kb.recompute_ready(conn)
        res = kb.dispatch_once(conn, spawn_fn=lambda *a, **k: 999)
    assert rev not in getattr(res, "skipped_cross_model", [])
    assert rev in [s[0] for s in res.spawned], res


def test_dispatch_refuses_an_implement_on_its_contract_authors_host(home, monkeypatch):
    """Regression (found by the live negative test, 2026-08-22).

    The dispatch gate was optimised to `stage == "review"` BEFORE
    CROSS_MODEL_STAGE_PAIRS was generalised to also cover
    implement<-contract. Result: the implement rule existed in
    check_cross_model_review but was never CALLED at dispatch, so a card whose
    coder shared a host with its test author spawned anyway -- the exact
    self-marking the split exists to prevent. Gate on the pair table, never on
    a hardcoded stage name.
    """
    _cfg(monkeypatch)
    with kb.connect_closing() as conn:
        con = kb.create_task(
            conn, title="contract", assignee="opus-reviewer",
            provenance=kb.encode_provenance(origin="decomposer", root_id="r", stage="contract"))
        with kb.write_txn(conn):
            conn.execute("UPDATE tasks SET status='done' WHERE id=?", (con,))
        imp = kb.create_task(
            conn, title="implement", assignee="opus-orchestrator", parents=[con],
            provenance=kb.encode_provenance(origin="decomposer", root_id="r", stage="implement"))
    with kb.connect_closing() as conn:
        kb.recompute_ready(conn)
        res = kb.dispatch_once(conn, spawn_fn=lambda *a, **k: 999)
    assert imp in res.skipped_cross_model, res
    assert imp not in [s[0] for s in res.spawned]
    with kb.connect_closing() as conn:
        assert kb.get_task(conn, imp).status != "running"


def test_the_gate_is_driven_by_the_pair_table_not_a_literal_stage():
    """Structural guard: adding a pair to CROSS_MODEL_STAGE_PAIRS must be
    enough. If the dispatch gate names a stage literally, this fails."""
    import inspect
    src = inspect.getsource(kb._dispatch_once_locked)
    assert "CROSS_MODEL_STAGE_PAIRS" in src, "dispatch gate must consult the pair table"
    assert '== "review"' not in src, "dispatch gate must not hardcode a stage name"


# --------------------------------------------------------------------------
# the manual-smoke human gate
# --------------------------------------------------------------------------
# `human-smoke` is an assignee with NO worker_command and no Hermes profile.
# The dispatcher must therefore never spawn it: the card sits visibly in
# `ready` until a person completes it. That is the manual-smoke gate, and it is
# what makes "never merged into main until manual smoke" structural rather than
# a rule someone has to remember.

def _chain_cfg(monkeypatch):
    monkeypatch.setattr(kb, "_load_kanban_config", lambda: {"worker_command": {
        "opus-orchestrator": ["claude", "-p"],
        "opus-contract":     ["claude", "-p"],
        "codex-builder":     ["codex", "exec"],
        "opus-reviewer":     ["claude", "-p"],
        "opus-triage":       ["claude", "-p"],
        "opus-recorder":     ["claude", "-p"],
        # human-smoke deliberately absent
    }})


def test_human_gate_card_is_never_spawned(home, monkeypatch):
    _chain_cfg(monkeypatch)
    with kb.connect_closing() as conn:
        gate = kb.create_task(
            conn, title="manual smoke", assignee="human-smoke",
            provenance=kb.encode_provenance(origin="decomposer", root_id="r", stage="manual-smoke"))
    with kb.connect_closing() as conn:
        res = kb.dispatch_once(conn, spawn_fn=lambda *a, **k: 999)
    assert gate not in [s[0] for s in res.spawned]
    assert gate in res.skipped_nonspawnable
    with kb.connect_closing() as conn:
        t = kb.get_task(conn, gate)
    assert t.status == "ready", "must stay visibly ready, not blocked or failed"


def test_human_gate_accrues_no_failures_across_repeated_ticks(home, monkeypatch):
    """It waits indefinitely without tripping the circuit breaker."""
    _chain_cfg(monkeypatch)
    with kb.connect_closing() as conn:
        gate = kb.create_task(
            conn, title="manual smoke", assignee="human-smoke",
            provenance=kb.encode_provenance(origin="decomposer", root_id="r", stage="manual-smoke"))
    for _ in range(5):
        with kb.connect_closing() as conn:
            kb.dispatch_once(conn, spawn_fn=lambda *a, **k: 999)
    with kb.connect_closing() as conn:
        t = kb.get_task(conn, gate)
    assert t.status == "ready"
    assert t.consecutive_failures == 0
    assert t.block_recurrences == 0


def test_record_card_cannot_run_until_the_human_completes_the_gate(home, monkeypatch):
    """This is what enforces 'no merge until manual smoke': the recording card
    -- and anything after it -- is gated behind a card only a person can close."""
    _chain_cfg(monkeypatch)
    with kb.connect_closing() as conn:
        gate = kb.create_task(conn, title="manual smoke", assignee="human-smoke",
                              provenance=kb.encode_provenance(origin="decomposer", root_id="r", stage="manual-smoke"))
        rec = kb.create_task(conn, title="record", assignee="opus-recorder", parents=[gate],
                             provenance=kb.encode_provenance(origin="decomposer", root_id="r", stage="record"))
        assert kb.get_task(conn, rec).status == "todo"
    with kb.connect_closing() as conn:
        kb.recompute_ready(conn)
        res = kb.dispatch_once(conn, spawn_fn=lambda *a, **k: 999)
    assert rec not in [s[0] for s in res.spawned]
    # a human completes the gate -> only now does record become runnable
    with kb.connect_closing() as conn:
        kb.complete_task(conn, gate, result="manual smoke PASS")
    with kb.connect_closing() as conn:
        kb.recompute_ready(conn)
        assert kb.get_task(conn, rec).status == "ready"


def test_archiving_the_gate_does_not_release_the_record_card(home, monkeypatch):
    """Cancelling the smoke gate must not look like passing it."""
    _chain_cfg(monkeypatch)
    with kb.connect_closing() as conn:
        gate = kb.create_task(conn, title="manual smoke", assignee="human-smoke",
                              provenance=kb.encode_provenance(origin="decomposer", root_id="r", stage="manual-smoke"))
        rec = kb.create_task(conn, title="record", assignee="opus-recorder", parents=[gate],
                             provenance=kb.encode_provenance(origin="decomposer", root_id="r", stage="record"))
        kb.archive_task(conn, gate)
    with kb.connect_closing() as conn:
        kb.recompute_ready(conn)
        assert kb.get_task(conn, rec).status == "todo"


def test_the_full_six_stage_chain_is_cross_model_valid(home, monkeypatch):
    """Every authorship boundary in the real chain must pass the gate."""
    _chain_cfg(monkeypatch)
    stages = [("plan", "opus-orchestrator"), ("contract", "opus-contract"),
              ("implement", "codex-builder"), ("review", "opus-reviewer"),
              ("manual-smoke", "human-smoke"), ("record", "opus-recorder")]
    with kb.connect_closing() as conn:
        prev = None
        ids = {}
        for stage, who in stages:
            tid = kb.create_task(
                conn, title=stage, assignee=who,
                parents=[prev] if prev else [],
                provenance=kb.encode_provenance(origin="decomposer", root_id="r", stage=stage))
            ids[stage] = tid
            prev = tid
        for stage, tid in ids.items():
            ok, why = kb.check_cross_model_review(conn, tid)
            assert ok, f"{stage} failed the cross-model gate: {why}"
