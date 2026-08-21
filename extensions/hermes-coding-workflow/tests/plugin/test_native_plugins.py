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
