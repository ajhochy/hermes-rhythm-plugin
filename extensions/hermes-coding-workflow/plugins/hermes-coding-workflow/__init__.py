"""Native Hermes v0.20 registration and fail-closed hcw/v1 mutation guard."""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

BOOTSTRAP_MARKER = "HCW_BOOTSTRAP_V1"
SCHEMA_VERSION = "hcw/v1"
_WRITE_TOOLS = {"write_file", "patch", "apply_patch"}
_TERMINAL_TOOLS = {"terminal", "exec_command", "run_terminal"}
_TEST_PATH = re.compile(r"(?:^|/)(?:tests?/.*|test_[^/]+|[^/]+_test\.[^/]+|[^/]+\.(?:test|spec)\.[^/]+)$")
_READ_ONLY_GIT = {"status", "diff", "log", "show", "rev-parse"}
_HCW_COMMANDS = {"create-run", "show", "approve-design", "approve-plan", "check", "commit", "review", "verify", "complete", "repair"}


def _build_bootstrap() -> str:
    launcher = (Path(__file__).resolve().parent / "runtime" / "bin" / "hcw").resolve()
    commands = "; ".join(f"{launcher} {command}" for command in ("create-run", "approve-design", "approve-plan", "check", "commit", "review", "verify", "complete"))
    return f"{BOOTSTRAP_MARKER}: installed lifecycle launcher is {launcher}. Use only: {commands}. Apply hcw orchestration and pinned superpowers:brainstorming principles."


def _skills_root() -> Path:
    here = Path(__file__).resolve().parent
    for candidate in (here / "skills", here.parents[1] / "skills"):
        if candidate.is_dir():
            return candidate
    raise RuntimeError("hcw plugin: missing role skills; reinstall")


