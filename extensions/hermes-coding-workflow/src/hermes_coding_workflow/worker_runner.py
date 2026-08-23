"""Detached entry point that actually invokes the Claude Code CLI.

`WorkflowService.dispatch_worker` spawns this module (`python -m
hermes_coding_workflow.worker_runner <repo> <run_id> <stage> <attempt>
<worker_attempt>`) as a new-session, fully-detached process and returns
immediately. This process is the one that blocks on the real `claude`
subprocess and atomically records the terminal state/result metadata --
the parent CLI invocation never waits on it.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

from .claude_worker import actor_env, build_argv, build_prompt, resolve_claude_executable, scrub_env
from .safety import atomic_write_text, redact, validate_controlled_worktree
from .service import _authoritative_intent, _valid_repair_context, full_sha_hash, now
from .store import RunStore


def _fail(store: RunStore, stage: str, attempt: int, worker_attempt: int, record: dict, note: str) -> int:
    with store.locked():
        latest = store.read_worker(stage, attempt, worker_attempt)
        if latest is None:
            return 1
        updated = dict(latest)
        updated.update(state="failed", note=note[:512], updated_at=now())
        store.write_worker(stage, attempt, worker_attempt, updated)
    return 1


def main(argv: list[str]) -> int:
    repo = Path(argv[1]).resolve()
    run_id, stage = argv[2], argv[3]
    attempt, worker_attempt = int(argv[4]), int(argv[5])
    store = RunStore(repo, run_id)

    # Plan/design/identity are read here, under the same lock as the
    # queued->running ownership check, and their hashes are compared against
    # the ones `dispatch_worker` pinned into the record at dispatch time.
    # Reading them again later, unlocked, would leave a TOCTOU window where
    # an on-disk mutation between the check and the second read would go
    # undetected; `plan`/`design` below are exactly what was verified here.
    with store.locked():
        run = store.read()
        record = store.read_worker(stage, attempt, worker_attempt)
        if record is None or record["state"] != "queued" or record["pid"] != os.getpid():
            return 1
        # `dispatch_worker` released the run lock once this worker was
        # queued. Another authorized lifecycle call (a stage `check`, a
        # `repair`, a stale-worker reclaim) can acquire it first and move the
        # run on -- advance the stage, bump the attempt, or replace the
        # task/profile/brief graph -- before this detached process ever gets
        # here. The record's own internally-consistent `dispatch_sha256`
        # (checked below) only proves the record was not tampered with in
        # isolation; it proves nothing about whether the *authoritative*
        # run/internal state it was queued against still holds. Re-deriving
        # that binding from a fresh read, still under this same lock, is
        # what actually closes the window.
        internal = store.read("internal.json") if store._path("internal.json").exists() else {}
        retry_authorization = (internal.get("worker_retry_authorizations") or {}).get(stage)
        gate_failure_context = retry_authorization if isinstance(retry_authorization, dict) and retry_authorization.get("attempt") == attempt and retry_authorization.get("retry_worker_attempt") == worker_attempt else None
        intent = _authoritative_intent(internal, attempt)
        dispatch = run.get("dispatches", {}).get(stage, {})
        if (
            run.get("attempt") != attempt
            or run.get("stage_statuses", {}).get(stage) != "active"
            or run.get("stage_profiles", {}).get(stage) != record["profile"]
            or run.get("kanban_task_ids", {}).get(stage) != record["task_id"]
            or dispatch.get("task_id") != record["task_id"]
            or dispatch.get("profile") != record["profile"]
            or dispatch.get("attempt") != attempt
            or dispatch.get("brief_hash") != record["brief_hash"]
            or intent.get("task_ids", {}).get(stage) != record["task_id"]
            or intent.get("brief_hashes", {}).get(stage) != record["brief_hash"]
        ):
            updated = dict(record)
            updated.update(state="failed", note="launch_identity_mismatch", updated_at=now())
            store.write_worker(stage, attempt, worker_attempt, updated)
            return 1
        plan_record = store.read("plan.json")
        design_record = store.read("approved-design.json")
        repair_context = store.read("repair-context.json") if store._path("repair-context.json").exists() else None
        dispatch_sha256 = full_sha_hash({
            "run_id": run_id, "stage": stage, "task_id": record["task_id"], "profile": record["profile"],
            "attempt": attempt, "brief_hash": record["brief_hash"],
        })
        if (
            full_sha_hash(design_record) != record.get("design_sha256")
            or full_sha_hash(plan_record) != record.get("plan_sha256")
            or dispatch_sha256 != record.get("dispatch_sha256")
            or (record.get("repair_context_sha256") is None and repair_context is not None)
            or (record.get("repair_context_sha256") is not None and record.get("repair_context_sha256") != full_sha_hash(repair_context))
            or not _valid_repair_context(repair_context, run, internal)
        ):
            updated = dict(record)
            updated.update(state="failed", note="artifact_mutated", updated_at=now())
            store.write_worker(stage, attempt, worker_attempt, updated)
            return 1
        plan, design = plan_record["content"], design_record["content"]
        record = dict(record)
        record.update(state="running", updated_at=now())
        store.write_worker(stage, attempt, worker_attempt, record)

    try:
        worktree = validate_controlled_worktree(repo, record["worktree_path"], run_id=run_id, attempt=attempt, expected_branch=run["branch"])
    except ValueError as exc:
        return _fail(store, stage, attempt, worker_attempt, record, str(exc))

    try:
        prompt = build_prompt(
            run=run, plan=plan, design=design, stage=stage, profile=record["profile"],
            task_id=record["task_id"], brief_hash=record["brief_hash"], worktree_path=str(worktree),
            repair_context=repair_context,
            gate_failure_context=gate_failure_context,
        )
        executable = resolve_claude_executable()
        cmd = build_argv(executable, stage, plan)
        env = scrub_env(
            os.environ,
            actor_env(profile=record["profile"], task_id=record["task_id"], session_id=run_id, model=record["model"]),
        )
        result = subprocess.run(cmd, cwd=str(worktree), env=env, input=prompt, text=True, capture_output=True, timeout=1800)
    except Exception as exc:  # noqa: BLE001 - any launch failure must still terminate the durable record
        return _fail(store, stage, attempt, worker_attempt, record, f"launch_failed:{exc}"[:512])

    artifacts = store.root / "artifacts"
    if artifacts.exists() and artifacts.is_symlink():
        return _fail(store, stage, attempt, worker_attempt, record, "path_scope_violation")
    artifacts.mkdir(exist_ok=True)
    stdout_text = redact(result.stdout or "")
    stderr_text = redact(result.stderr or "")
    stdout_file = artifacts / f"worker-{stage}-{attempt}-{worker_attempt}-stdout.log"
    stderr_file = artifacts / f"worker-{stage}-{attempt}-{worker_attempt}-stderr.log"
    try:
        atomic_write_text(stdout_file, stdout_text)
        atomic_write_text(stderr_file, stderr_text)
    except ValueError as exc:
        return _fail(store, stage, attempt, worker_attempt, record, str(exc))

    with store.locked():
        final = dict(record)
        final.update(
            state="succeeded" if result.returncode == 0 else "failed",
            exit_code=result.returncode,
            stdout_path=str(stdout_file.relative_to(repo)),
            stderr_path=str(stderr_file.relative_to(repo)),
            stdout_sha256=hashlib.sha256(stdout_text.encode()).hexdigest(),
            stderr_sha256=hashlib.sha256(stderr_text.encode()).hexdigest(),
            updated_at=now(),
        )
        store.write_worker(stage, attempt, worker_attempt, final)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
