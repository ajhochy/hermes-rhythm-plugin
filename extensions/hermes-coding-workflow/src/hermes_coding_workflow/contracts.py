"""The small, dependency-free authoritative hcw/v1 record validators."""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

SCHEMA_VERSION = "hcw/v1"
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
STAGES = ("design", "plan", "red", "green", "spec-review", "quality-review", "verify", "live", "complete")
PROFILES = {"design": "dev-planner", "plan": "dev-planner", "red": "dev-contract", "green": "dev-builder", "spec-review": "dev-spec-reviewer", "quality-review": "dev-quality-reviewer", "verify": "dev-verifier", "live": "dev-verifier", "complete": "dev-recorder"}

# Deterministic external-backend tier map. design/plan/spec-review/verify/live stay on the
# Hermes/OpenAI-native orchestrator; these four stages are executed by an external, Hermes-
# dispatched Claude Code CLI subprocess authenticated by its own account/Team login (never an
# API key inside Hermes).
CLAUDE_BACKEND = "claude-code-cli"
CLAUDE_STAGES = ("red", "green", "quality-review", "complete")
CLAUDE_TIER_MODELS = {"red": "claude-sonnet-4-6", "green": "claude-sonnet-4-6", "quality-review": "claude-opus-4-6", "complete": "claude-haiku-4-5"}
WORKER_STATES = {"queued", "running", "succeeded", "failed"}
WORKER_FIELDS = {"schema_version", "kind", "id", "created_at", "updated_at", "run_id", "stage", "task_id", "profile", "backend", "model", "attempt", "worker_attempt", "brief_hash", "worktree_path", "pid", "state", "stdout_path", "stderr_path", "stdout_sha256", "stderr_sha256", "exit_code", "note", "design_sha256", "plan_sha256", "dispatch_sha256", "repair_context_sha256", "process_identity"}
LEGACY_WORKER_FIELDS = WORKER_FIELDS - {"repair_context_sha256"}

def full_sha(value: object) -> bool: return isinstance(value, str) and bool(SHA.fullmatch(value))
def _valid_attempt_history_item(item: object) -> bool:
    if not isinstance(item, dict): return False
    base_keys = {"attempt", "worktree_path", "head_sha"}
    if set(item) - base_keys - {"attempt_base_sha","next_attempt_base_sha"}: return False
    if not isinstance(item.get("attempt"), int) or item["attempt"] < 1: return False
    if not _text(item.get("worktree_path"), 4096) or not item.get("worktree_path"): return False
    if not full_sha(item.get("head_sha")): return False
    if "attempt_base_sha" in item and not full_sha(item["attempt_base_sha"]): return False
    if "next_attempt_base_sha" in item and not full_sha(item["next_attempt_base_sha"]): return False
    return True
def valid_run_id(value: object) -> bool: return isinstance(value, str) and bool(RUN_ID.fullmatch(value))
def _text(value: object, maximum: int = 4096) -> bool: return isinstance(value, str) and bool(value) and len(value) <= maximum
def _actor(value: object) -> bool:
    return isinstance(value, Mapping) and set(value) == {"profile", "task_id", "session_id", "model", "provider"} and all(_text(value.get(key), 160) for key in ("profile", "task_id", "session_id", "model", "provider"))
def _argv(value: object) -> bool: return isinstance(value, list) and bool(value) and len(value) <= 32 and all(_text(v, 512) and "\n" not in v and "\r" not in v for v in value)
def _dispatch(stage: str, value: object) -> bool:
    return isinstance(value, Mapping) and set(value) == {"stage", "task_id", "profile", "provider", "model", "session_id", "attempt", "brief_hash"} and value.get("stage") == stage and _text(value.get("task_id"), 160) and _text(value.get("profile"), 160) and _text(value.get("provider"), 160) and _text(value.get("model"), 160) and _text(value.get("session_id"), 160) and isinstance(value.get("attempt"), int) and value["attempt"] >= 1 and isinstance(value.get("brief_hash"), str) and bool(re.fullmatch(r"[0-9a-f]{64}", value["brief_hash"]))

def validate_design(value: object) -> bool:
    return isinstance(value, Mapping) and set(value) == {"observable_outcome", "requirements", "acceptance_criteria", "approved"} and _text(value.get("observable_outcome")) and value.get("approved") is True and isinstance(value.get("requirements"), list) and value["requirements"] and all(isinstance(x, Mapping) and set(x) == {"id", "description"} and _text(x.get("id"), 80) and _text(x.get("description")) for x in value["requirements"]) and isinstance(value.get("acceptance_criteria"), list) and value["acceptance_criteria"] and all(_text(x) for x in value["acceptance_criteria"])

