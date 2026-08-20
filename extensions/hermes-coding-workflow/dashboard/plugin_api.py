"""Read-only, descriptor-safe projection of Hermes Coding Workflow runs."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Protocol

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_PR_URL = re.compile(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/[1-9][0-9]*\Z")
_SECRET = re.compile(r"(?i)(?:token|password|secret|api[_-]?key|authorization|credential)\s*[:=]\s*[^\s,;]+")
_MAX_ITEMS, _MAX_TEXT, _MAX_FILE_BYTES = 100, 500, 256 * 1024
_STAGE_DEPENDENCIES = {"design": [], "plan": ["design"], "red": ["plan"], "green": ["red"], "spec-review": ["green"], "quality-review": ["spec-review"], "verify": ["quality-review"], "live": ["verify"], "complete": ["live"]}
_ARTIFACTS = {"run.json": "Run record", "approved-design.json": "Approved design", "plan.json": "Plan", "evidence.jsonl": "Evidence", "reviews.json": "Reviews", "verification.json": "Verification", "handoff.json": "Handoff"}
_OPEN_FILE = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
_OPEN_DIR = _OPEN_FILE | getattr(os, "O_DIRECTORY", 0)


class ProjectionError(RuntimeError): pass


class Adapter(Protocol):
    def boards(self) -> list[dict[str, Any]]: ...
    def runs(self, board: str) -> list[dict[str, Any]]: ...
    def run(self, board: str, run_id: str) -> dict[str, Any] | None: ...


def _id(value: str, kind: str) -> str:
    if not _IDENTIFIER.fullmatch(value) or value in {".", ".."}: raise HTTPException(422, f"invalid {kind} identifier")
    return value


def _safe_text(value: Any, limit: int = _MAX_TEXT) -> str:
    """The only conversion from untrusted text into a response field."""
    if not isinstance(value, str): return ""
    return _SECRET.sub("[redacted]", value.replace("\x00", ""))[:limit]


def _items(value: Any) -> list[Any]: return value[:_MAX_ITEMS] if isinstance(value, list) else []
def _sha(value: Any) -> str | None: return value if isinstance(value, str) and _SHA.fullmatch(value) else None
def _hash(value: Any) -> str | None: return value if isinstance(value, str) and _HASH.fullmatch(value) else None


def _open_dir_at(parent_fd: int, name: str) -> int:
    if name != ".hermes" and not _IDENTIFIER.fullmatch(name): raise ProjectionError("unsafe directory")
    try:
        fd = os.open(name, _OPEN_DIR, dir_fd=parent_fd)
        if not stat.S_ISDIR(os.fstat(fd).st_mode): raise ProjectionError("unsafe directory")
        return fd
    except OSError as exc: raise ProjectionError("unsafe directory") from exc


def _read_file(root_fd: int, name: str, maximum: int = _MAX_FILE_BYTES) -> bytes | None:
    """Open by descriptor, then inspect that same descriptor before bounded read."""
    if name not in _ARTIFACTS: return None
    try:
        fd = os.open(name, _OPEN_FILE, dir_fd=root_fd)
    except FileNotFoundError: return None
    except OSError as exc: raise ProjectionError("unsafe artifact") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size < 0 or info.st_size > maximum: raise ProjectionError("unsafe artifact")
        chunks, remaining = [], info.st_size
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk: raise ProjectionError("truncated artifact")
            chunks.append(chunk); remaining -= len(chunk)
        return b"".join(chunks)
    except OSError as exc: raise ProjectionError("unreadable artifact") from exc
    finally: os.close(fd)


def _json_file(root_fd: int, name: str) -> dict[str, Any] | None:
    raw = _read_file(root_fd, name)
    if raw is None: return None
    try:
        value = json.loads(raw.decode("utf-8"))
        return value if isinstance(value, dict) else None
    except (UnicodeError, json.JSONDecodeError): return None


def _safe_repo(value: Any) -> Path | None:
    if not isinstance(value, str) or not value: return None
    path = Path(value)
    try:
        resolved = path.resolve(strict=True)
        return resolved if path.is_absolute() and resolved.is_dir() and (resolved / ".git").exists() else None
    except OSError: return None


def _digest_record(record: dict[str, Any]) -> str:
    value = dict(record); value.pop("evidence_hash", None)
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _evidence(root_fd: int) -> list[dict[str, Any]]:
    raw = _read_file(root_fd, "evidence.jsonl")
    if raw is None: return []
    try: lines = raw.decode("utf-8").splitlines()
    except UnicodeError as exc: raise ProjectionError("unreadable evidence") from exc
    if len(lines) > _MAX_ITEMS: raise ProjectionError("too much evidence")
    records, previous = [], None
    for line in lines:
        try: record = json.loads(line)
        except json.JSONDecodeError as exc: raise ProjectionError("malformed evidence") from exc
        if not isinstance(record, dict) or record.get("schema_version") != "hcw/v1" or record.get("kind") != "evidence" or record.get("previous_evidence_hash") != previous or not _hash(record.get("artifact_sha256")):
            raise ProjectionError("malformed evidence chain")
        known = record.get("evidence_hash")
        if not _hash(known) or known != _digest_record(record) or not _sha(record.get("commit_sha")) or not isinstance(record.get("exit_code"), int): raise ProjectionError("invalid evidence")
        records.append(record); previous = known
    return records


def _valid_run(run: dict[str, Any]) -> bool:
    required = {"schema_version", "kind", "id", "revision", "created_at", "updated_at", "package_id", "base_sha", "head_sha", "branch", "status", "attempt", "kanban_board", "kanban_task_ids", "stage_profiles", "stage_statuses", "dispatches"}
    if not required.issubset(run) or run.get("schema_version") != "hcw/v1" or run.get("kind") != "run" or not isinstance(run.get("revision"), int) or run["revision"] < 0 or not _IDENTIFIER.fullmatch(str(run.get("id"))) or not _sha(run.get("base_sha")) or not _sha(run.get("head_sha")) or not isinstance(run.get("attempt"), int): return False
    for field in ("kanban_task_ids", "stage_profiles", "stage_statuses", "dispatches"):
        if not isinstance(run.get(field), dict): return False
    if set(run["dispatches"]) != set(_STAGE_DEPENDENCIES): return False
    for stage, dispatch in run["dispatches"].items():
        if stage not in _STAGE_DEPENDENCIES or not isinstance(dispatch, dict) or set(dispatch) != {"stage", "task_id", "profile", "provider", "model", "session_id", "attempt", "brief_hash"} or dispatch.get("stage") != stage or not isinstance(dispatch.get("attempt"), int) or not _hash(dispatch.get("brief_hash")): return False
    return True


class FileAdapter:
    """Uses Hermes board metadata as authority and never returns filesystem data."""
    def _metadata(self) -> list[dict[str, Any]]:
        try:
            from hermes_cli import kanban_db
            return [x for x in kanban_db.list_boards(include_archived=False) if isinstance(x, dict)]
        except Exception: return []

    def _repo(self, metadata: dict[str, Any]) -> Path | None:
        declared = _safe_repo(metadata.get("default_workdir")); project_id = metadata.get("project_id")
        if not project_id: return declared
        try:
            from hermes_cli import projects_db
            with projects_db.connect_closing() as conn: project = projects_db.get_project(conn, str(project_id))
            primary = _safe_repo(getattr(project, "primary_path", None)) if project else None
            return primary if primary and (declared is None or declared == primary) else None
        except Exception: return None

    def _board(self, board: str) -> tuple[dict[str, Any], Path] | None:
        for item in self._metadata():
            if item.get("slug") == board and (repo := self._repo(item)): return item, repo
        return None

    def boards(self) -> list[dict[str, Any]]:
        return [{"id": slug, "label": _safe_text(item.get("name") or slug, 120), "repo": _safe_text(repo.name, 120)} for item in self._metadata() if isinstance((slug := item.get("slug")), str) and _IDENTIFIER.fullmatch(slug) if (repo := self._repo(item))][:_MAX_ITEMS]

    def _workflow_fd(self, board: str, run_id: str) -> int | None:
        entry = self._board(board)
        if entry is None: return None
        try:
            repo_fd = os.open(entry[1], _OPEN_DIR)
            hermes_fd = _open_dir_at(repo_fd, ".hermes")
            workflows_fd = _open_dir_at(hermes_fd, "workflows")
            run_fd = _open_dir_at(workflows_fd, run_id)
            for fd in (repo_fd, hermes_fd, workflows_fd): os.close(fd)
            return run_fd
        except (OSError, ProjectionError):
            for fd in (locals().get("repo_fd"), locals().get("hermes_fd"), locals().get("workflows_fd")):
                if isinstance(fd, int):
                    try: os.close(fd)
                    except OSError: pass
            return None

    def _compose(self, root_fd: int) -> dict[str, Any] | None:
        try:
            before = _json_file(root_fd, "run.json")
            if before is None: return None
            if not _valid_run(before): raise ProjectionError("malformed run")
            revision, result = before["revision"], dict(before)
            for name in ("approved-design.json", "plan.json", "verification.json", "handoff.json"):
                value = _json_file(root_fd, name)
                if value is not None: result[name] = value
            reviews = _json_file(root_fd, "reviews.json")
            if reviews is not None:
                if not isinstance(reviews.get("reviews"), list): raise ProjectionError("malformed reviews")
                result["reviews"] = reviews["reviews"]
            result["evidence"] = _evidence(root_fd)
            result["_artifacts"] = [{"id": name, "label": label} for name, label in _ARTIFACTS.items() if _read_file(root_fd, name) is not None]
            after = _json_file(root_fd, "run.json")
            if after is None or not _valid_run(after) or after["revision"] != revision: raise ProjectionError("run projection is changing")
            return result
        finally: os.close(root_fd)

    def run(self, board: str, run_id: str) -> dict[str, Any] | None:
        fd = self._workflow_fd(board, run_id); return self._compose(fd) if fd is not None else None

    def runs(self, board: str) -> list[dict[str, Any]]:
        entry = self._board(board)
        if entry is None: return []
        try:
            repo_fd = os.open(entry[1], _OPEN_DIR); hermes_fd = _open_dir_at(repo_fd, ".hermes"); workflows_fd = _open_dir_at(hermes_fd, "workflows")
            names = os.listdir(workflows_fd)
        except (OSError, ProjectionError): return []
        finally:
            for fd in (locals().get("repo_fd"), locals().get("hermes_fd"), locals().get("workflows_fd")):
                if isinstance(fd, int):
                    try: os.close(fd)
                    except OSError: pass
        result = []
        for name in names:
            if len(result) == _MAX_ITEMS: break
            if _IDENTIFIER.fullmatch(name):
                try:
                    if (run := self.run(board, name)): result.append(run)
                except ProjectionError: continue
        return result


_adapter: Adapter = FileAdapter()
def set_adapter(adapter: Adapter) -> None:
    global _adapter; _adapter = adapter


def _dispatch(run: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    dispatches = run["dispatches"]
    active = next((stage for stage in _STAGE_DEPENDENCIES if run["stage_statuses"].get(stage) == "active" and stage in dispatches), None)
    stage = active or next((stage for stage in reversed(tuple(_STAGE_DEPENDENCIES)) if stage in dispatches), "")
    return stage, dispatches.get(stage, {})


def _run_dto(run: dict[str, Any]) -> dict[str, Any]:
    stage, current = _dispatch(run)
    return {"id": _safe_text(run.get("id"), 80), "status": _safe_text(run.get("status"), 80), "revision": run["revision"], "package_id": _safe_text(run.get("package_id"), 80), "attempt": run["attempt"], "branch": _safe_text(run.get("branch"), 200), "base_sha": _sha(run.get("base_sha")), "candidate_sha": _sha(run.get("head_sha")), "kanban_board": _safe_text(run.get("kanban_board"), 120), "current_dispatch": {"stage": _safe_text(stage, 80), "task_id": _safe_text(current.get("task_id"), 120), "profile": _safe_text(current.get("profile"), 120), "provider": _safe_text(current.get("provider"), 120), "model": _safe_text(current.get("model"), 120), "session_id": _safe_text(current.get("session_id"), 120), "attempt": current.get("attempt") if isinstance(current.get("attempt"), int) else 0}}


def _detail(run: dict[str, Any]) -> dict[str, Any]:
    tasks, statuses, profiles, dispatches = run["kanban_task_ids"], run["stage_statuses"], run["stage_profiles"], run["dispatches"]
    stages = [{"id": stage, "status": _safe_text(statuses.get(stage), 80), "depends_on": deps, "task_id": _safe_text(tasks.get(stage), 120), "profile": _safe_text((dispatches.get(stage) or {}).get("profile") or profiles.get(stage), 120), "dispatch": {key: _safe_text((dispatches.get(stage) or {}).get(key), 120) for key in ("provider", "model", "session_id")}} for stage, deps in _STAGE_DEPENDENCIES.items()]
    reviews = []
    for review in _items(run.get("reviews")):
        if not isinstance(review, dict): continue
        reviewer = review.get("reviewer") if isinstance(review.get("reviewer"), dict) else {}
        dispositions = {item.get("finding_id"): item.get("disposition") for item in _items(review.get("dispositions")) if isinstance(item, dict)}
        findings = [{"id": _safe_text(item.get("id"), 120), "severity": _safe_text(item.get("severity"), 40), "description": _safe_text(item.get("description"), _MAX_TEXT), "disposition": _safe_text(dispositions.get(item.get("id")), 80)} for item in _items(review.get("findings")) if isinstance(item, dict)]
        reviews.append({"reviewer": {key: _safe_text(reviewer.get(key), 120) for key in ("profile", "task_id", "session_id", "provider", "model")}, "decision": _safe_text(review.get("decision"), 80), "findings": findings, "dispositions": [{"finding_id": _safe_text(item.get("finding_id"), 120), "disposition": _safe_text(item.get("disposition"), 80)} for item in _items(review.get("dispositions")) if isinstance(item, dict)]})
    evidence = [{"name": _safe_text(item.get("type"), 80), "status": "passed" if item.get("exit_code") == 0 else "failed", "summary": _safe_text(item.get("summary")), "commit_sha": _sha(item.get("commit_sha")), "artifact_sha256": _hash(item.get("artifact_sha256"))} for item in _items(run.get("evidence")) if isinstance(item, dict)]
    attempts = [{"attempt": item.get("attempt") if isinstance(item.get("attempt"), int) else 0, "status": _safe_text(item.get("reason") or "archived", 80), "summary": _safe_text(item.get("reason")), "candidate_sha": _sha(item.get("head_sha"))} for item in _items(run.get("attempt_history")) if isinstance(item, dict)]
    verification = run.get("verification.json") if isinstance(run.get("verification.json"), dict) else {}; handoff = run.get("handoff.json") if isinstance(run.get("handoff.json"), dict) else {}
    stale = any(_sha(item.get("reviewed_sha")) not in {None, _sha(run.get("head_sha"))} for item in _items(run.get("reviews")) if isinstance(item, dict)) or _sha(verification.get("candidate_sha")) not in {None, _sha(run.get("head_sha"))}
    blockers = [{"kind": "repair", "summary": _safe_text(item.get("reason"))} for item in _items(run.get("attempt_history")) if isinstance(item, dict) and item.get("reason")]
    pr_url = handoff.get("pr_url")
    return {"run": _run_dto(run), "stages": stages, "reviews": reviews, "evidence": evidence, "attempt_history": attempts, "blockers": blockers, "health": {"stale": stale, "status": "stale" if stale else "current"}, "handoff": {"pr_url": pr_url if isinstance(pr_url, str) and _PR_URL.fullmatch(pr_url) else None}, "artifacts": [{"id": _safe_text(item.get("id"), 80), "label": _safe_text(item.get("label"), 120)} for item in _items(run.get("_artifacts")) if isinstance(item, dict)]}


@router.get("/boards")
def boards() -> dict[str, list[dict[str, str]]]: return {"boards": [{"id": _id(str(item.get("id", "")), "board"), "label": _safe_text(item.get("label"), 120), "repo": _safe_text(item.get("repo"), 120)} for item in _items(_adapter.boards()) if isinstance(item, dict)]}


def _resolve(board: str, run_id: str | None = None) -> dict[str, Any] | None:
    board = _id(board, "board")
    if board not in {item["id"] for item in boards()["boards"]}: raise HTTPException(404, "board not found")
    try: return _adapter.run(board, _id(run_id, "run")) if run_id else None
    except ProjectionError as exc: raise HTTPException(409, "run projection is changing or malformed; retry polling") from exc


@router.get("/runs")
def runs(board: str = Query(...)) -> dict[str, list[dict[str, Any]]]: _resolve(board); return {"runs": [_run_dto(item) for item in _items(_adapter.runs(board)) if isinstance(item, dict)]}


@router.get("/runs/{run_id}")
def run_detail(run_id: str, board: str = Query(...)) -> dict[str, Any]:
    run = _resolve(board, run_id)
    if run is None: raise HTTPException(404, "run not found")
    return _detail(run)


@router.get("/runs/{run_id}/{projection}")
def projection(run_id: str, projection: str, board: str = Query(...)) -> dict[str, Any]:
    if projection not in {"stages", "reviews", "evidence", "blockers", "health"}: raise HTTPException(404, "projection not found")
    run = _resolve(board, run_id)
    if run is None: raise HTTPException(404, "run not found")
    return {projection: _detail(run)[projection]}
