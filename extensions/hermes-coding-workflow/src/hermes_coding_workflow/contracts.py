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

def full_sha(value: object) -> bool: return isinstance(value, str) and bool(SHA.fullmatch(value))
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

def validate_review(value: object) -> bool:
    if not isinstance(value, Mapping) or set(value) != {"reviewed_sha", "decision", "findings", "dispositions"} or not full_sha(value.get("reviewed_sha")) or value.get("decision") not in {"approved", "changes_requested"} or not isinstance(value.get("findings"), list) or not isinstance(value.get("dispositions"), list): return False
    ids = set()
    for finding in value["findings"]:
        if not isinstance(finding, Mapping) or set(finding) != {"id", "severity", "description"} or not _text(finding.get("id"), 80) or finding["id"] in ids or finding.get("severity") not in {"blocker", "major", "minor"} or not _text(finding.get("description")): return False
        ids.add(finding["id"])
    return all(isinstance(d, Mapping) and set(d) == {"finding_id", "disposition"} and d.get("finding_id") in ids and d.get("disposition") in {"accepted", "rejected", "fixed"} for d in value["dispositions"])

def validate_record(record: Mapping[str, Any]) -> str | None:
    kind = record.get("kind")
    required = {"run": {"schema_version","kind","id","revision","created_at","updated_at","package_id","base_sha","head_sha","branch","repo_root","worktree_path","status","scope","attempt","attempt_history","kanban_board","kanban_task_ids","stage_profiles","stage_statuses","setup","goal","dispatches"}, "evidence": {"schema_version","kind","id","created_at","run_id","type","actor","commit_sha","command","exit_code","artifact_path","artifact_sha256","previous_evidence_hash","evidence_hash"}, "review": {"schema_version","kind","id","created_at","run_id","reviewer","reviewed_sha","decision","findings","dispositions"}, "verification": {"schema_version","kind","id","created_at","run_id","candidate_sha","evidence_ids","status"}, "handoff": {"schema_version","kind","id","created_at","run_id","candidate_sha","action"}}
    if kind not in required or set(record) != required[kind] or record.get("schema_version") != SCHEMA_VERSION: return "malformed_schema"
    if kind == "run":
        statuses=record.get("stage_statuses")
        good = valid_run_id(record.get("id")) and isinstance(record.get("revision"), int) and record["revision"] >= 0 and _text(record.get("package_id"), 120) and _text(record.get("goal")) and full_sha(record.get("base_sha")) and full_sha(record.get("head_sha")) and isinstance(record.get("scope"), list) and bool(record["scope"]) and isinstance(record.get("attempt"), int) and record["attempt"] >= 1 and isinstance(record.get("attempt_history"), list) and isinstance(record.get("kanban_task_ids"), Mapping) and set(record["kanban_task_ids"]) == set(STAGES) and all(_text(v,160) for v in record["kanban_task_ids"].values()) and record.get("stage_profiles") == PROFILES and isinstance(record.get("dispatches"),Mapping) and set(record["dispatches"]) == set(STAGES) and all(_dispatch(stage, value) for stage, value in record["dispatches"].items()) and isinstance(statuses,Mapping) and set(statuses)==set(STAGES) and all(value in {"pending","active","completed","blocked"} for value in statuses.values()) and record.get("status") in {"awaiting_design","awaiting_plan","awaiting_red","awaiting_green","awaiting_spec_review","awaiting_quality_review","awaiting_verify","awaiting_live","verified","completed","repairing","blocked_setup"}
        return None if good else "malformed_schema"
    if kind == "evidence": return None if valid_run_id(record.get("run_id")) and record.get("type") in {"red","green","full","security","live"} and _actor(record.get("actor")) and full_sha(record.get("commit_sha")) and _argv(record.get("command")) and isinstance(record.get("exit_code"), int) and _text(record.get("artifact_path"),512) and isinstance(record.get("artifact_sha256"),str) and bool(re.fullmatch(r"[0-9a-f]{64}",record["artifact_sha256"])) else "malformed_schema"
    if kind == "review": return None if valid_run_id(record.get("run_id")) and _actor(record.get("reviewer")) and validate_review({k: record[k] for k in ("reviewed_sha","decision","findings","dispositions")}) else "malformed_schema"
    if kind == "verification": return None if valid_run_id(record.get("run_id")) and full_sha(record.get("candidate_sha")) and record.get("status") in {"passed","deterministic_passed"} and isinstance(record.get("evidence_ids"),list) else "malformed_schema"
    return None if valid_run_id(record.get("run_id")) and full_sha(record.get("candidate_sha")) and record.get("action") == "draft_pr_manual_merge" else "malformed_schema"