def _object(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _git_worktree_is_registered(repo: Path, worktree: Path) -> bool:
    try:
        common = subprocess.run(["git", "-C", str(repo), "rev-parse", "--git-common-dir"], text=True, capture_output=True, check=True).stdout.strip()
        common_path = (repo / common).resolve() if not Path(common).is_absolute() else Path(common).resolve()
        if common_path != (repo / ".git").resolve():
            return False
        listing = subprocess.run(["git", "-C", str(repo), "worktree", "list", "--porcelain"], text=True, capture_output=True, check=True).stdout.splitlines()
        return any(line == f"worktree {worktree}" for line in listing)
    except (OSError, subprocess.CalledProcessError):
        return False


def _load_matching_run() -> tuple[dict[str, Any] | None, str | None]:
    identity = {name: os.getenv(name) for name in ("HCW_RUN_ID", "HERMES_KANBAN_TASK", "HERMES_PROFILE")}
    if not any(identity.values()):
        return None, None
    if not all(identity.values()):
        return None, "incomplete workflow identity"
    run_id = identity["HCW_RUN_ID"]
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", run_id):
        return None, "invalid workflow run id"
    cwd = Path.cwd().resolve()
    locator = _object(cwd / ".hermes" / "hcw-run.json")
    if locator is None:
        return None, "malformed matching workflow locator"
    try:
        repo = Path(locator["repo_root"]).resolve()
        worktree = Path(locator["worktree_path"]).resolve()
    except (KeyError, TypeError, OSError):
        return None, "malformed matching workflow locator"
    if locator.get("schema_version") != SCHEMA_VERSION or locator.get("run_id") != run_id or cwd != worktree:
        return None, "workflow locator mismatch"
    if not _git_worktree_is_registered(repo, worktree):
        return None, "untrusted workflow worktree"
    run = _object(repo / ".hermes" / "workflows" / run_id / "run.json")
    if not run or run.get("schema_version") != SCHEMA_VERSION or run.get("id") != run_id:
        return None, "malformed matching workflow state"
    if Path(str(run.get("repo_root", ""))).resolve() != repo or Path(str(run.get("worktree_path", ""))).resolve() != worktree:
        return None, "workflow state locator mismatch"
    return run, None


def _explicit_path(args: dict[str, Any] | None) -> str | None:
    values = args or {}
    path = values.get("path", values.get("file_path", values.get("target")))
    return path if isinstance(path, str) and path else None


def _scoped_path(run: dict[str, Any], candidate: str | None, *, tests_only: bool = False) -> bool:
    if not candidate or Path(candidate).is_absolute() or ".." in Path(candidate).parts:
        return False
    worktree = Path(run["worktree_path"]).resolve()
    try:
        relative = (Path.cwd() / candidate).resolve().relative_to(worktree).as_posix()
    except (OSError, ValueError):
        return False
    if relative.startswith((".git/", ".hermes/")) or relative in {".git", ".hermes"}:
        return False
    in_scope = any(fnmatch.fnmatch(relative, pattern) for pattern in run.get("scope", []) if isinstance(pattern, str))
    return in_scope and (not tests_only or bool(_TEST_PATH.search(relative)))


def _verified_red(run: dict[str, Any]) -> bool:
    evidence = Path(run["repo_root"]) / ".hermes" / "workflows" / run["id"] / "evidence.jsonl"
    previous = None
    try:
        for line in evidence.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            known = item.pop("evidence_hash", None)
            digest = hashlib.sha256(json.dumps(item, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if item.get("previous_evidence_hash") != previous or known != digest:
                return False
            previous = known
            if item.get("type") == "red" and item.get("commit_sha") == run.get("base_sha") and isinstance(item.get("exit_code"), int) and item["exit_code"] != 0:
                return True
    except (OSError, json.JSONDecodeError, TypeError):
        return False
    return False


def _terminal_allowed(run: dict[str, Any] | None, stage: str | None, args: dict[str, Any] | None) -> bool:
    values = args or {}
    command = values.get("command", values.get("cmd", ""))
    if not isinstance(command, str) or not command.strip() or any(token in command for token in (";", "&&", "||", "|", ">", "<", "\n", "\r")):
        return False
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    if not argv:
        return False
    expected_hcw = (Path(__file__).resolve().parent / "runtime" / "bin" / "hcw").resolve()
    try:
        executable = Path(argv[0]).resolve()
    except OSError:
        executable = Path(argv[0])
    if executable == expected_hcw and len(argv) >= 2 and argv[1] in _HCW_COMMANDS:
        subcommand = argv[1]
        if run is None:
            return subcommand in {"create-run", "show"}
        if len(argv) < 4 or argv[3] != run.get("id"):
            return False
        expected = {"design":{"approve-design"}, "plan":{"approve-plan"}, "red":{"check"}, "green":{"check","commit"}, "spec-review":{"review"}, "quality-review":{"review"}, "verify":{"check","verify"}, "live":{"check"}, "complete":{"complete"}}
        if subcommand not in expected.get(stage, set()):
            return False
        if subcommand == "check":
            return len(argv) >= 5 and (argv[4] == {"red":"red","green":"green","verify":"full","live":"live"}.get(stage) or (stage == "verify" and argv[4] == "security"))
        return True
    if argv[0] != "git" or len(argv) < 2:
        return False
    if argv[1] in _READ_ONLY_GIT or argv[1:3] == ["branch", "--show-current"]:
        return True
    return False


def _guard_decision(tool_name: str | None = None, args: dict[str, Any] | None = None) -> dict[str, str] | None:
    if tool_name not in _WRITE_TOOLS | _TERMINAL_TOOLS:
        return None
    run, error = _load_matching_run()
    if run is None:
        if tool_name in _TERMINAL_TOOLS and error is None and _terminal_allowed(None, None, args):
            return None
        return {"action": "block", "message": error or "workflow identity required for mutation"}
    task, profile = os.environ["HERMES_KANBAN_TASK"], os.environ["HERMES_PROFILE"]
    matches = [stage for stage, task_id in run.get("kanban_task_ids", {}).items() if task_id == task]
    if len(matches) != 1 or run.get("stage_profiles", {}).get(matches[0]) != profile:
        return {"action": "block", "message": "task/profile binding mismatch"}
    stage = matches[0]
    if run.get("stage_statuses", {}).get(stage) != "active":
        return {"action": "block", "message": "workflow stage is not active"}
    if tool_name in _TERMINAL_TOOLS:
        return None if _terminal_allowed(run, stage, args) else {"action": "block", "message": "terminal command is not allowlisted for this workflow stage"}
    path = _explicit_path(args)
    if stage == "red":
        if _scoped_path(run, path, tests_only=True):
            return None
        return {"action": "block", "message": "RED permits explicit scoped test-path writes only"}
    if stage != "green":
        return {"action": "block", "message": "this workflow role may not mutate source"}
    if not _verified_red(run):
        return {"action": "block", "message": "observed RED evidence required"}
    return None if _scoped_path(run, path) else {"action": "block", "message": "write target is outside the registered workflow scope"}


def _pre_tool_call(tool_name: str | None = None, args: dict[str, Any] | None = None, **_: Any) -> dict[str, str] | None:
    return _guard_decision(tool_name, args)


def register(ctx: Any) -> None:
    for skill in sorted(_skills_root().glob("*/SKILL.md")):
        ctx.register_skill(skill.parent.name, skill)
    ctx.register_hook("pre_llm_call", lambda is_first_turn=None, **_: {"context": _build_bootstrap()} if is_first_turn else None)
    ctx.register_hook("pre_tool_call", _pre_tool_call)
