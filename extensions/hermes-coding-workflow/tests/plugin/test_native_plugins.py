"""Authoritative hcw/v1 contracts exercised through Hermes's real plugin host."""
from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from hermes_coding_workflow import cli

ROOT = Path(__file__).parents[2]


def hermes_source() -> Path:
    configured = os.getenv("HERMES_SOURCE")
    if configured: return Path(configured).resolve()
    hermes = shutil.which("hermes")
    assert hermes
    version = subprocess.run([hermes, "--version"], text=True, capture_output=True, check=True).stdout
    for line in version.splitlines():
        if line.startswith("Install directory: "): return Path(line.split(": ", 1)[1]).resolve()
    raise AssertionError("Hermes did not report its install directory")


def load_plugin(name: str):
    path = ROOT / "plugins" / name / "__init__.py"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class Host:
    def __init__(self): self.skills, self.hooks = [], []
    def register_skill(self, name, path): self.skills.append((name, path))
    def register_hook(self, name, callback): self.hooks.append((name, callback))


def run(repo: Path, run_id: str, worktree: Path, *, status="awaiting_red") -> dict:
    value = {"schema_version":"hcw/v1", "kind":"run", "id":run_id, "revision":0,
             "created_at":"2026-08-19T00:00:00Z", "updated_at":"2026-08-19T00:00:00Z", "package_id":"pkg",
             "base_sha":subprocess.check_output(["git","-C",str(repo),"rev-parse","HEAD"], text=True).strip(),
             "head_sha":subprocess.check_output(["git","-C",str(repo),"rev-parse","HEAD"], text=True).strip(),
             "branch":"hcw/test/attempt-1", "repo_root":str(repo), "worktree_path":str(worktree), "status":status,
             "scope":["app.py", "tests/**"], "attempt":1, "attempt_history":[], "kanban_board":"hcw-test",
             "kanban_task_ids":{"design":"task-design","plan":"task-plan","red":"task-red","green":"task-green","spec-review":"task-spec","quality-review":"task-quality","verify":"task-verify","live":"task-live","complete":"task-complete"},
             "stage_profiles":{"design":"dev-planner","plan":"dev-planner","red":"dev-contract","green":"dev-builder","spec-review":"dev-spec-reviewer","quality-review":"dev-quality-reviewer","verify":"dev-verifier","live":"dev-verifier","complete":"dev-recorder"},
             "stage_statuses":{stage:("active" if stage == "red" else "pending") for stage in ("design","plan","red","green","spec-review","quality-review","verify","live","complete")}, "setup":{"created":[]}}
    root = repo / ".hermes" / "workflows" / run_id; root.mkdir(parents=True)
    (root / "run.json").write_text(json.dumps(value))
    (worktree / ".hermes").mkdir(exist_ok=True)
    (worktree / ".hermes" / "hcw-run.json").write_text(json.dumps({"schema_version":"hcw/v1", "run_id":run_id, "repo_root":str(repo), "worktree_path":str(worktree)}))
    return value


@pytest.fixture
def workflow(tmp_path, monkeypatch):
    repo = tmp_path / "repo"; subprocess.run(["git","init",str(repo)],check=True,capture_output=True)
    subprocess.run(["git","-C",str(repo),"config","user.email","test@example.invalid"],check=True)
    subprocess.run(["git","-C",str(repo),"config","user.name","Test"],check=True)
    (repo / "app.py").write_text("value = 1\n"); subprocess.run(["git","-C",str(repo),"add","."],check=True); subprocess.run(["git","-C",str(repo),"commit","-m","base"],check=True,capture_output=True)
    worktree = repo / ".worktrees" / "hcw-test-1"; subprocess.run(["git","-C",str(repo),"worktree","add","-b","hcw/test/attempt-1",str(worktree)],check=True,capture_output=True)
    state = run(repo,"run-test",worktree)
    monkeypatch.chdir(worktree); monkeypatch.setenv("HCW_RUN_ID","run-test"); monkeypatch.setenv("HERMES_KANBAN_TASK","task-red"); monkeypatch.setenv("HERMES_PROFILE","dev-contract")
    return repo, worktree, state


