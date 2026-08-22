"""Native Hermes v0.20 registration and fail-closed hcw/v1 mutation guard."""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
from pathlib import Path
from typing import Any

BOOTSTRAP_MARKER = "HCW_BOOTSTRAP_V1"
SCHEMA_VERSION = "hcw/v1"
_WRITE_TOOLS = {"write_file", "patch", "apply_patch", "execute_code"}
_TERMINAL_TOOLS = {"terminal", "exec_command", "run_terminal"}
_TEST_PATH = re.compile(r"(?:^|/)(?:tests?/.*|test_[^/]+|[^/]+_test\.[^/]+|[^/]+\.(?:test|spec)\.[^/]+)$")
_READ_ONLY_GIT = {"status", "diff", "log", "show", "rev-parse"}
_HCW_COMMANDS = {"create-run", "show", "approve-design", "approve-plan", "check", "commit", "review", "verify", "complete", "repair", "dispatch-worker", "worker-status"}
_CLAUDE_WORKER_COMMANDS = {"dispatch-worker", "worker-status"}
_CLAUDE_WORKER_STAGES = {"red", "green", "quality-review", "complete"}
_STAGE_PAYLOAD_NAMES = {
    "design": "approved-design.input.json",
    "plan": "approved-plan.input.json",
    "spec-review": "spec-review.input.json",
    "quality-review": "quality-review.input.json",
}


