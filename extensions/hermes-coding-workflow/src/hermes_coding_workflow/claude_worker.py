"""Command/env/prompt construction for external Claude Code CLI workers.

Claude Code runs as an ordinary detached subprocess in the run's controlled
worktree. Its internal tool calls never pass through Hermes `pre_tool_call`
hooks -- that boundary only exists for Hermes's own agent loop. Safety here
comes from: worktree isolation, exact stage/task/brief identity checked
before dispatch (see `service.WorkflowService.dispatch_worker`), a scrubbed
credential-free environment, least-privilege `--allowedTools`, and the
durable review/verification gates the orchestrator still enforces after the
worker exits.
"""
from __future__ import annotations

import os
import shlex
import shutil
from typing import Mapping

from .contracts import CLAUDE_BACKEND, CLAUDE_STAGES, CLAUDE_TIER_MODELS

CLAUDE_CLI_ENV = "HCW_CLAUDE_CLI"
OPERATIONAL_ENV_KEYS = frozenset({
    "HOME", "PATH", "TMPDIR", "TMP", "TEMP", "LANG", "SHELL", "USER", "LOGNAME", "TERM", "COLORTERM",
    "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS",
})
TEST_ENV_KEYS = frozenset({CLAUDE_CLI_ENV, "FAKE_CLAUDE_MARKER", "FAKE_CLAUDE_EXIT"})
SUBPROCESS_SCRUB_KEYS = (
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "GITHUB_TOKEN",
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
)

# `--tools` (Claude Code CLI 2.1.234) restricts which tool categories are even
# loaded for the run -- quality-review/complete never get a Bash tool at all,
# so no `--allowedTools` matcher construction mistake there could grant shell
# access. red/green need a real Bash tool because their declared stage
# command (from the durable plan) has to actually run.
TOOLS = {
    "red": ("Read", "Write", "Edit", "Grep", "Glob", "Bash"),
    "green": ("Read", "Write", "Edit", "Grep", "Glob", "Bash"),
    "quality-review": ("Read", "Grep", "Glob"),
    "complete": ("Read",),
}
# Narrow, read-only git operations red/green may need to orient themselves.
# Never a wildcard: no `Bash(git:*)`, which would also auto-allow `git push`,
# `git commit`, `git reset --hard`, etc.
NARROW_GIT_READS = ("Bash(git status)", "Bash(git diff)")
MAX_TURNS = {"red": 30, "green": 30, "quality-review": 20, "complete": 8}


def resolve_claude_executable() -> str:
    """Locate the `claude` CLI, allowing tests to inject a fake one.

    `HCW_CLAUDE_CLI` lets doctor/install/dispatch tests point at a disposable
    fake executable instead of depending on a real Claude Team/account login.
    """
    override = os.environ.get(CLAUDE_CLI_ENV)
    if override:
        return override
    found = shutil.which("claude")
    if not found:
        raise RuntimeError("claude_cli_not_found")
    return found


def actor_env(*, profile: str, task_id: str, session_id: str, model: str) -> dict[str, str]:
    return {
        "HERMES_PROFILE": profile,
        "HERMES_KANBAN_TASK": task_id,
        "HERMES_SESSION_ID": session_id,
        "HERMES_MODEL": model,
        "HERMES_PROVIDER": CLAUDE_BACKEND,
    }


def scrub_env(base_env: Mapping[str, str], actor: Mapping[str, str]) -> dict[str, str]:
    """Build a credential-minimal environment for the external Claude process.

    Account authentication uses the user's HOME/keychain state. Local declared
    build commands need PATH plus basic locale/temp/certificate paths. Nothing
    else from the Hermes control-plane environment is inherited. Disposable
    tests may pass their explicit fake controls only when HCW_CLAUDE_CLI is set.
    """
    env = {
        key: value for key, value in base_env.items()
        if key in OPERATIONAL_ENV_KEYS or key.startswith("LC_")
    }
    if base_env.get(CLAUDE_CLI_ENV):
        env.update({key: base_env[key] for key in TEST_ENV_KEYS if key in base_env})
    env["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"] = ",".join(SUBPROCESS_SCRUB_KEYS)
    env.update(actor)
    return env


STAGE_COMMAND_KINDS = {"red": ("red",), "green": ("green",), "quality-review": (), "complete": ()}


def declared_command_patterns(stage: str, plan: Mapping[str, object]) -> list[str]:
    """Derive the exact, literal `Bash(...)` matcher pattern(s) for `stage`'s
    declared command(s) from the durable plan's argv -- never a wildcard, and
    never anything the plan did not literally declare (an unrelated command
    such as `/bin/echo` can never appear here by construction).
    """
    commands = plan.get("commands", {}) if plan else {}
    patterns = []
    for kind in STAGE_COMMAND_KINDS.get(stage, ()):
        command = commands.get(kind) if isinstance(commands, Mapping) else None
        argv = command.get("argv") if isinstance(command, Mapping) else None
        if argv:
            patterns.append("Bash(" + shlex.join(argv) + ")")
    return patterns


