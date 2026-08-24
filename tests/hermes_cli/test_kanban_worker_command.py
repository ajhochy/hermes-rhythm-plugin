"""`kanban.worker_command` — let the dispatcher launch a non-Hermes worker.

The dispatcher hardcoded `hermes -p <profile> chat -q "work kanban task <id>"`,
so the only way to do coding work on a card was a Hermes agent session. That
forces one 9.8k-system-prompt bootstrap per card and rules out driving the
Claude Code / Codex agent-stack chain from the board.

`worker_command` maps an ASSIGNEE to an argv template. The board therefore
decides which host runs a card, and the model has no say — which is what makes
"this model wrote it, the other model reviews it" an invariant of the graph
rather than an instruction a model can ignore. (It can: on 2026-08-22 the HCW
planner pinned a command the card body explicitly and repeatedly forbade.)

Everything else about dispatch is unchanged: claim locks, concurrency caps,
stale/crash recovery, retries and the per-task log all still apply.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from hermes_cli import kanban_db as kb


@pytest.fixture
def kanban_home(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    (home / "profiles" / "default").mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    kb.init_db()
    return home


# --------------------------------------------------------------------------
# schema + resolution
# --------------------------------------------------------------------------

def test_worker_command_is_registered_in_the_config_schema():
    from hermes_cli.config_defaults import DEFAULT_CONFIG
    assert "worker_command" in DEFAULT_CONFIG["kanban"]


def test_no_override_configured_returns_none(kanban_home, monkeypatch):
    monkeypatch.setattr(kb, "_load_kanban_config", lambda: {})
    assert kb.worker_command_for("codex-builder") is None


def test_override_for_the_assignee_is_returned(kanban_home, monkeypatch):
    monkeypatch.setattr(kb, "_load_kanban_config", lambda: {
        "worker_command": {"codex-builder": ["codex", "exec", "{task_id}"]},
    })
    assert kb.worker_command_for("codex-builder") == ["codex", "exec", "{task_id}"]


def test_an_assignee_without_an_override_falls_through(kanban_home, monkeypatch):
    monkeypatch.setattr(kb, "_load_kanban_config", lambda: {
        "worker_command": {"codex-builder": ["codex", "exec"]},
    })
    assert kb.worker_command_for("opus-reviewer") is None


@pytest.mark.parametrize("bad", [
    {"codex-builder": []},              # empty argv
    {"codex-builder": "codex exec"},    # string, not a list
    {"codex-builder": [""]},            # blank executable
    {"codex-builder": ["codex", 7]},    # non-string member
])
def test_malformed_overrides_fail_closed(kanban_home, monkeypatch, bad):
    """A bad template must not spawn something arbitrary — it must be
    ignored, so the card stays queued and the operator sees it."""
    monkeypatch.setattr(kb, "_load_kanban_config", lambda: {"worker_command": bad})
    assert kb.worker_command_for("codex-builder") is None


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def test_placeholders_are_substituted(kanban_home):
    argv = kb.render_worker_command(
        ["run", "--task", "{task_id}", "--cwd", "{workspace}",
         "--board", "{board}", "--role", "{assignee}"],
        task_id="t_abc", workspace="/tmp/ws", board="default",
        assignee="codex-builder",
    )
    assert argv == ["run", "--task", "t_abc", "--cwd", "/tmp/ws",
                    "--board", "default", "--role", "codex-builder"]


def test_unknown_placeholders_are_left_alone(kanban_home):
    """A literal brace in a command must not explode the render."""
    argv = kb.render_worker_command(
        ["sh", "-c", "echo {not_a_placeholder} {task_id}"],
        task_id="t_1", workspace="/w", board="b", assignee="a",
    )
    assert argv == ["sh", "-c", "echo {not_a_placeholder} t_1"]


# --------------------------------------------------------------------------
# host identity — derived from the command, so there is one source of truth
# --------------------------------------------------------------------------

def test_host_is_derived_from_the_command_not_extra_config(kanban_home, monkeypatch):
    monkeypatch.setattr(kb, "_load_kanban_config", lambda: {"worker_command": {
        "opus-orchestrator": ["/Users/x/.local/bin/claude", "-p", "{task_id}"],
        "codex-builder": ["/opt/homebrew/bin/codex", "exec"],
    }})
    assert kb.worker_host_for("opus-orchestrator") == "claude"
    assert kb.worker_host_for("codex-builder") == "codex"


def test_host_without_an_override_is_hermes(kanban_home, monkeypatch):
    monkeypatch.setattr(kb, "_load_kanban_config", lambda: {})
    assert kb.worker_host_for("dev-builder") == "hermes"


# --------------------------------------------------------------------------
# the cross-model invariant
# --------------------------------------------------------------------------

def _hosts(monkeypatch):
    monkeypatch.setattr(kb, "_load_kanban_config", lambda: {"worker_command": {
        "opus-orchestrator": ["claude", "-p"],
        "opus-reviewer": ["claude", "-p"],
        "codex-builder": ["codex", "exec"],
    }})


def test_review_card_on_a_different_host_is_accepted(kanban_home, monkeypatch):
    _hosts(monkeypatch)
    with kb.connect_closing() as conn:
        impl = kb.create_task(
            conn, title="implement", assignee="codex-builder",
            provenance=kb.encode_provenance(origin="decomposer", root_id="r", stage="implement"),
        )
        rev = kb.create_task(
            conn, title="review", assignee="opus-reviewer", parents=[impl],
            provenance=kb.encode_provenance(origin="decomposer", root_id="r", stage="review"),
        )
        ok, reason = kb.check_cross_model_review(conn, rev)
    assert ok, reason


def test_review_card_on_the_same_host_as_the_implementer_is_rejected(kanban_home, monkeypatch):
    """The whole point: the reviewer must not be the author's model."""
    _hosts(monkeypatch)
    with kb.connect_closing() as conn:
        impl = kb.create_task(
            conn, title="implement", assignee="opus-orchestrator",
            provenance=kb.encode_provenance(origin="decomposer", root_id="r", stage="implement"),
        )
        rev = kb.create_task(
            conn, title="review", assignee="opus-reviewer", parents=[impl],
            provenance=kb.encode_provenance(origin="decomposer", root_id="r", stage="review"),
        )
        ok, reason = kb.check_cross_model_review(conn, rev)
    assert not ok
    assert reason == "same_host_as_author"