def validate_plan(value: object, requirement_ids: set[str] | None = None) -> bool:
    if not isinstance(value, Mapping) or set(value) != {"tasks", "commands", "approved"} or value.get("approved") is not True or not isinstance(value.get("tasks"), list) or not value["tasks"]: return False
    seen: set[str] = set()
    for task in value["tasks"]:
        if not isinstance(task, Mapping) or set(task) != {"id", "description", "paths", "test_command", "requirement_ids"} or not _text(task.get("id"), 80) or task["id"] in seen or not _text(task.get("description")) or not isinstance(task.get("paths"), list) or not task["paths"] or not all(_text(path, 512) and not path.startswith("/") and ".." not in path.split("/") for path in task["paths"]) or not _argv(task.get("test_command")) or not isinstance(task.get("requirement_ids"), list) or not task["requirement_ids"]: return False
        seen.add(task["id"])
        if requirement_ids is not None and not set(task["requirement_ids"]).issubset(requirement_ids): return False
    commands=value.get("commands")
    if not isinstance(commands, Mapping) or set(commands) != {"red","green","full","security","live"}: return False
    covered:set[str]=set()
    for stage, command in commands.items():
        if not isinstance(command, Mapping) or set(command) != {"argv","requirement_ids"} or not _argv(command.get("argv")) or not isinstance(command.get("requirement_ids"), list) or not command["requirement_ids"]: return False
        ids=set(command["requirement_ids"])
        if len(ids) != len(command["requirement_ids"]) or (requirement_ids is not None and not ids.issubset(requirement_ids)): return False
        covered |= ids
    return commands["red"]["argv"] == commands["green"]["argv"] and (requirement_ids is None or covered == requirement_ids)

def validate_worker(value: object) -> bool:
    if not isinstance(value, Mapping) or frozenset(value) not in {frozenset(WORKER_FIELDS), frozenset(LEGACY_WORKER_FIELDS)} or value.get("schema_version") != SCHEMA_VERSION or value.get("kind") != "worker": return False
    if not valid_run_id(value.get("run_id")) or value.get("stage") not in CLAUDE_STAGES or not _text(value.get("task_id"), 160) or not _text(value.get("profile"), 160): return False
    if value.get("backend") != CLAUDE_BACKEND or not _text(value.get("model"), 160): return False
    if not isinstance(value.get("attempt"), int) or value["attempt"] < 1 or not isinstance(value.get("worker_attempt"), int) or value["worker_attempt"] < 1: return False
    if not isinstance(value.get("brief_hash"), str) or not re.fullmatch(r"[0-9a-f]{64}", value["brief_hash"]) or not _text(value.get("worktree_path"), 4096): return False
    pid = value.get("pid")
    if pid is not None and not (isinstance(pid, int) and pid > 0): return False
    if value.get("state") not in WORKER_STATES: return False
    for key in ("stdout_path", "stderr_path", "note"):
        v = value.get(key)
        if v is not None and not _text(v, 512): return False
    for key in ("stdout_sha256", "stderr_sha256", "design_sha256", "plan_sha256", "dispatch_sha256", "repair_context_sha256"):
        v = value.get(key)
        if v is not None and not (isinstance(v, str) and bool(re.fullmatch(r"[0-9a-f]{64}", v))): return False
    identity = value.get("process_identity")
    if identity is not None and not (isinstance(identity, Mapping) and set(identity) == {"args_suffix", "start"} and _text(identity.get("args_suffix"), 4096) and _text(identity.get("start"), 160)): return False
    exit_code = value.get("exit_code")
    return exit_code is None or isinstance(exit_code, int)

def validate_review(value: object) -> bool:
    if not isinstance(value, Mapping) or set(value) != {"reviewed_sha", "decision", "findings", "dispositions"} or not full_sha(value.get("reviewed_sha")) or value.get("decision") not in {"approved", "changes_requested"} or not isinstance(value.get("findings"), list) or not isinstance(value.get("dispositions"), list) or len(value["findings"]) > 50 or len(value["dispositions"]) > 50: return False
    ids = set(); description_chars = 0
    for finding in value["findings"]:
        if not isinstance(finding, Mapping) or set(finding) != {"id", "severity", "description"} or not _text(finding.get("id"), 80) or finding["id"] in ids or finding.get("severity") not in {"blocker", "major", "minor"} or not _text(finding.get("description")): return False
        ids.add(finding["id"]); description_chars += len(finding["description"])
    return description_chars <= 32768 and all(isinstance(d, Mapping) and set(d) == {"finding_id", "disposition"} and d.get("finding_id") in ids and d.get("disposition") in {"accepted", "rejected", "fixed"} for d in value["dispositions"])

