"""Prove the worker_runner subprocess can import itself from an installed
runtime/site layout, with no inherited PYTHONPATH -- exactly the shape
`scripts/install.py` produces (see `_build_plugin`'s `runtime/site` +
`runtime/bin/hcw` launcher). A source-tree-only PYTHONPATH test cannot catch
a launcher that only mutates `sys.path` for its own process.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SRC = ROOT / "src" / "hermes_coding_workflow"

FAKE_CLAUDE = r'''#!/usr/bin/env python3
import json, os, sys
def main():
    print(json.dumps({"result": "ok"}))
    return 0
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


def _stage_installed_site(tmp_path: Path) -> Path:
    """Copy the real package into a `runtime/site/hermes_coding_workflow`
    layout, exactly what `_build_plugin` in `scripts/install.py` produces."""
    site = tmp_path / "runtime" / "site"
    shutil.copytree(PACKAGE_SRC, site / "hermes_coding_workflow")
    return site


def _import_installed_service(site: Path) -> types.ModuleType:
    """Import the staged copy under a distinct top-level package name so it
    never collides with the source-tree `hermes_coding_workflow` already
    cached in `sys.modules` by the rest of this test session."""
    package_dir = site / "hermes_coding_workflow"
    spec = importlib.util.spec_from_file_location(
        "hcw_installed_runner_probe", package_dir / "__init__.py",
        submodule_search_locations=[str(package_dir)],
    )
    assert spec and spec.loader
    package = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = package
    spec.loader.exec_module(package)
    service_spec = importlib.util.spec_from_file_location(
        f"{spec.name}.service", package_dir / "service.py",
    )
    assert service_spec and service_spec.loader
    service = importlib.util.module_from_spec(service_spec)
    service.__package__ = spec.name
    sys.modules[service_spec.name] = service
    service_spec.loader.exec_module(service)
    return service


def payloads():
    design = {"observable_outcome": "new behavior", "requirements": [{"id": "R1", "description": "change app"}], "acceptance_criteria": ["green"], "approved": True}
    command = [sys.executable, "-c", "raise SystemExit(0)"]
    plan = {"tasks": [{"id": "one", "description": "change it", "paths": ["app.txt"], "test_command": command, "requirement_ids": ["R1"]}], "commands": {"red": {"argv": command, "requirement_ids": ["R1"]}, "green": {"argv": command, "requirement_ids": ["R1"]}, "full": {"argv": command, "requirement_ids": ["R1"]}, "security": {"argv": command, "requirement_ids": ["R1"]}, "live": {"argv": command, "requirement_ids": ["R1"]}}, "approved": True}
    return design, plan


def test_dispatched_worker_reaches_terminal_state_from_an_installed_runtime_site_with_no_inherited_pythonpath(
    tmp_path: Path, repo: Path, monkeypatch
) -> None:
    site = _stage_installed_site(tmp_path)
    installed_service = _import_installed_service(site)

    fake_claude = tmp_path / "fake-claude"
    fake_claude.write_text(FAKE_CLAUDE)
    fake_claude.chmod(0o755)
    monkeypatch.setenv("HCW_CLAUDE_CLI", str(fake_claude))
    monkeypatch.delenv("PYTHONPATH", raising=False)

    from hermes_coding_workflow.adapters import KanbanAdapter
    from hermes_coding_workflow.contracts import PROFILES

    calls: list[tuple[str, ...]] = []
    statuses: dict[str, str] = {}

    def run(argv, cwd):
        calls.append(tuple(argv))
        if "create" in argv:
            stage = argv[argv.index("create") + 1].split(": ")[-1]
            ident = "task-" + stage
            statuses[ident] = "todo"
            return subprocess.CompletedProcess(argv, 0, json.dumps({"id": ident}) if "--json" in argv else "", "")
        if "show" in argv:
            ident = argv[argv.index("show") + 1]
            return subprocess.CompletedProcess(argv, 0, json.dumps({"task": {"id": ident, "status": statuses.get(ident, "todo")}}), "")
        if "promote" in argv:
            statuses[argv[argv.index("promote") + 1]] = "ready"
            return subprocess.CompletedProcess(argv, 0, "", "")
        if "complete" in argv:
            statuses[argv[argv.index("complete") + 1]] = "done"
        return subprocess.CompletedProcess(argv, 0, "", "")

    board = KanbanAdapter(repo, "hcw-test", run)
    svc = installed_service.WorkflowService(repo)
    svc.create_run("pkg", ["app.txt"], "run-1", "hcw-test", board)
    design, plan = payloads()
    svc.approve_design("run-1", installed_service.ActorContext(PROFILES["design"], "task-design"), design)
    svc.approve_plan("run-1", installed_service.ActorContext(PROFILES["plan"], "task-plan"), plan)

    svc.dispatch_worker("run-1", "red")

    deadline = time.monotonic() + 10.0
    record = svc.worker_status("run-1", "red")
    while record["state"] in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(0.05)
        record = svc.worker_status("run-1", "red")

    runner_log = repo / ".hermes" / "workflows" / "run-1" / "workers" / "red-1-1.runner-log"
    log_text = runner_log.read_text() if runner_log.is_file() else "<no runner log>"
    assert record["state"] == "succeeded", (
        f"worker never reached succeeded (state={record['state']!r}); runner log:\n{log_text}"
    )