def test_non_review_cards_are_not_constrained(kanban_home, monkeypatch):
    _hosts(monkeypatch)
    with kb.connect_closing() as conn:
        a = kb.create_task(conn, title="a", assignee="codex-builder",
                           provenance=kb.encode_provenance(
                               origin="decomposer", root_id="r", stage="implement"))
        b = kb.create_task(conn, title="b", assignee="codex-builder", parents=[a],
                           provenance=kb.encode_provenance(
                               origin="decomposer", root_id="r", stage="implement"))
        ok, _ = kb.check_cross_model_review(conn, b)
    assert ok


def test_diagnostics_flag_a_same_host_review(kanban_home, monkeypatch):
    _hosts(monkeypatch)
    with kb.connect_closing() as conn:
        impl = kb.create_task(conn, title="implement", assignee="opus-orchestrator",
                              provenance=kb.encode_provenance(
                                  origin="decomposer", root_id="r", stage="implement"))
        kb.create_task(conn, title="review", assignee="opus-reviewer", parents=[impl],
                       provenance=kb.encode_provenance(
                           origin="decomposer", root_id="r", stage="review"))
        found = kb.board_diagnostics(conn)
    kinds = {d.kind for d in found}
    assert "cross_model_review_violation" in kinds


def test_diagnostics_stay_quiet_on_a_correct_cross_model_graph(kanban_home, monkeypatch):
    _hosts(monkeypatch)
    with kb.connect_closing() as conn:
        impl = kb.create_task(conn, title="implement", assignee="codex-builder",
                              provenance=kb.encode_provenance(
                                  origin="decomposer", root_id="r", stage="implement"))
        kb.create_task(conn, title="review", assignee="opus-reviewer", parents=[impl],
                       provenance=kb.encode_provenance(
                           origin="decomposer", root_id="r", stage="review"))
        found = kb.board_diagnostics(conn)
    assert "cross_model_review_violation" not in {d.kind for d in found}


# --------------------------------------------------------------------------
# contract-author != implementer  (the self-marking guard)
# --------------------------------------------------------------------------
# `acceptance-contract` authors a test that must FAIL before implementation.
# If the same model then writes the code, it can satisfy the spec by weakening
# the spec -- the coding-agent skill names this exact failure mode ("I'll make
# the contract test pass by mocking the thing it checks"). Putting the test
# author on a different host removes the ABILITY, not just the temptation:
# any edit to a test it does not own shows up in the diff the reviewer reads.

def _roles(monkeypatch):
    monkeypatch.setattr(kb, "_load_kanban_config", lambda: {"worker_command": {
        "opus-planner": ["claude", "-p"],
        "opus-contract": ["claude", "-p"],
        "opus-reviewer": ["claude", "-p"],
        "opus-triage": ["claude", "-p"],
        "codex-builder": ["codex", "exec"],
    }})


def _chain(conn, contract_assignee, implement_assignee):
    con = kb.create_task(
        conn, title="write failing test", assignee=contract_assignee,
        provenance=kb.encode_provenance(origin="decomposer", root_id="r", stage="contract"))
    imp = kb.create_task(
        conn, title="implement", assignee=implement_assignee, parents=[con],
        provenance=kb.encode_provenance(origin="decomposer", root_id="r", stage="implement"))
    return con, imp