def validate_record(record: Mapping[str, Any]) -> str | None:
    kind = record.get("kind")
    required = {"run": {"schema_version","kind","id","revision","created_at","updated_at","package_id","base_sha","head_sha","branch","repo_root","worktree_path","status","scope","attempt","attempt_history","kanban_board","kanban_task_ids","stage_profiles","stage_statuses","setup","goal","dispatches"}, "evidence": {"schema_version","kind","id","created_at","run_id","type","actor","commit_sha","command","exit_code","artifact_path","artifact_sha256","previous_evidence_hash","evidence_hash"}, "review": {"schema_version","kind","id","created_at","run_id","reviewer","reviewed_sha","decision","findings","dispositions"}, "verification": {"schema_version","kind","id","created_at","run_id","candidate_sha","evidence_ids","status"}, "handoff": {"schema_version","kind","id","created_at","run_id","candidate_sha","action"}, "worker": WORKER_FIELDS}
    if kind not in required: return "malformed_schema"
    if kind == "worker": return None if validate_worker(record) else "malformed_schema"
    allowed_extra = {"attempt_base_sha"} if kind == "run" else set()
    if (set(record) - allowed_extra) != required[kind] or record.get("schema_version") != SCHEMA_VERSION: return "malformed_schema"
    if kind == "run":
        statuses=record.get("stage_statuses")
        cur_attempt = record.get("attempt", 0)
        history = record.get("attempt_history", [])
        good = valid_run_id(record.get("id")) and isinstance(record.get("revision"), int) and record["revision"] >= 0 and _text(record.get("package_id"), 120) and _text(record.get("goal")) and full_sha(record.get("base_sha")) and full_sha(record.get("head_sha")) and isinstance(record.get("scope"), list) and bool(record["scope"]) and isinstance(cur_attempt, int) and cur_attempt >= 1 and isinstance(history, list) and all(_valid_attempt_history_item(x) for x in history) and isinstance(record.get("kanban_task_ids"), Mapping) and set(record["kanban_task_ids"]) == set(STAGES) and all(_text(v,160) for v in record["kanban_task_ids"].values()) and record.get("stage_profiles") == PROFILES and isinstance(record.get("dispatches"),Mapping) and set(record["dispatches"]) == set(STAGES) and all(_dispatch(stage, value) for stage, value in record["dispatches"].items()) and isinstance(statuses,Mapping) and set(statuses)==set(STAGES) and all(value in {"pending","active","completed","blocked"} for value in statuses.values()) and record.get("status") in {"awaiting_design","awaiting_plan","awaiting_red","awaiting_green","awaiting_spec_review","awaiting_quality_review","awaiting_verify","awaiting_live","verified","completed","repairing","blocked_setup"} and ("attempt_base_sha" not in record or full_sha(record["attempt_base_sha"]))
        if not good: return "malformed_schema"
        # Enforce sequential unique attempt history: exactly attempt-1 entries, attempts 1..attempt-1
        if len(history) != cur_attempt - 1: return "malformed_schema"
        if history and [item.get("attempt") for item in history] != list(range(1, cur_attempt)): return "malformed_schema"
        # Chain rule for attempt_base_sha (when populated; absent = legacy, skip)
        for i, entry in enumerate(history):
            if "attempt_base_sha" not in entry: continue
            expected_sha = record["base_sha"] if i == 0 else history[i - 1].get("next_attempt_base_sha",history[i - 1].get("head_sha"))
            if entry["attempt_base_sha"] != expected_sha: return "malformed_schema"
        if "attempt_base_sha" in record:
            if cur_attempt == 1:
                if record["attempt_base_sha"] != record["base_sha"]: return "malformed_schema"
            elif history:
                if record["attempt_base_sha"] != history[-1].get("next_attempt_base_sha",history[-1].get("head_sha")): return "malformed_schema"
        return None
    if kind == "evidence": return None if valid_run_id(record.get("run_id")) and record.get("type") in {"red","green","full","security","live"} and _actor(record.get("actor")) and full_sha(record.get("commit_sha")) and _argv(record.get("command")) and isinstance(record.get("exit_code"), int) and _text(record.get("artifact_path"),512) and isinstance(record.get("artifact_sha256"),str) and bool(re.fullmatch(r"[0-9a-f]{64}",record["artifact_sha256"])) else "malformed_schema"
    if kind == "review": return None if valid_run_id(record.get("run_id")) and _actor(record.get("reviewer")) and validate_review({k: record[k] for k in ("reviewed_sha","decision","findings","dispositions")}) else "malformed_schema"
    if kind == "verification": return None if valid_run_id(record.get("run_id")) and full_sha(record.get("candidate_sha")) and record.get("status") in {"passed","deterministic_passed"} and isinstance(record.get("evidence_ids"),list) else "malformed_schema"
    if kind == "worker": return None if validate_worker(record) else "malformed_schema"
    return None if valid_run_id(record.get("run_id")) and full_sha(record.get("candidate_sha")) and record.get("action") == "draft_pr_manual_merge" else "malformed_schema"
