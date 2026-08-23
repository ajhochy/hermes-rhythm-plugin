"""Always-executed installed Hermes v0.20 lifecycle proof."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).parents[2]
ROLES = {"design":"dev-planner", "plan":"dev-planner", "red":"dev-contract", "green":"dev-builder", "spec-review":"dev-spec-reviewer", "quality-review":"dev-quality-reviewer", "verify":"dev-verifier", "live":"dev-verifier", "complete":"dev-recorder"}


def call(argv, env, cwd):
    result = subprocess.run(argv, env=env, cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(f"command failed rc={result.returncode}: stdout={result.stdout!r} stderr={result.stderr!r}")
    return json.loads(result.stdout)


def source(hermes: str) -> Path:
    text = subprocess.run([hermes, "--version"], text=True, capture_output=True, check=True).stdout
    return Path(next(line.split(": ", 1)[1] for line in text.splitlines() if line.startswith("Install directory: ")))


def test_installed_lifecycle_runs_real_disposable_repository(tmp_path, monkeypatch):
    hermes = shutil.which("hermes")
    assert hermes, "mandatory installed lifecycle E2E requires local Hermes"
    home, repo = tmp_path / "hermes", tmp_path / "repo"; home.mkdir(); repo.mkdir()
    fake_claude = tmp_path / "fake-claude"
    fake_claude.write_text("""#!/usr/bin/env python3
import json, pathlib, sys
prompt = sys.stdin.read()
if "stage 'red'" in prompt:
    pathlib.Path("tests").mkdir(exist_ok=True)
    pathlib.Path("tests/__init__.py").write_text("")
    pathlib.Path("tests/test_app.py").write_text("import unittest\\nfrom app import value\\nclass TestValue(unittest.TestCase):\\n def test_value(self): self.assertEqual(value(), 2)\\n")
elif "stage 'green'" in prompt:
    pathlib.Path("app.py").write_text("def value():\\n    return 2\\n")