def _build_bootstrap() -> str:
    launcher = (Path(__file__).resolve().parent / "runtime" / "bin" / "hcw").resolve()
    run, error = _load_matching_run()
    if run is not None:
        stage, binding_error = _bound_active_stage(run)
        if stage is not None:
            repo = shlex.quote(str(run["repo_root"]))
            run_id = shlex.quote(str(run["id"]))
            payload = _stage_payload_path(run, stage)
            payload_arg = shlex.quote(str(payload)) if payload is not None else "<invalid-payload-path>"
            guidance = {
                "design": (f"approve-design {repo} {run_id} --json {payload_arg}",),
                "plan": (f"approve-plan {repo} {run_id} --json {payload_arg}",),
                "red": (f"dispatch-worker {repo} {run_id} red", f"worker-status {repo} {run_id} red", f"check {repo} {run_id} --timeout 600 red -- <failing-test-command>"),
                "green": (f"dispatch-worker {repo} {run_id} green", f"worker-status {repo} {run_id} green", f"commit {repo} {run_id} --message <quoted-commit-message>", f"check {repo} {run_id} --timeout 600 green -- <passing-test-command>"),
                "spec-review": (f"review {repo} {run_id} --json {payload_arg}",),
                "quality-review": (f"dispatch-worker {repo} {run_id} quality-review", f"worker-status {repo} {run_id} quality-review", f"review {repo} {run_id} --json {payload_arg}"),
                "verify": (f"check {repo} {run_id} --timeout 600 full -- <full-test-command>", f"check {repo} {run_id} --timeout 600 security -- <security-test-command>", f"verify {repo} {run_id}"),
                "live": (f"check {repo} {run_id} --timeout 600 live -- <live-acceptance-command>",),
                "complete": (f"dispatch-worker {repo} {run_id} complete", f"worker-status {repo} {run_id} complete", f"complete {repo} {run_id}"),
            }
            commands = "; ".join(f"{shlex.quote(str(launcher))} {command}" for command in guidance[stage])
            external = (
                " For this external stage, dispatch exactly once, poll worker-status at bounded intervals until "
                "the state is succeeded or failed, and run the later authoritative transition only after succeeded; "
                "on failed, do not transition HCW and block the Kanban task with the worker note."
                if stage in _CLAUDE_WORKER_STAGES else ""
            )
            return (
                f"{BOOTSTRAP_MARKER}: registered HCW stage {stage} for run {run['id']} in repository {run['repo_root']}. "
                f"Use only this active-stage command guidance; do not prefix environment assignments: {commands}. "
                f"Apply hcw orchestration and pinned superpowers:brainstorming principles.{external}"
            )
        error = binding_error
    if error is not None:
        return f"{BOOTSTRAP_MARKER}: registered HCW workflow identity is invalid; do not run lifecycle commands."
    commands = "; ".join(f"{launcher} {command}" for command in ("create-run", "approve-design", "approve-plan", "check", "commit", "review", "verify", "complete"))
    task = os.getenv("HERMES_KANBAN_TASK", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", task):
        task = "<kanban-task-id>"
    board = os.getenv("HERMES_KANBAN_BOARD", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", board):
        board = "<board-slug>"
    create = (
        f"{shlex.quote(str(launcher))} create-run {shlex.quote(str(Path.cwd().resolve()))} "
        f"--run-id {shlex.quote(task)} --package {shlex.quote(task)} "
        f"--scope <task-approved-path-or-glob> --board {shlex.quote(board)} --goal <quoted-task-goal>"
    )
    return (
        f"{BOOTSTRAP_MARKER}: installed lifecycle launcher is {launcher}. "
        f"For initial Kanban bootstrap, replace the angle-bracket scope/goal fields in this complete command; "
        f"do not omit arguments or prefix environment assignments: {create}. "
        f"The run id must equal HERMES_KANBAN_TASK. Use only: {commands}. "
        "Apply hcw orchestration and pinned superpowers:brainstorming principles."
    )


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


def _has_no_symlink_components(path: Path, root: Path) -> bool:
    """Refuse authority paths that traverse a symlink below their trusted root."""
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return False
    candidate = root
    if candidate.is_symlink():
        return False
    for part in parts:
        candidate /= part
        if candidate.is_symlink():
            return False
    return True


def _raw_git_path(path_text: str, parent: Path) -> Path | None:
    """Anchor Git metadata without resolving away its authority spelling."""
    if not path_text or "\0" in path_text:
        return None
    path = Path(path_text)
    return path if path.is_absolute() else parent / path


def _is_nonsymlink_directory(path: Path) -> bool:
    """Require every raw authority component to be a real directory before resolving."""
    if not path.is_absolute():
        return False
    candidate = Path(path.anchor)
    try:
        if not stat.S_ISDIR(candidate.lstat().st_mode):
            return False
        for component in path.parts[1:]:
            if component == ".":
                continue
            if component == "..":
                candidate = candidate.parent
                continue
            candidate /= component
            mode = candidate.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                return False
    except OSError:
        return False
    return True


def _read_regular_file(path: Path) -> str | None:
    """Read a metadata file only after rejecting links and special files."""
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def _canonical_identity_directory(value: Any) -> Path | None:
    """Accept only an exact canonical absolute non-symlink directory spelling."""
    if not isinstance(value, str) or not value or "\0" in value:
        return None
    raw = Path(value)
    if not raw.is_absolute() or str(raw) != value or not _is_nonsymlink_directory(raw):
        return None
    try:
        canonical = raw.resolve(strict=True)
    except OSError:
        return None
    return canonical if canonical == raw else None


def _gitdir_target(marker: Path) -> Path | None:
    """Parse Git's one-line linked-worktree marker without following it first."""
    text = _read_regular_file(marker)
    if text is None or "\0" in text:
        return None
    lines = text.splitlines()
    if len(lines) != 1:
        return None
    match = re.fullmatch(r"gitdir: (.+)", lines[0])
    return _raw_git_path(match.group(1), marker.parent) if match else None


def _git_commondir_target(gitdir: Path) -> Path | None:
    """Read a linked-worktree commondir only through a regular local file."""
    text = _read_regular_file(gitdir / "commondir")
    if text is None or "\0" in text:
        return None
    lines = text.splitlines()
    return _raw_git_path(lines[0], gitdir) if len(lines) == 1 and lines[0] else None


def _trusted_git_common_dir(worktree: Path) -> Path | None:
    """Return a canonical common dir only after validating its raw spelling."""
    try:
        raw_worktree = Path(os.path.abspath(worktree))
        if not _is_nonsymlink_directory(raw_worktree):
            return None
        marker = raw_worktree / ".git"
        marker_mode = marker.lstat().st_mode
        linked_gitdir: Path | None = None
        expected_common: Path | None = None
        if stat.S_ISDIR(marker_mode):
            if marker.is_symlink() or not _is_nonsymlink_directory(marker):
                return None
        elif stat.S_ISREG(marker_mode):
            linked_gitdir = _gitdir_target(marker)
            if linked_gitdir is None or not _is_nonsymlink_directory(linked_gitdir):
                return None
            commondir = linked_gitdir / "commondir"
            if os.path.lexists(commondir):
                expected_common = _git_commondir_target(linked_gitdir)
                if expected_common is None or not _is_nonsymlink_directory(expected_common):
                    return None
            else:
                expected_common = linked_gitdir
        else:
            return None
        top_text = subprocess.run(
            ["git", "-C", str(raw_worktree), "rev-parse", "--show-toplevel"],
            text=True, capture_output=True, check=True,
        ).stdout.strip()
        top = _raw_git_path(top_text, raw_worktree)
        if top != raw_worktree or top is None or not _is_nonsymlink_directory(top):
            return None
        common_text = subprocess.run(
            ["git", "-C", str(raw_worktree), "rev-parse", "--git-common-dir"],
            text=True, capture_output=True, check=True,
        ).stdout.strip()
        common = _raw_git_path(common_text, raw_worktree)
        if common is None or common.name != ".git" or not _is_nonsymlink_directory(common):
            return None
        canonical_common = common.resolve(strict=True)
        if linked_gitdir is None:
            return canonical_common if canonical_common == marker.resolve(strict=True) else None
        if expected_common is None or canonical_common != expected_common.resolve(strict=True):
            return None
        return canonical_common
    except (OSError, subprocess.CalledProcessError):
        return None


def _git_worktree_is_registered(repo: Path, worktree: Path) -> bool:
    try:
        worktree_common = _trusted_git_common_dir(worktree)
        if worktree_common is None:
            return False
        common_path = _trusted_git_common_dir(repo)
        if common_path is None or worktree_common != common_path:
            return False
        listing = subprocess.run(["git", "-C", str(repo), "worktree", "list", "--porcelain"], text=True, capture_output=True, check=True).stdout.splitlines()
        registered = {line.removeprefix("worktree ") for line in listing if line.startswith("worktree ")}
        return str(repo) in registered and str(worktree) in registered
    except (OSError, subprocess.CalledProcessError):
        return False


def _canonical_repository_for_worktree(worktree: Path) -> Path | None:
    """Return the canonical parent repository for this exact registered worktree."""
    try:
        common = _trusted_git_common_dir(worktree)
        if common is None:
            return None
        repo = common.parent
        return repo if _git_worktree_is_registered(repo, worktree) else None
    except (OSError, subprocess.CalledProcessError):
        return None


def _linked_task_root_allowed(worktree: Path) -> bool:
    """Recognize only the exact registered Kanban linked-worktree root."""
    task = os.getenv("HERMES_KANBAN_TASK")
    if (
        worktree.parent.name != ".worktrees"
        or not task
        or worktree.name != task
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", task)
    ):
        return False
    try:
        branch = subprocess.run(
            ["git", "-C", str(worktree), "branch", "--show-current"],
            text=True, capture_output=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return False
    primary = _canonical_repository_for_worktree(worktree)
    return branch == f"wt/{task}" and primary is not None and _git_worktree_is_registered(primary, worktree)


def _missing_locator_error(worktree: Path) -> str | None:
    """Recognize controlled linked worktrees without inferring any stage identity."""
    if worktree.parent.name != ".worktrees":
        return None
    if not worktree.name.startswith("hcw-"):
        return None if _linked_task_root_allowed(worktree) else "untrusted workflow worktree"
    repo = worktree.parent.parent
    if not _git_worktree_is_registered(repo, worktree):
        return "untrusted workflow worktree"
    workflows = repo / ".hermes" / "workflows"
    if not _has_no_symlink_components(workflows, repo):
        return "untrusted authoritative workflow state"
    if not workflows.is_dir():
        return "unregistered workflow worktree"
    matches = 0
    try:
        for run_dir in workflows.iterdir():
            manifest = run_dir / "run.json"
            if not run_dir.is_dir() or not _has_no_symlink_components(manifest, repo):
                return "untrusted authoritative workflow state"
            if not manifest.is_file():
                return "malformed authoritative workflow state"
            run = _object(manifest)
            if not run or run.get("schema_version") != SCHEMA_VERSION:
                return "malformed authoritative workflow state"
            run_repo = _canonical_identity_directory(run.get("repo_root"))
            run_worktree = _canonical_identity_directory(run.get("worktree_path"))
            if run_repo is None or run_worktree is None:
                return "malformed authoritative workflow state"
            if run_repo != repo:
                return "workflow state locator mismatch"
            if run_worktree == worktree:
                matches += 1
    except OSError:
        return "untrusted authoritative workflow state"
    if matches == 1:
        return "missing matching workflow locator"
    if matches > 1:
        return "ambiguous authoritative workflow state"
    return "unregistered workflow worktree"


def _load_matching_run() -> tuple[dict[str, Any] | None, str | None]:
    cwd = Path.cwd().resolve()
    locator_path = cwd / ".hermes" / "hcw-run.json"
    if not _has_no_symlink_components(locator_path, cwd):
        return None, "untrusted workflow locator"
    if not os.path.lexists(locator_path):
        return None, _missing_locator_error(cwd)
    identity = {name: os.getenv(name) for name in ("HCW_RUN_ID", "HERMES_KANBAN_TASK", "HERMES_PROFILE")}
    if not any(identity.values()):
        return None, None
    if not identity["HERMES_KANBAN_TASK"] or not identity["HERMES_PROFILE"]:
        return None, "incomplete workflow identity"
    locator = _object(locator_path)
    if locator is None:
        return None, "malformed matching workflow locator"
    repo = _canonical_identity_directory(locator.get("repo_root"))
    worktree = _canonical_identity_directory(locator.get("worktree_path"))
    if repo is None or worktree is None:
        return None, "malformed matching workflow locator"
    locator_run_id = locator.get("run_id")
    run_id = identity["HCW_RUN_ID"] or locator_run_id
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", run_id):
        return None, "invalid workflow run id"
    if locator.get("schema_version") != SCHEMA_VERSION or locator_run_id != run_id or cwd != worktree:
        return None, "workflow locator mismatch"
    if not _git_worktree_is_registered(repo, worktree):
        return None, "untrusted workflow worktree"
    manifest = repo / ".hermes" / "workflows" / run_id / "run.json"
    if not _has_no_symlink_components(manifest, repo):
        return None, "untrusted authoritative workflow state"
    run = _object(manifest)
    if not run or run.get("schema_version") != SCHEMA_VERSION or run.get("id") != run_id:
        return None, "malformed matching workflow state"
    run_repo = _canonical_identity_directory(run.get("repo_root"))
    run_worktree = _canonical_identity_directory(run.get("worktree_path"))
    if run_repo != repo or run_worktree != worktree:
        return None, "workflow state locator mismatch"
    return run, None


def _bound_active_stage(run: dict[str, Any]) -> tuple[str | None, str | None]:
    task, profile = os.getenv("HERMES_KANBAN_TASK"), os.getenv("HERMES_PROFILE")
    matches = [stage for stage, task_id in run.get("kanban_task_ids", {}).items() if task_id == task]
    if len(matches) != 1 or run.get("stage_profiles", {}).get(matches[0]) != profile:
        return None, "task/profile binding mismatch"
    stage = matches[0]
    if run.get("stage_statuses", {}).get(stage) != "active":
        return None, "workflow stage is not active"
    return stage, None


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


def _stage_payload_path(run: dict[str, Any], stage: str) -> Path | None:
    """Return the sole metadata input path writable by a JSON-consuming stage."""
    name = _STAGE_PAYLOAD_NAMES.get(stage)
    worktree = _canonical_identity_directory(run.get("worktree_path"))
    return worktree / ".hermes" / "hcw-inputs" / name if name is not None and worktree is not None else None


def _stage_payload_write_allowed(run: dict[str, Any], stage: str, candidate: str | None) -> bool:
    expected = _stage_payload_path(run, stage)
    if expected is None or not candidate or "\0" in candidate:
        return False
    raw = Path(candidate)
    if not raw.is_absolute() or candidate != os.path.normpath(candidate) or raw != expected:
        return False
    worktree = Path(run["worktree_path"])
    payload_root = expected.parent
    if not _has_no_symlink_components(expected, worktree):
        return False
    try:
        if os.path.lexists(payload_root) and (payload_root.is_symlink() or not payload_root.is_dir()):
            return False
        if os.path.lexists(expected) and (expected.is_symlink() or not stat.S_ISREG(expected.lstat().st_mode)):
            return False
    except OSError:
        return False
    return True


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


def _bootstrap_create_run_allowed(args: dict[str, Any] | None) -> bool:
    values = args or {}
    command = values.get("command", values.get("cmd", ""))
    if not isinstance(command, str) or not command.strip() or any(token in command for token in (";", "&&", "||", "|", ">", "<", "\n", "\r")):
        return False
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    if len(argv) < 5 or argv[1] != "create-run":
        return False
    expected_hcw = (Path(__file__).resolve().parent / "runtime" / "bin" / "hcw").resolve()
    try:
        executable = Path(argv[0]).resolve()
        repo = _canonical_identity_directory(argv[2])
        cwd = _canonical_identity_directory(str(Path.cwd()))
    except OSError:
        return False
    if executable != expected_hcw or repo is None or cwd is None or repo != cwd:
        return False
    canonical_repository = _canonical_repository_for_worktree(repo)
    if canonical_repository != repo and not _linked_task_root_allowed(repo):
        return False

    run_ids: list[str] = []
    for index, token in enumerate(argv[3:], start=3):
        if token == "--run-id":
            if index + 1 >= len(argv):
                return False
            run_ids.append(argv[index + 1])
        elif token.startswith("--run-id="):
            run_ids.append(token.split("=", 1)[1])
    if len(run_ids) != 1:
        return False
    requested_run_id = run_ids[0]
    task_id = os.getenv("HERMES_KANBAN_TASK")
    inherited_run_id = os.getenv("HCW_RUN_ID")
    if not task_id or requested_run_id != task_id:
        return False
    if inherited_run_id and inherited_run_id != task_id:
        return False
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", requested_run_id):
        return False

    locator = repo / ".hermes" / "hcw-run.json"
    manifest = repo / ".hermes" / "workflows" / requested_run_id / "run.json"
    if not _has_no_symlink_components(locator, repo) or not _has_no_symlink_components(manifest, repo):
        return False
    return not os.path.lexists(locator) and not os.path.lexists(manifest)


def _is_exact_authoritative_repo(path_text: str, run: dict[str, Any]) -> bool:
    """Accept only the immutable spelling stored in the authoritative run."""
    authoritative_text = run.get("repo_root")
    if not isinstance(authoritative_text, str):
        return False
    supplied = Path(path_text)
    authoritative = Path(authoritative_text)
    if not supplied.is_absolute() or not authoritative.is_absolute():
        return False
    if path_text != os.path.normpath(path_text) or authoritative_text != os.path.normpath(authoritative_text):
        return False
    try:
        resolved = supplied.resolve(strict=True)
        authoritative_resolved = authoritative.resolve(strict=True)
    except OSError:
        return False
    return path_text == str(resolved) == authoritative_text == str(authoritative_resolved)


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
            return subcommand == "show"
        if len(argv) < 4 or argv[3] != run.get("id"):
            return False
        if not _is_exact_authoritative_repo(argv[2], run):
            return False
        expected = {"design":{"approve-design"}, "plan":{"approve-plan"}, "red":{"check","dispatch-worker","worker-status"}, "green":{"check","commit","dispatch-worker","worker-status"}, "spec-review":{"review"}, "quality-review":{"review","dispatch-worker","worker-status"}, "verify":{"check","verify"}, "live":{"check"}, "complete":{"complete","dispatch-worker","worker-status"}}
        if subcommand not in expected.get(stage, set()):
            return False
        if subcommand == "check":
            check_index = 4
            if len(argv) > 5 and argv[4] == "--timeout":
                timeout_token = argv[5]
                if not timeout_token.isascii() or not timeout_token.isdigit() or not timeout_token.strip("0"):
                    return False
                check_index = 6
            if len(argv) <= check_index + 2 or argv[check_index + 1] != "--":
                return False
            check_type = argv[check_index]
            expected_check = {"red":"red","green":"green","verify":"full","live":"live"}.get(stage) if stage is not None else None
            return check_type == expected_check or (stage == "verify" and check_type == "security")
        if subcommand in _CLAUDE_WORKER_COMMANDS:
            if len(argv) < 5 or not _is_exact_authoritative_repo(argv[2], run) or argv[4] != stage:
                return False
            if subcommand == "worker-status":
                return len(argv) == 5
            return len(argv) == 5 or (stage in {"red", "green"} and len(argv) == 6 and argv[5] == "--retry-succeeded")
        if subcommand in {"approve-design", "approve-plan", "review"}:
            json_paths: list[str] = []
            index = 4
            while index < len(argv):
                token = argv[index]
                if token == "--json" and index + 1 < len(argv):
                    json_paths.append(argv[index + 1]); index += 2; continue
                if token.startswith("--json="):
                    json_paths.append(token.split("=", 1)[1]); index += 1; continue
                return False
            return stage is not None and len(json_paths) == 1 and _stage_payload_write_allowed(run, stage, json_paths[0])
        return True
    if argv[0] != "git" or len(argv) < 2:
        return False
    if argv[1] in _READ_ONLY_GIT or argv[1:3] == ["branch", "--show-current"]:
        return True
    return False


def _guard_decision(tool_name: str | None = None, args: dict[str, Any] | None = None) -> dict[str, str] | None:
    if tool_name not in _WRITE_TOOLS | _TERMINAL_TOOLS:
        return None
    if tool_name in _TERMINAL_TOOLS and _bootstrap_create_run_allowed(args):
        return None
    run, error = _load_matching_run()
    if run is None:
        if tool_name in _TERMINAL_TOOLS and error is None and _terminal_allowed(None, None, args):
            return None
        return {"action": "block", "message": error or "workflow identity required for mutation"}
    stage, binding_error = _bound_active_stage(run)
    if stage is None:
        return {"action": "block", "message": binding_error or "task/profile binding mismatch"}
    if tool_name in _TERMINAL_TOOLS:
        return None if _terminal_allowed(run, stage, args) else {"action": "block", "message": "terminal command is not allowlisted for this workflow stage"}
    path = _explicit_path(args)
    if _stage_payload_write_allowed(run, stage, path):
        return None
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