def test_native_packages_register_bare_role_skills_hooks_and_bootstrap():
    hcw, powers = load_plugin("hermes-coding-workflow"), load_plugin("superpowers-pinned")
    host, companion = Host(), Host(); hcw.register(host); powers.register(companion)
    assert {name for name, _ in host.skills} == {path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")}
    assert {name for name, _ in companion.skills} >= {"brainstorming"}
    assert {name for name, _ in host.hooks} == {"pre_llm_call", "pre_tool_call"}
    bootstrap = hcw._build_bootstrap()
    assert hcw.BOOTSTRAP_MARKER in bootstrap
    assert str((ROOT / "plugins" / "hermes-coding-workflow" / "runtime" / "bin" / "hcw").resolve()) in bootstrap
    for command in ("create-run", "approve-design", "approve-plan", "check", "review", "verify", "complete"):
        assert f"hcw {command}" in bootstrap


def test_bootstrap_context_gives_dispatcher_a_complete_matching_create_run_shape(tmp_path, monkeypatch):
    hcw = load_plugin("hermes-coding-workflow")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HERMES_KANBAN_TASK", "t_81f59d6c")
    monkeypatch.setenv("HERMES_KANBAN_BOARD", "default")

    bootstrap = hcw._build_bootstrap()
    launcher = shlex.quote(str((ROOT / "plugins" / "hermes-coding-workflow" / "runtime" / "bin" / "hcw").resolve()))
    assert f"{launcher} create-run {shlex.quote(str(tmp_path.resolve()))}" in bootstrap
    assert "--run-id t_81f59d6c --package t_81f59d6c" in bootstrap
    assert "--scope <task-approved-path-or-glob>" in bootstrap
    assert "--board default --goal <quoted-task-goal>" in bootstrap
    assert "do not omit arguments or prefix environment assignments" in bootstrap


@pytest.mark.parametrize(
    ("stage", "profile", "task", "commands"),
    (
        ("design", "dev-planner", "task-design", ("approve-design <repo> run-test --json <approved-design.json>",)),
        ("plan", "dev-planner", "task-plan", ("approve-plan <repo> run-test --json <approved-plan.json>",)),
        ("red", "dev-contract", "task-red", ("check <repo> run-test red -- <failing-test-command>",)),
        ("green", "dev-builder", "task-green", ("check <repo> run-test green -- <passing-test-command>", "commit <repo> run-test --message <quoted-commit-message>")),
        ("spec-review", "dev-spec-reviewer", "task-spec", ("review <repo> run-test --json <spec-review.json>",)),
        ("quality-review", "dev-quality-reviewer", "task-quality", ("review <repo> run-test --json <quality-review.json>",)),
        ("verify", "dev-verifier", "task-verify", ("check <repo> run-test full -- <full-test-command>", "check <repo> run-test security -- <security-test-command>", "verify <repo> run-test")),
        ("live", "dev-verifier", "task-live", ("check <repo> run-test live -- <live-acceptance-command>",)),
        ("complete", "dev-recorder", "task-complete", ("complete <repo> run-test",)),
    ),
)
def test_stage_worker_bootstrap_derives_registered_run_and_guides_only_its_active_stage(
    workflow, monkeypatch, stage, profile, task, commands
):
    """Removing locator-backed identity derivation would reintroduce the rejected stage bootstrap."""
    plugin = load_plugin("hermes-coding-workflow")
    repo, _, state = workflow
    state["stage_statuses"] = {name: ("active" if name == stage else "pending") for name in state["stage_statuses"]}
    (repo / ".hermes" / "workflows" / "run-test" / "run.json").write_text(json.dumps(state))
    monkeypatch.delenv("HCW_RUN_ID")
    monkeypatch.setenv("HERMES_KANBAN_TASK", task)
    monkeypatch.setenv("HERMES_PROFILE", profile)

    bootstrap = plugin._build_bootstrap()

    assert "create-run" not in bootstrap
    assert "run-test" in bootstrap
    assert str(repo) in bootstrap
    assert stage in bootstrap
    for command in commands:
        assert command.replace("<repo>", str(repo)) in bootstrap
    authorized_commands = {
        "design": f"approve-design {repo} run-test --json approved-design.json",
        "plan": f"approve-plan {repo} run-test --json approved-plan.json",
        "red": f"check {repo} run-test red -- pytest",
        "green": f"check {repo} run-test green -- pytest",
        "spec-review": f"review {repo} run-test --json spec-review.json",
        "quality-review": f"review {repo} run-test --json quality-review.json",
        "verify": f"check {repo} run-test full -- pytest",
        "live": f"check {repo} run-test live -- pytest",
        "complete": f"complete {repo} run-test",
    }
    assert plugin._pre_tool_call(
        tool_name="terminal",
        args={"command": f"{Path(plugin.__file__).resolve().parent / 'runtime' / 'bin' / 'hcw'} {authorized_commands[stage]}"},
    ) is None


@pytest.mark.parametrize(
    ("task", "profile", "active_stage"),
    (
        ("wrong-task", "dev-contract", "red"),
        ("task-red", "wrong-profile", "red"),
        ("task-red", "dev-contract", "green"),
    ),
    ids=("wrong-task", "wrong-profile", "inactive-stage"),
)
def test_registered_locator_with_invalid_stage_binding_never_emits_bootstrap_lifecycle_guidance(
    workflow, monkeypatch, task, profile, active_stage
):
    plugin = load_plugin("hermes-coding-workflow")
    repo, _, state = workflow
    state["stage_statuses"] = {
        name: ("active" if name == active_stage else "pending")
        for name in state["stage_statuses"]
    }
    (repo / ".hermes" / "workflows" / "run-test" / "run.json").write_text(json.dumps(state))
    monkeypatch.delenv("HCW_RUN_ID")
    monkeypatch.setenv("HERMES_KANBAN_TASK", task)
    monkeypatch.setenv("HERMES_PROFILE", profile)

    bootstrap = plugin._build_bootstrap()

    assert bootstrap == (
        f"{plugin.BOOTSTRAP_MARKER}: registered HCW workflow identity is invalid; "
        "do not run lifecycle commands."
    )
    for command in ("create-run", "approve-design", "approve-plan", "check", "commit", "review", "verify", "complete"):
        assert command not in bootstrap


def test_locator_derived_stage_identity_rejects_a_symlinked_locator(workflow, monkeypatch):
    """Following a symlinked locator would let an alternate worktree borrow the active stage binding."""
    plugin = load_plugin("hermes-coding-workflow")
    repo, worktree, _ = workflow
    monkeypatch.delenv("HCW_RUN_ID")
    locator = worktree / ".hermes" / "hcw-run.json"
    alternate = worktree.parent / "alternate-locator.json"
    alternate.write_text(locator.read_text())
    locator.unlink()
    locator.symlink_to(alternate)
    launcher = Path(plugin.__file__).resolve().parent / "runtime" / "bin" / "hcw"

    decision = plugin._pre_tool_call(
        tool_name="terminal",
        args={"command": f"{launcher} check {repo} run-test red -- pytest"},
    )

    assert decision and decision["action"] == "block"


def test_symlinked_git_common_directory_authority_fails_closed(workflow, monkeypatch):
    """Git authority must retain raw symlink provenance for linked worktrees."""
    plugin = load_plugin("hermes-coding-workflow")
    repo, worktree, _ = workflow
    authority = repo.parent / "redirected-git-authority"
    authority.mkdir()
    shutil.move(str(repo / ".git"), str(authority / ".git"))
    (repo / ".git").symlink_to(authority / ".git", target_is_directory=True)
    launcher = Path(plugin.__file__).resolve().parent / "runtime" / "bin" / "hcw"

    bootstrap = plugin._build_bootstrap()
    decision = plugin._pre_tool_call(
        tool_name="terminal",
        args={"command": f"{launcher} check {repo} run-test red -- pytest"},
    )

    assert bootstrap == (
        f"{plugin.BOOTSTRAP_MARKER}: registered HCW workflow identity is invalid; "
        "do not run lifecycle commands."
    )
    assert "create-run" not in bootstrap
    assert "check" not in bootstrap
    assert decision and decision["action"] == "block"


def test_git_authority_accepts_regular_primary_and_linked_worktrees(workflow):
    """A normal linked-worktree .git file still resolves to its real common dir."""
    plugin = load_plugin("hermes-coding-workflow")
    repo, worktree, _ = workflow

    assert plugin._canonical_repository_for_worktree(repo) == repo
    assert plugin._canonical_repository_for_worktree(worktree) == repo


@pytest.mark.parametrize("locator_kind", ("malformed", "symlink"))
def test_untrusted_locator_bootstrap_emits_only_invalid_identity_message(workflow, monkeypatch, locator_kind):
    plugin = load_plugin("hermes-coding-workflow")
    _, worktree, _ = workflow
    monkeypatch.delenv("HCW_RUN_ID")
    locator = worktree / ".hermes" / "hcw-run.json"
    if locator_kind == "malformed":
        locator.write_text("{")
    else:
        alternate = worktree.parent / "alternate-locator.json"
        alternate.write_text(locator.read_text())
        locator.unlink()
        locator.symlink_to(alternate)

    bootstrap = plugin._build_bootstrap()

    assert bootstrap == (
        f"{plugin.BOOTSTRAP_MARKER}: registered HCW workflow identity is invalid; "
        "do not run lifecycle commands."
    )
    assert "create-run" not in bootstrap


def test_registered_stage_worktree_with_missing_locator_cannot_rebootstrap_as_root(workflow, monkeypatch):
    """A lost locator must not let the original stage worker create a second run."""
    plugin = load_plugin("hermes-coding-workflow")
    repo, worktree, _ = workflow
    locator = worktree / ".hermes" / "hcw-run.json"
    locator.unlink()
    monkeypatch.delenv("HCW_RUN_ID")

    bootstrap = plugin._build_bootstrap()
    decision = plugin._pre_tool_call(
        tool_name="terminal",
        args={"command": _bootstrap_command(plugin, worktree, "task-red")},
    )

    assert bootstrap == (
        f"{plugin.BOOTSTRAP_MARKER}: registered HCW workflow identity is invalid; "
        "do not run lifecycle commands."
    )
    assert "create-run" not in bootstrap
    assert decision and decision["action"] == "block"
    assert (repo / ".hermes" / "workflows" / "run-test" / "run.json").is_file()


def test_symlinked_locator_parent_cannot_supply_active_stage_identity(workflow, monkeypatch):
    """A locator is untrusted when any authority directory component is a symlink."""
    plugin = load_plugin("hermes-coding-workflow")
    repo, worktree, _ = workflow
    locator_dir = worktree / ".hermes"
    external = worktree.parent / "external-locator"
    shutil.copytree(locator_dir, external)
    (locator_dir / "hcw-run.json").unlink()
    locator_dir.rmdir()
    locator_dir.symlink_to(external, target_is_directory=True)
    monkeypatch.delenv("HCW_RUN_ID")
    launcher = Path(plugin.__file__).resolve().parent / "runtime" / "bin" / "hcw"

    bootstrap = plugin._build_bootstrap()
    decision = plugin._pre_tool_call(
        tool_name="terminal",
        args={"command": f"{launcher} check {repo} run-test red -- pytest"},
    )

    assert bootstrap == (
        f"{plugin.BOOTSTRAP_MARKER}: registered HCW workflow identity is invalid; "
        "do not run lifecycle commands."
    )
    assert "create-run" not in bootstrap
    assert decision and decision["action"] == "block"


@pytest.mark.parametrize("state_kind", ("multiple", "malformed"))
def test_missing_locator_with_ambiguous_or_malformed_authority_fails_closed(workflow, monkeypatch, state_kind):
    plugin = load_plugin("hermes-coding-workflow")
    repo, worktree, state = workflow
    (worktree / ".hermes" / "hcw-run.json").unlink()
    extra = repo / ".hermes" / "workflows" / "other-run"
    extra.mkdir()
    if state_kind == "multiple":
        extra_state = {**state, "id": "other-run"}
        (extra / "run.json").write_text(json.dumps(extra_state))
    else:
        (extra / "run.json").write_text("{")
    monkeypatch.delenv("HCW_RUN_ID")

    bootstrap = plugin._build_bootstrap()
    decision = plugin._pre_tool_call(
        tool_name="terminal", args={"command": _bootstrap_command(plugin, worktree, "task-red")}
    )

    assert "create-run" not in bootstrap
    assert "do not run lifecycle commands" in bootstrap
    assert decision and decision["action"] == "block"


def test_unregistered_linked_worktree_without_locator_cannot_borrow_another_run(workflow, monkeypatch):
    plugin = load_plugin("hermes-coding-workflow")
    repo, worktree, _ = workflow
    other = repo / ".worktrees" / "unregistered"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-b", "other", str(other)], check=True, capture_output=True)
    monkeypatch.chdir(other)
    monkeypatch.delenv("HCW_RUN_ID")

    bootstrap = plugin._build_bootstrap()
    decision = plugin._pre_tool_call(
        tool_name="terminal", args={"command": _bootstrap_command(plugin, other, "task-red")}
    )

    assert "create-run" not in bootstrap
    assert "do not run lifecycle commands" in bootstrap
    assert decision and decision["action"] == "block"
    assert worktree != other


@pytest.mark.parametrize("authority_kind", ("parent", "leaf"))
def test_symlinked_authoritative_manifest_path_fails_closed(workflow, monkeypatch, authority_kind):
    plugin = load_plugin("hermes-coding-workflow")
    repo, _, _ = workflow
    authority = repo / ".hermes"
    external = repo.parent / f"external-authority-{authority_kind}"
    if authority_kind == "parent":
        shutil.copytree(authority, external)
        shutil.rmtree(authority)
        authority.symlink_to(external, target_is_directory=True)
    else:
        manifest = authority / "workflows" / "run-test" / "run.json"
        external.write_text(manifest.read_text())
        manifest.unlink()
        manifest.symlink_to(external)
    monkeypatch.delenv("HCW_RUN_ID")

    bootstrap = plugin._build_bootstrap()

    assert bootstrap == (
        f"{plugin.BOOTSTRAP_MARKER}: registered HCW workflow identity is invalid; "
        "do not run lifecycle commands."
    )
    assert "create-run" not in bootstrap


def test_guard_fails_closed_without_identity_and_enforces_exact_lifecycle_commands(workflow, monkeypatch):
    plugin = load_plugin("hermes-coding-workflow"); repo, worktree, state = workflow
    assert plugin._pre_tool_call(tool_name="write_file", args={"path":"app.py"})["action"] == "block"
    assert plugin._pre_tool_call(tool_name="write_file", args={"path":"tests/test_app.py"}) is None
    assert plugin._pre_tool_call(tool_name="write_file", args={"path":"../tests/test_escape.py"})["action"] == "block"
    assert plugin._pre_tool_call(tool_name="write_file", args={"path":str(worktree.parent / "tests" / "test_escape.py")})["action"] == "block"
    assert plugin._pre_tool_call(tool_name="terminal", args={"command":"sed -i '' 's/1/2/' app.py"})["action"] == "block"
    assert plugin._pre_tool_call(tool_name="terminal", args={"command":"python -c 'open(\"app.py\",\"w\").write(\"bad\")'"})["action"] == "block"
    state["stage_statuses"]["red"] = "completed"; state["stage_statuses"]["green"] = "active"; state["status"] = "awaiting_green"
    (repo / ".hermes" / "workflows" / "run-test" / "run.json").write_text(json.dumps(state))
    monkeypatch.setenv("HERMES_KANBAN_TASK", "task-green"); monkeypatch.setenv("HERMES_PROFILE", "dev-builder")
    assert plugin._pre_tool_call(tool_name="write_file", args={"path":"app.py"})["action"] == "block"
    red = {"schema_version":"hcw/v1", "kind":"evidence", "id":"EV-red", "created_at":"2026-08-19T00:00:00Z", "run_id":"run-test", "type":"red", "actor":{"profile":"dev-contract", "task_id":"task-red"}, "commit_sha":state["base_sha"], "command":["python","-m","unittest"], "exit_code":1, "artifact_path":"artifacts/red.log", "artifact_sha256":"a" * 64, "previous_evidence_hash":None}
    red["evidence_hash"] = hashlib.sha256(json.dumps(red, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    (repo / ".hermes" / "workflows" / "run-test" / "evidence.jsonl").write_text(json.dumps(red) + "\n")
    assert plugin._pre_tool_call(tool_name="write_file", args={"path":"app.py"}) is None
    assert plugin._pre_tool_call(tool_name="write_file", args={"path":"README.md"})["action"] == "block"
    assert plugin._pre_tool_call(tool_name="write_file", args={"path":str(worktree.parent / "outside.py")})["action"] == "block"
    assert plugin._pre_tool_call(tool_name="terminal", args={"command":"python -c 'open(\"app.py\",\"w\").write(\"bad\")'"})["action"] == "block"
    assert plugin._pre_tool_call(tool_name="terminal", args={"command":"git status --short"}) is None
    assert plugin._pre_tool_call(tool_name="terminal", args={"command":"git add -- app.py"})["action"] == "block"
    assert plugin._pre_tool_call(tool_name="terminal", args={"command":"git commit --only README.md -m escape"})["action"] == "block"
    monkeypatch.delenv("HCW_RUN_ID"); monkeypatch.delenv("HERMES_KANBAN_TASK"); monkeypatch.delenv("HERMES_PROFILE")
    assert plugin._pre_tool_call(tool_name="write_file", args={"path":"app.py"})["action"] == "block"
    assert plugin._pre_tool_call(tool_name="terminal", args={"command":"git status --short"}) is None
    assert plugin._pre_tool_call(tool_name="terminal", args={"command":f"{(ROOT / 'plugins' / 'hermes-coding-workflow' / 'runtime' / 'bin' / 'hcw').resolve()} create-run repo --run-id bootstrap --package pkg --scope tests/** --board hcw --goal bootstrap"})["action"] == "block"
    assert plugin._pre_tool_call(tool_name="terminal", args={"command":"hcw check repo bootstrap red -- false"})["action"] == "block"
    monkeypatch.setenv("HCW_RUN_ID", "run-test")
    assert plugin._pre_tool_call(tool_name="write_file", args={"path":"app.py"})["action"] == "block"


def _bootstrap_command(plugin, repo: Path, run_id: str) -> str:
    launcher = (Path(plugin.__file__).resolve().parent / "runtime" / "bin" / "hcw").resolve()
    return (
        f"{launcher} create-run {repo} --run-id {run_id} --package pkg "
        "--scope tests/** --board hcw --goal bootstrap"
    )


def test_dispatcher_partial_identity_permits_only_matching_create_run(workflow, monkeypatch):
    plugin = load_plugin("hermes-coding-workflow"); repo, _, _ = workflow
    monkeypatch.chdir(repo)
    monkeypatch.delenv("HCW_RUN_ID"); monkeypatch.delenv("HERMES_PROFILE")
    monkeypatch.setenv("HERMES_KANBAN_TASK", "t_bootstrap")

    assert plugin._pre_tool_call(
        tool_name="terminal",
        args={"command": _bootstrap_command(plugin, repo, "t_bootstrap")},
    ) is None


def test_full_identity_without_locator_permits_matching_create_run(workflow, monkeypatch):
    plugin = load_plugin("hermes-coding-workflow"); repo, _, _ = workflow
    monkeypatch.chdir(repo)
    monkeypatch.setenv("HCW_RUN_ID", "t_bootstrap")
    monkeypatch.setenv("HERMES_KANBAN_TASK", "t_bootstrap")
    monkeypatch.setenv("HERMES_PROFILE", "hcw-dev")

    assert plugin._pre_tool_call(
        tool_name="terminal",
        args={"command": _bootstrap_command(plugin, repo, "t_bootstrap")},
    ) is None


def test_bootstrap_rejects_mismatched_run_id(workflow, monkeypatch):
    plugin = load_plugin("hermes-coding-workflow"); repo, _, _ = workflow
    monkeypatch.chdir(repo)
    monkeypatch.delenv("HCW_RUN_ID"); monkeypatch.delenv("HERMES_PROFILE")
    monkeypatch.setenv("HERMES_KANBAN_TASK", "t_bootstrap")

    decision = plugin._pre_tool_call(
        tool_name="terminal",
        args={"command": _bootstrap_command(plugin, repo, "different-run")},
    )
    assert decision and decision["action"] == "block"


def test_bootstrap_rejects_non_hcw_terminal_command(workflow, monkeypatch):
    plugin = load_plugin("hermes-coding-workflow"); repo, _, _ = workflow
    monkeypatch.chdir(repo)
    monkeypatch.delenv("HCW_RUN_ID"); monkeypatch.delenv("HERMES_PROFILE")
    monkeypatch.setenv("HERMES_KANBAN_TASK", "t_bootstrap")

    decision = plugin._pre_tool_call(
        tool_name="terminal",
        args={"command": "python -c 'open(\"app.py\", \"w\").write(\"bad\")'"},
    )
    assert decision and decision["action"] == "block"


def test_post_bootstrap_source_mutation_requires_full_registered_lifecycle(workflow, monkeypatch):
    plugin = load_plugin("hermes-coding-workflow"); _, worktree, _ = workflow
    monkeypatch.chdir(worktree)
    monkeypatch.delenv("HCW_RUN_ID"); monkeypatch.delenv("HERMES_PROFILE")
    monkeypatch.setenv("HERMES_KANBAN_TASK", "task-red")

    partial = plugin._pre_tool_call(tool_name="write_file", args={"path":"tests/test_app.py"})
    assert partial and partial["action"] == "block"

    monkeypatch.setenv("HCW_RUN_ID", "run-test")
    monkeypatch.setenv("HERMES_PROFILE", "dev-contract")
    assert plugin._pre_tool_call(tool_name="write_file", args={"path":"tests/test_app.py"}) is None
    source = plugin._pre_tool_call(tool_name="write_file", args={"path":"app.py"})
    assert source and source["action"] == "block"


CLAUDE_WORKER_STAGES = {
    "red": ("dev-contract", "task-red"),
    "green": ("dev-builder", "task-green"),
    "quality-review": ("dev-quality-reviewer", "task-quality"),
    "complete": ("dev-recorder", "task-complete"),
}


def _activate_claude_stage(repo: Path, state: dict, monkeypatch, stage: str) -> None:
    profile, task_id = CLAUDE_WORKER_STAGES[stage]
    state["stage_statuses"] = {name: ("active" if name == stage else "pending") for name in state["stage_statuses"]}
    (repo / ".hermes" / "workflows" / "run-test" / "run.json").write_text(json.dumps(state))
    monkeypatch.setenv("HERMES_KANBAN_TASK", task_id)
    monkeypatch.setenv("HERMES_PROFILE", profile)


@pytest.mark.parametrize("stage", CLAUDE_WORKER_STAGES)
@pytest.mark.parametrize("command", ("dispatch-worker", "worker-status"))
def test_claude_worker_commands_allow_only_the_authoritative_canonical_repo(workflow, monkeypatch, stage, command):
    plugin = load_plugin("hermes-coding-workflow"); repo, _, state = workflow
    _activate_claude_stage(repo, state, monkeypatch, stage)
    launcher = (ROOT / "plugins" / "hermes-coding-workflow" / "runtime" / "bin" / "hcw").resolve()
    exact = f"{launcher} {command} {repo.resolve()} run-test {stage}"
    assert plugin._pre_tool_call(tool_name="terminal", args={"command": exact}) is None


@pytest.mark.parametrize("command", ("dispatch-worker", "worker-status"))
def test_claude_worker_commands_reject_other_repo_even_when_run_and_stage_match(workflow, command):
    plugin = load_plugin("hermes-coding-workflow"); repo, _, _ = workflow
    other = repo.parent / "other-repo"; other.mkdir()
    launcher = (ROOT / "plugins" / "hermes-coding-workflow" / "runtime" / "bin" / "hcw").resolve()
    decision = plugin._pre_tool_call(tool_name="terminal", args={"command": f"{launcher} {command} {other} run-test red"})
    assert decision and decision["action"] == "block"


@pytest.mark.parametrize("command", ("dispatch-worker", "worker-status"))
def test_claude_worker_commands_reject_repo_symlink_alias_and_nonexistent_path(workflow, command):
    plugin = load_plugin("hermes-coding-workflow"); repo, _, _ = workflow
    alias = repo.parent / "repo-alias"; alias.symlink_to(repo, target_is_directory=True)
    launcher = (ROOT / "plugins" / "hermes-coding-workflow" / "runtime" / "bin" / "hcw").resolve()
    decision = plugin._pre_tool_call(tool_name="terminal", args={"command": f"{launcher} {command} {alias} run-test red"})
    assert decision and decision["action"] == "block"
    missing = repo.parent / "does-not-exist"
    decision = plugin._pre_tool_call(tool_name="terminal", args={"command": f"{launcher} {command} {missing} run-test red"})
    assert decision and decision["action"] == "block"


@pytest.mark.parametrize("command", ("dispatch-worker", "worker-status"))
def test_claude_worker_alias_swap_cannot_retarget_cli_after_hook_authorization(workflow, command):
    """The hook must reject an alias before the CLI can resolve it again."""
    plugin = load_plugin("hermes-coding-workflow"); repo, _, _ = workflow
    other = repo.parent / "other-repo"
    subprocess.run(["git", "init", str(other)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(other), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(other), "config", "user.name", "Test"], check=True)
    (other / "app.py").write_text("value = 2\n")
    subprocess.run(["git", "-C", str(other), "add", "."], check=True)
    subprocess.run(["git", "-C", str(other), "commit", "-m", "other"], check=True, capture_output=True)
    other_state = run(other, "run-test", other)
    other_state["stage_statuses"]["red"] = "active"
    (other / ".hermes" / "workflows" / "run-test" / "run.json").write_text(json.dumps(other_state))
    alias = repo.parent / "repo-alias"; alias.symlink_to(repo, target_is_directory=True)
    launcher = (ROOT / "plugins" / "hermes-coding-workflow" / "runtime" / "bin" / "hcw").resolve()

    authorization = plugin._pre_tool_call(
        tool_name="terminal", args={"command": f"{launcher} {command} {alias} run-test red"}
    )
    alias.unlink()
    alias.symlink_to(other, target_is_directory=True)
    cli_repo, cli_run_id = cli._repo_and_run(alias, "run-test")

    assert cli_repo == other
    assert cli_run_id == "run-test"
    assert authorization and authorization["action"] == "block"


@pytest.mark.parametrize("command", ("dispatch-worker", "worker-status"))
def test_claude_worker_commands_reject_wrong_identity_shape_and_shell_escapes(workflow, monkeypatch, command):
    plugin = load_plugin("hermes-coding-workflow"); repo, _, state = workflow
    launcher = (ROOT / "plugins" / "hermes-coding-workflow" / "runtime" / "bin" / "hcw").resolve()
    valid = f"{launcher} {command} {repo} run-test red"
    for candidate in (
        f"{launcher} {command} {repo} wrong-run red",
        f"{launcher} {command} {repo} run-test green",
        f"{launcher} {command} . run-test red",
        f"{launcher} {command} {repo.parent / repo.name / '..' / repo.name} run-test red",
        f"{launcher} {command} {repo} run-test",
        f"{valid} extra",
        f"HCW_RUN_ID=run-test {valid}",
        f"hcw {command} {repo} run-test red",
        f"{valid} && true",
        f"{valid} > output.txt",
    ):
        decision = plugin._pre_tool_call(tool_name="terminal", args={"command": candidate})
        assert decision and decision["action"] == "block", candidate
    _activate_claude_stage(repo, state, monkeypatch, "red")
    decision = plugin._pre_tool_call(tool_name="terminal", args={"command": valid})
    assert decision is None
    state["stage_statuses"]["red"] = "completed"
    (repo / ".hermes" / "workflows" / "run-test" / "run.json").write_text(json.dumps(state))
    decision = plugin._pre_tool_call(tool_name="terminal", args={"command": valid})
    assert decision and decision["action"] == "block"
    monkeypatch.delenv("HCW_RUN_ID"); monkeypatch.delenv("HERMES_PROFILE"); monkeypatch.delenv("HERMES_KANBAN_TASK")
    decision = plugin._pre_tool_call(tool_name="terminal", args={"command": valid})
    assert decision and decision["action"] == "block"


def test_dispatch_worker_blocked_once_its_bound_stage_is_no_longer_active(workflow):
    plugin = load_plugin("hermes-coding-workflow"); repo, worktree, state = workflow
    state["stage_statuses"]["red"] = "completed"; state["stage_statuses"]["green"] = "active"
    (repo / ".hermes" / "workflows" / "run-test" / "run.json").write_text(json.dumps(state))
    launcher = (ROOT / "plugins" / "hermes-coding-workflow" / "runtime" / "bin" / "hcw").resolve()

    decision = plugin._pre_tool_call(tool_name="terminal", args={"command": f"{launcher} dispatch-worker {repo} run-test red"})
    assert decision and decision["action"] == "block"


def test_installer_scans_real_packages_and_doctor_is_clean(tmp_path):
    hermes = shutil.which("hermes")
    assert hermes, "mandatory native-package test requires Hermes"
    home = tmp_path / "home"; home.mkdir(); env = {**os.environ, "HERMES_HOME":str(home), "PYTHONPATH":str(hermes_source())}
    subprocess.run([hermes,"profile","create","dev","--no-alias"],env=env,check=True,capture_output=True,text=True)
    subprocess.run([hermes,"config","set","model.provider","openai"],env=env,check=True,capture_output=True,text=True)
    subprocess.run([hermes,"config","set","model.default","gpt-4o-mini"],env=env,check=True,capture_output=True,text=True)
    subprocess.run([hermes,"config","set","model.provider","openai"],env={**env,"HERMES_HOME":str(home / "profiles" / "dev")},check=True,capture_output=True,text=True)
    subprocess.run([hermes,"config","set","model.default","gpt-4o-mini"],env={**env,"HERMES_HOME":str(home / "profiles" / "dev")},check=True,capture_output=True,text=True)
    subprocess.run([sys.executable,str(ROOT / "scripts" / "install.py"),"--hermes-home",str(home),"--source-profile","dev"],env=env,check=True,capture_output=True,text=True)
    subprocess.run([hermes,"plugins","doctor",str(home / "plugins" / "hcw-dashboard"),"--ci"],env=env,check=True,capture_output=True,text=True)
    assert not (home / "plugins" / "hcw").exists()
    assert not (home / "plugins" / "superpowers").exists()
    assert (home / "desktop-plugins" / "hcw" / "plugin.js").is_file()
    protected = (home / "profiles" / "dev", *(home / "profiles" / name for name in ("dev-planner","dev-contract","dev-builder","dev-spec-reviewer","dev-quality-reviewer","dev-verifier","dev-recorder")))
    for target in protected:
        for package in ("hcw", "superpowers"):
            subprocess.run([hermes,"plugins","doctor",str(target / "plugins" / package),"--ci"],env={**env,"HERMES_HOME":str(target)},check=True,capture_output=True,text=True)
        assert (target / "plugins" / "hcw" / "runtime" / "bin" / "hcw").is_file()
    subprocess.run([sys.executable,str(ROOT / "scripts" / "doctor.py"),"--hermes-home",str(home)],env=env,check=True,capture_output=True,text=True)


def test_doctor_accepts_the_installed_nondefault_source_profile(tmp_path):
    hermes = shutil.which("hermes")
    assert hermes, "mandatory source-profile doctor test requires Hermes"
    home = tmp_path / "home"; home.mkdir()
    env = {**os.environ, "HERMES_HOME":str(home), "PYTHONPATH":str(hermes_source())}
    source = "hcw-dev"
    subprocess.run([hermes,"profile","create",source,"--no-alias"],env=env,check=True,capture_output=True,text=True)
    subprocess.run([hermes,"config","set","model.provider","openai"],env=env,check=True,capture_output=True,text=True)
    subprocess.run([hermes,"config","set","model.default","gpt-4o-mini"],env=env,check=True,capture_output=True,text=True)
    source_env = {**env,"HERMES_HOME":str(home / "profiles" / source)}
    subprocess.run([hermes,"config","set","model.provider","openai"],env=source_env,check=True,capture_output=True,text=True)
    subprocess.run([hermes,"config","set","model.default","gpt-4o-mini"],env=source_env,check=True,capture_output=True,text=True)
    subprocess.run([sys.executable,str(ROOT / "scripts" / "install.py"),"--hermes-home",str(home),"--source-profile",source],env=env,check=True,capture_output=True,text=True)
    subprocess.run([sys.executable,str(ROOT / "scripts" / "doctor.py"),"--hermes-home",str(home),"--source-profile",source],env=env,check=True,capture_output=True,text=True)