print(json.dumps({"result": "ok"}))
""")
    fake_claude.chmod(0o755)
    base_env = {**os.environ, "HERMES_HOME":str(home), "PYTHONPATH":str(source(hermes)), "PYTHONDONTWRITEBYTECODE":"1", "HCW_CLAUDE_CLI":str(fake_claude)}
    subprocess.run([hermes,"profile","create","dev","--no-alias"],env=base_env,check=True,capture_output=True,text=True)
    # Configuring the safe Hermes dispatch route is inert; no model call occurs.
    subprocess.run([hermes,"config","set","model.provider","openai"],env=base_env,check=True,capture_output=True,text=True)
    subprocess.run([hermes,"config","set","model.default","gpt-4o-mini"],env=base_env,check=True,capture_output=True,text=True)
    subprocess.run([hermes,"config","set","model.provider","openai"],env={**base_env,"HERMES_HOME":str(home / "profiles" / "dev")},check=True,capture_output=True,text=True)
    subprocess.run([hermes,"config","set","model.default","gpt-4o-mini"],env={**base_env,"HERMES_HOME":str(home / "profiles" / "dev")},check=True,capture_output=True,text=True)
    subprocess.run([sys.executable,str(ROOT / "scripts" / "install.py"),"--hermes-home",str(home),"--source-profile","dev"],env=base_env,check=True,capture_output=True,text=True)
    subprocess.run(["git","init","-b","main",str(repo)],check=True,capture_output=True); subprocess.run(["git","-C",str(repo),"config","user.email","e2e@example.invalid"],check=True); subprocess.run(["git","-C",str(repo),"config","user.name","E2E"],check=True)
    (repo / "app.py").write_text("def value():\n    return 1\n")
    subprocess.run(["git","-C",str(repo),"add","."],check=True); subprocess.run(["git","-C",str(repo),"commit","-m","base"],check=True,capture_output=True)
    base_sha = subprocess.check_output(["git","-C",str(repo),"rev-parse","HEAD"],text=True).strip(); run_id="e2e-run"; board="hcw-e2e"
    launcher = home / "profiles" / "dev" / "plugins" / "hcw" / "runtime" / "bin" / "hcw"
    created = call([str(launcher),"create-run",str(repo),"--run-id",run_id,"--goal","make value return two","--package","P5","--scope","app.py","--scope","tests/**","--board",board],base_env,repo)
    worktree=Path(created["worktree_path"]); tasks=created["kanban_task_ids"]
    assert all(tasks.values()), "public create-run must return actual Hermes task IDs"
    def env(stage): return {**base_env,"HERMES_HOME":str(home / "profiles" / ROLES[stage]),"HERMES_PROFILE":ROLES[stage],"HERMES_KANBAN_TASK":tasks[stage],"HCW_RUN_ID":run_id}
    def external_worker(stage):
        stage_launcher = home / "profiles" / ROLES[stage] / "plugins" / "hcw" / "runtime" / "bin" / "hcw"
        queued = call([str(stage_launcher),"dispatch-worker",str(repo),run_id,stage],env(stage),worktree)
        assert queued["state"] == "queued"
        status = queued
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            status = call([str(stage_launcher),"worker-status",str(repo),run_id,stage],env(stage),worktree)
            if status["state"] in {"succeeded","failed"}: break
            time.sleep(0.05)
        assert status["state"] == "succeeded" and status["exit_code"] == 0
        return status
    design={"observable_outcome":"value returns two","requirements":[{"id":"R1","description":"change app"}],"acceptance_criteria":["unittest passes"],"approved":True}
    unit=[sys.executable,"-m","unittest","discover","-s","tests"]
    plan={"tasks":[{"id":"T1","description":"test then change","paths":["app.py","tests/test_app.py"],"test_command":unit,"requirement_ids":["R1"]}],"commands":{"red":{"argv":unit,"requirement_ids":["R1"]},"green":{"argv":unit,"requirement_ids":["R1"]},"full":{"argv":unit,"requirement_ids":["R1"]},"security":{"argv":[sys.executable,"-m","compileall","-q","app.py"],"requirement_ids":["R1"]},"live":{"argv":[sys.executable,"-c","import app; assert app.value()==2"],"requirement_ids":["R1"]}},"approved":True}
    for stage, command, payload in (("design","approve-design",design),("plan","approve-plan",plan)):
        path=tmp_path / f"{stage}.json"; path.write_text(json.dumps(payload)); call([str(home / "profiles" / ROLES[stage] / "plugins" / "hcw" / "runtime" / "bin" / "hcw"),command,str(repo),run_id,"--json",str(path)],env(stage),repo)
    installed = home / "profiles" / "dev-contract" / "plugins" / "hcw" / "__init__.py"; spec=importlib.util.spec_from_file_location("installed_hcw",installed); plugin=importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(plugin)
    monkeypatch.chdir(worktree); monkeypatch.delenv("HCW_RUN_ID",raising=False); monkeypatch.delenv("HERMES_KANBAN_TASK",raising=False); monkeypatch.delenv("HERMES_PROFILE",raising=False)
    assert plugin._pre_tool_call("write_file",{"path":"app.py"})["action"] == "block"
    monkeypatch.setenv("HCW_RUN_ID",run_id); monkeypatch.setenv("HERMES_KANBAN_TASK",tasks["design"]); monkeypatch.setenv("HERMES_PROFILE",ROLES["design"])
    assert plugin._pre_tool_call("write_file",{"path":"app.py"})["action"] == "block"
    monkeypatch.setenv("HERMES_KANBAN_TASK",tasks["red"]); monkeypatch.setenv("HERMES_PROFILE",ROLES["red"])
    assert plugin._pre_tool_call("write_file",{"path":"app.py"})["action"] == "block"
    assert plugin._pre_tool_call("write_file",{"path":"tests/test_app.py"}) is None
    external_worker("red")
    red = call([str(home / "profiles" / ROLES["red"] / "plugins" / "hcw" / "runtime" / "bin" / "hcw"),"check",str(repo),run_id,"red","--",*unit],env("red"),worktree); assert red["exit_code"] != 0
    monkeypatch.setenv("HERMES_KANBAN_TASK",tasks["green"]); monkeypatch.setenv("HERMES_PROFILE",ROLES["green"])
    assert plugin._pre_tool_call("write_file",{"path":"app.py"}) is None
    external_worker("green")
    call([str(home / "profiles" / ROLES["green"] / "plugins" / "hcw" / "runtime" / "bin" / "hcw"),"commit",str(repo),run_id,"--message","implement value"],env("green"),worktree)
    green=call([str(home / "profiles" / ROLES["green"] / "plugins" / "hcw" / "runtime" / "bin" / "hcw"),"check",str(repo),run_id,"green","--",*unit],env("green"),worktree); candidate=green["commit_sha"]
    review={"reviewed_sha":candidate,"decision":"approved","findings":[],"dispositions":[]}
    for stage in ("spec-review","quality-review"):
        if stage == "quality-review": external_worker(stage)
        path=tmp_path / f"{stage}.json"; path.write_text(json.dumps(review)); call([str(home / "profiles" / ROLES[stage] / "plugins" / "hcw" / "runtime" / "bin" / "hcw"),"review",str(repo),run_id,"--json",str(path)],env(stage),worktree)
    for stage, kind, declared in (("verify","full",unit),("verify","security",plan["commands"]["security"]["argv"])):
        evidence=call([str(home / "profiles" / ROLES[stage] / "plugins" / "hcw" / "runtime" / "bin" / "hcw"),"check",str(repo),run_id,kind,"--",*declared],env(stage),worktree); assert evidence["exit_code"] == 0 and len(evidence["evidence_hash"]) == 64
    call([str(home / "profiles" / ROLES["verify"] / "plugins" / "hcw" / "runtime" / "bin" / "hcw"),"verify",str(repo),run_id],env("verify"),worktree)
    evidence=call([str(home / "profiles" / ROLES["live"] / "plugins" / "hcw" / "runtime" / "bin" / "hcw"),"check",str(repo),run_id,"live","--",*plan["commands"]["live"]["argv"]],env("live"),worktree); assert evidence["exit_code"] == 0
    external_worker("complete")
    completed=call([str(home / "profiles" / ROLES["complete"] / "plugins" / "hcw" / "runtime" / "bin" / "hcw"),"complete",str(repo),run_id],env("complete"),worktree); assert completed["status"] == "completed"
    # The installed dashboard must project the current artifact shape without
    # leaking executable command lines or machine paths.
    sys.path.insert(0, str(source(hermes))); monkeypatch.setenv("HERMES_HOME", str(home))
    dashboard_spec = importlib.util.spec_from_file_location("installed_dashboard", home / "plugins" / "hcw-dashboard" / "dashboard" / "plugin_api.py")
    dashboard = importlib.util.module_from_spec(dashboard_spec); assert dashboard_spec and dashboard_spec.loader; dashboard_spec.loader.exec_module(dashboard)
    app = FastAPI(); app.include_router(dashboard.router); projection = TestClient(app).get(f"/runs/{run_id}?board={board}").json()
    assert projection["reviews"] and len(projection["evidence"]) == 5
    assert {stage["id"]: (stage["depends_on"], stage["profile"]) for stage in projection["stages"]}["plan"] == (["design"], "dev-planner")
    assert str(repo) not in json.dumps(projection) and "command" not in json.dumps(projection)
    subprocess.run([sys.executable,str(ROOT / "scripts" / "doctor.py"),"--hermes-home",str(home)],env=base_env,check=True,capture_output=True,text=True)
    assert (home / "desktop-plugins" / "hcw" / "plugin.js").is_file()
    assert subprocess.check_output(["git","-C",str(repo),"rev-parse","main"],text=True).strip() == base_sha
    assert subprocess.check_output(["git","-C",str(repo),"branch","--show-current"],text=True).strip() == "main"
    assert candidate != base_sha