def test_implementer_on_a_different_host_than_the_test_author_is_accepted(kanban_home, monkeypatch):
    _roles(monkeypatch)
    with kb.connect_closing() as conn:
        _con, imp = _chain(conn, "opus-contract", "codex-builder")
        ok, reason = kb.check_cross_model_review(conn, imp)
    assert ok, reason


def test_implementer_on_the_same_host_as_the_test_author_is_rejected(kanban_home, monkeypatch):
    """Opus writing the test AND the code = self-marking. Refuse."""
    _roles(monkeypatch)
    with kb.connect_closing() as conn:
        _con, imp = _chain(conn, "opus-contract", "opus-planner")
        ok, reason = kb.check_cross_model_review(conn, imp)
    assert not ok
    assert reason == "same_host_as_author"


def test_the_review_rule_still_holds_alongside_the_contract_rule(kanban_home, monkeypatch):
    _roles(monkeypatch)
    with kb.connect_closing() as conn:
        _con, imp = _chain(conn, "opus-contract", "codex-builder")
        rev = kb.create_task(
            conn, title="review", assignee="codex-builder", parents=[imp],
            provenance=kb.encode_provenance(origin="decomposer", root_id="r", stage="review"))
        ok, reason = kb.check_cross_model_review(conn, rev)
    assert not ok, "codex reviewing codex's own diff must be refused"
    assert reason == "same_host_as_author"


def test_a_card_with_no_authored_parent_is_unconstrained(kanban_home, monkeypatch):
    _roles(monkeypatch)
    with kb.connect_closing() as conn:
        imp = kb.create_task(
            conn, title="standalone", assignee="codex-builder",
            provenance=kb.encode_provenance(origin="user", stage="implement"))
        ok, _ = kb.check_cross_model_review(conn, imp)
    assert ok


# --------------------------------------------------------------------------
# bounded repair: reviewer -> triage -> coder -> reviewer, then STOP
# --------------------------------------------------------------------------

def test_repair_rounds_are_bounded_and_terminate_in_triage(kanban_home):
    """The reviewer->triage->coder loop must be transitions on ONE card, and it
    must stop. A card-per-iteration loop is the runaway-fan-out incident.

    The existing machinery already enforces this exactly: the 2nd rejection
    routes the card to `triage` (a human decision) and emits
    `block_loop_detected`; a 3rd rejection is refused outright.
    """
    with kb.connect_closing() as conn:
        tid = kb.create_task(conn, title="implement", assignee="codex-builder")
        assert kb.repair_round(conn, tid) == 0
        assert not kb.repair_budget_exhausted(conn, tid)

        # round 1 — reviewer rejects, triage hands back to the coder
        assert kb.block_task(conn, tid, reason="changes requested", kind="needs_input")
        assert kb.get_task(conn, tid).status == "blocked"
        assert kb.unblock_task(conn, tid)
        assert kb.get_task(conn, tid).status == "ready"
        assert kb.repair_round(conn, tid) == 1
        assert not kb.repair_budget_exhausted(conn, tid)

        # round 2 — at the ceiling: routed to triage for a human, not retried
        assert kb.block_task(conn, tid, reason="changes requested", kind="needs_input")
        assert kb.get_task(conn, tid).status == "triage"
        assert kb.repair_round(conn, tid) == kb.REPAIR_ROUND_LIMIT
        assert kb.repair_budget_exhausted(conn, tid)

        # and it is genuinely terminal — no further cycles
        assert not kb.unblock_task(conn, tid)
        assert not kb.block_task(conn, tid, reason="again", kind="needs_input")

        kinds = [r[0] for r in conn.execute(
            "SELECT kind FROM task_events WHERE task_id=? ORDER BY id", (tid,))]
        assert "block_loop_detected" in kinds
        # exactly ONE card the whole way through — no fan-out
        assert len(kb.list_tasks(conn, limit=1000)) == 1


def test_an_exhausted_repair_card_can_never_be_decomposed(kanban_home):
    """The closing link. A card parked in triage by the repair ceiling is
    there for a HUMAN. Decomposing it is exactly how one blocked stage became
    285 cards."""
    with kb.connect_closing() as conn:
        tid = kb.create_task(conn, title="implement", assignee="codex-builder")
        kb.block_task(conn, tid, reason="changes requested", kind="needs_input")
        kb.unblock_task(conn, tid)
        kb.block_task(conn, tid, reason="changes requested", kind="needs_input")
        assert kb.get_task(conn, tid).status == "triage"
        assert kb.repair_budget_exhausted(conn, tid)
        ok, reason = kb.decompose_eligibility(conn, tid)
    assert not ok
    assert reason == "block_loop_routed"


def test_repair_ceiling_matches_the_existing_block_recurrence_limit(kanban_home):
    """One number, not two that can drift."""
    assert kb.REPAIR_ROUND_LIMIT == kb.BLOCK_RECURRENCE_LIMIT