def build_allowed_tools(stage: str, plan: Mapping[str, object]) -> list[str]:
    """Build the exact `--allowedTools` matcher string for `stage` from the
    durable plan's declared argv, plus only the narrowly needed git reads.
    Quality-review and complete never mention Bash at all -- their `--tools`
    value (see `TOOLS`) does not even load a Bash tool for the matcher to
    apply to.
    """
    if stage in ("red", "green"):
        parts = ["Read", "Write", "Edit", "Grep", "Glob", *declared_command_patterns(stage, plan), *NARROW_GIT_READS]
        return parts
    if stage == "quality-review":
        return ["Read", "Grep", "Glob"]
    return ["Read"]


def build_argv(executable: str, stage: str, plan: Mapping[str, object] | None = None) -> list[str]:
    if stage not in CLAUDE_STAGES:
        raise ValueError("unsupported_claude_stage")
    return [
        executable,
        "-p",
        "--output-format", "json",
        "--model", CLAUDE_TIER_MODELS[stage],
        "--max-turns", str(MAX_TURNS[stage]),
        "--tools", *TOOLS[stage],
        "--allowedTools", *build_allowed_tools(stage, plan or {}),
        "--safe-mode",
        "--no-session-persistence",
    ]


def live_matcher_proof_command(executable: str, stage: str, plan: Mapping[str, object]) -> list[str]:
    """Return the exact `claude` invocation a human (or a live, non-CI proof
    job) should run interactively against a real, installed Claude Code CLI
    to confirm its `--tools`/`--allowedTools` matcher semantics accept the
    declared command and reject everything else. Unit tests cannot invoke
    the real CLI's permission engine; this hook documents the exact argv that
    proves it, so the proof stays reproducible and out of unit-test scope.
    """
    return build_argv(executable, stage, plan)
STAGE_INSTRUCTIONS = {
    "red": "Follow strict TDD: write only the failing acceptance test(s) implied by the task below. "
           "Do not implement the behavior yet. The declared red command must fail for the right reason "
           "before you stop.",
    "green": "Follow strict TDD: implement the minimal change so the previously-recorded red command "
             "passes. Touch only paths inside scope.",
    "quality-review": "Read-only review: correctness, simplicity, maintainability, and security only. "
                       "Make no source changes.",
    "complete": "Recording only: no implementation changes.",
}


def build_prompt(*, run: Mapping[str, object], plan: Mapping[str, object], design: Mapping[str, object],
                  stage: str, profile: str, task_id: str, brief_hash: str, worktree_path: str) -> str:
    """Build the worker's entire prompt from durable run/plan/design artifacts only.

    Deliberately takes no parent chat history: a Claude worker gets exactly
    the bounded, context-free brief a fresh worker is supposed to receive.

    Claude workers never transition HCW state themselves: they have no HCW
    launcher, subcommand, or tool available to them (see `TOOLS`/
    `build_allowed_tools`), and this prompt never instructs them to invoke
    one. The Hermes orchestrator is the only authority that reads this
    worker's durable output (files in the worktree, its exit code) and
    performs the corresponding `check`/`commit`/`review`/`complete`
    transition; the worker process exiting, even successfully, never
    advances HCW state on its own.
    """
    kinds = STAGE_COMMAND_KINDS[stage]
    commands = plan.get("commands", {})
    declared = {kind: commands[kind]["argv"] for kind in kinds if kind in commands}
    lines = [
        f"HCW worker brief for stage '{stage}' (run {run['id']}, attempt {run['attempt']}).",
        f"Goal: {run['goal']}",
        f"Scope (only these path globs may change): {run['scope']}",
        f"Branch: {run['branch']}",
        f"Worktree (this is your cwd; do not leave it): {worktree_path}",
        f"Observable outcome: {design.get('observable_outcome', '')}",
        "Tasks:",
    ]
    for task in plan.get("tasks", []):
        lines.append(f"  - {task['id']}: {task['description']} (paths={task['paths']}, test_command={task['test_command']})")
    if declared:
        lines.append(f"Declared command for this stage (must match exactly; never invent another): {declared}")
    lines.append(STAGE_INSTRUCTIONS[stage])
    lines.append(
        "Do not run or reference any HCW command or subcommand: you have no such tool available and "
        "none is provided. When your work for this stage is done, simply stop. The Hermes orchestrator "
        "alone reads your durable output and performs the authoritative HCW transition afterward; this "
        "process exiting successfully does not advance HCW state by itself."
    )
    lines.append(f"Task identity for this stage: profile={profile} task_id={task_id} brief_hash={brief_hash}")
    return "\n".join(lines)
