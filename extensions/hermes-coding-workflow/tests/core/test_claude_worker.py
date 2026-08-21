from __future__ import annotations

import pytest

from hermes_coding_workflow import claude_worker
from hermes_coding_workflow.contracts import CLAUDE_BACKEND, CLAUDE_STAGES, CLAUDE_TIER_MODELS


def test_tier_map_matches_the_deterministic_backend_contract() -> None:
    assert set(CLAUDE_STAGES) == {"red", "green", "quality-review", "complete"}
    assert CLAUDE_TIER_MODELS["red"] == CLAUDE_TIER_MODELS["green"] == "claude-sonnet-4-6"
    assert CLAUDE_TIER_MODELS["quality-review"] == "claude-opus-4-6"
    assert CLAUDE_TIER_MODELS["complete"] == "claude-haiku-4-5"
    assert CLAUDE_BACKEND == "claude-code-cli"


def test_resolve_claude_executable_prefers_injected_override(monkeypatch) -> None:
    monkeypatch.setenv(claude_worker.CLAUDE_CLI_ENV, "/tmp/fake-claude")
    assert claude_worker.resolve_claude_executable() == "/tmp/fake-claude"


def test_resolve_claude_executable_fails_closed_without_path_or_override(monkeypatch) -> None:
    monkeypatch.delenv(claude_worker.CLAUDE_CLI_ENV, raising=False)
    monkeypatch.setattr(claude_worker.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="claude_cli_not_found"):
        claude_worker.resolve_claude_executable()


def test_scrub_env_removes_every_anthropic_api_key_path_and_injects_actor_identity() -> None:
    base = {"PATH": "/usr/bin", "ANTHROPIC_API_KEY": "sk-secret", "ANTHROPIC_AUTH_TOKEN": "tok-secret", "HOME": "/home/x"}
    actor = claude_worker.actor_env(profile="dev-contract", task_id="task-red", session_id="run-1", model="claude-sonnet-4-6")
    env = claude_worker.scrub_env(base, actor)
    assert "ANTHROPIC_API_KEY" not in env and "ANTHROPIC_AUTH_TOKEN" not in env
    assert env["PATH"] == "/usr/bin" and env["HOME"] == "/home/x"
    assert env["HERMES_PROFILE"] == "dev-contract"
    assert env["HERMES_KANBAN_TASK"] == "task-red"
    assert env["HERMES_SESSION_ID"] == "run-1"
    assert env["HERMES_MODEL"] == "claude-sonnet-4-6"
    assert env["HERMES_PROVIDER"] == "claude-code-cli"


def test_scrub_env_is_operational_allowlist_and_removes_unrelated_credentials_and_backends() -> None:
    base = {
        "HOME": "/home/x", "PATH": "/usr/bin", "TMPDIR": "/tmp/x", "LANG": "en_US.UTF-8", "LC_ALL": "C",
        "GITHUB_TOKEN": "gh-secret", "OPENAI_API_KEY": "openai-secret", "AWS_SECRET_ACCESS_KEY": "aws-secret",
        "RANDOM_SERVICE_TOKEN": "random-secret", "DATABASE_PASSWORD": "db-secret", "PRIVATE_CREDENTIAL": "credential-secret",
        "CLAUDE_CODE_USE_BEDROCK": "1", "CLAUDE_CODE_USE_VERTEX": "1", "CLAUDE_CODE_USE_FOUNDRY": "1",
        "SSH_AUTH_SOCK": "/tmp/agent.sock", "UNRELATED_SETTING": "must-not-survive",
        "HCW_CLAUDE_CLI": "/tmp/fake-claude", "FAKE_CLAUDE_MARKER": "/tmp/marker", "FAKE_CLAUDE_EXIT": "3",
    }
    actor = claude_worker.actor_env(profile="dev-builder", task_id="task-green", session_id="run-1", model="claude-sonnet-4-6")
    env = claude_worker.scrub_env(base, actor)
    assert env["HOME"] == "/home/x" and env["PATH"] == "/usr/bin" and env["LC_ALL"] == "C"
    assert env["HCW_CLAUDE_CLI"] == "/tmp/fake-claude"
    assert env["FAKE_CLAUDE_MARKER"] == "/tmp/marker" and env["FAKE_CLAUDE_EXIT"] == "3"
    assert env["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"]
    forbidden = {
        "GITHUB_TOKEN", "OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY", "RANDOM_SERVICE_TOKEN", "DATABASE_PASSWORD",
        "PRIVATE_CREDENTIAL", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY",
        "SSH_AUTH_SOCK", "UNRELATED_SETTING",
    }
    assert forbidden.isdisjoint(env)


@pytest.mark.parametrize("stage", ["red", "green", "quality-review", "complete"])
def test_build_argv_is_safe_mode_no_bare_no_session_persistence_with_explicit_model(stage: str) -> None:
    argv = claude_worker.build_argv("/usr/local/bin/claude", stage)
    assert argv[0] == "/usr/local/bin/claude"
    assert "--bare" not in argv
    assert "--safe-mode" in argv
    assert "--no-session-persistence" in argv
    assert "--model" in argv and argv[argv.index("--model") + 1] == CLAUDE_TIER_MODELS[stage]
    assert "--max-turns" in argv and argv[argv.index("--max-turns") + 1].isdigit()
    assert "--output-format" in argv and argv[argv.index("--output-format") + 1] == "json"
    assert "--allowedTools" in argv
    assert all(isinstance(part, str) for part in argv)


def test_red_worker_has_the_full_implementation_turn_budget():
    argv = claude_worker.build_argv("/usr/local/bin/claude", "red")
    assert argv[argv.index("--max-turns") + 1] == "30"


def test_build_argv_rejects_stages_outside_the_claude_tier_map() -> None:
    with pytest.raises(ValueError, match="unsupported_claude_stage"):
        claude_worker.build_argv("/usr/local/bin/claude", "verify")


def test_build_prompt_is_built_from_durable_artifacts_only_and_identifies_the_task() -> None:
    run = {"id": "run-1", "attempt": 1, "goal": "add a widget", "scope": ["src/*.py"], "branch": "hcw/run-1/attempt-1", "repo_root": "/repo"}
    plan = {"tasks": [{"id": "t1", "description": "add widget", "paths": ["src/widget.py"], "test_command": ["python", "-m", "pytest"], "requirement_ids": ["R1"]}], "commands": {"red": {"argv": ["python", "-m", "pytest"], "requirement_ids": ["R1"]}, "green": {"argv": ["python", "-m", "pytest"], "requirement_ids": ["R1"]}}}
    design = {"observable_outcome": "widget appears"}
    prompt = claude_worker.build_prompt(run=run, plan=plan, design=design, stage="red", profile="dev-contract", task_id="task-red", brief_hash="a" * 64, worktree_path="/repo/.worktrees/hcw-run-1-1")
    assert "add a widget" in prompt
    assert "widget appears" in prompt
    assert "src/widget.py" in prompt
    assert "TDD" in prompt
    assert "profile=dev-contract" in prompt
    assert "task_id=task-red" in prompt
    assert "a" * 64 in prompt


def test_build_prompt_contains_no_launcher_placeholder_or_self_transition_claim() -> None:
    run = {"id": "run-1", "attempt": 1, "goal": "add a widget", "scope": ["src/*.py"], "branch": "hcw/run-1/attempt-1", "repo_root": "/repo"}
    plan = {"tasks": [{"id": "t1", "description": "add widget", "paths": ["src/widget.py"], "test_command": ["python", "-m", "pytest"], "requirement_ids": ["R1"]}], "commands": {"red": {"argv": ["python", "-m", "pytest"], "requirement_ids": ["R1"]}, "green": {"argv": ["python", "-m", "pytest"], "requirement_ids": ["R1"]}}}
    design = {"observable_outcome": "widget appears"}
    prompt = claude_worker.build_prompt(run=run, plan=plan, design=design, stage="red", profile="dev-contract", task_id="task-red", brief_hash="a" * 64, worktree_path="/repo/.worktrees/hcw-run-1-1")
    assert "<installed-hcw-launcher>" not in prompt
    assert "launcher" not in prompt.lower()
    assert "invoke" not in prompt.lower()
    assert "hcw " not in prompt


def test_build_prompt_states_the_controller_performs_transitions_and_success_does_not_advance_state() -> None:
    run = {"id": "run-1", "attempt": 1, "goal": "add a widget", "scope": ["src/*.py"], "branch": "hcw/run-1/attempt-1", "repo_root": "/repo"}
    plan = {"tasks": [{"id": "t1", "description": "add widget", "paths": ["src/widget.py"], "test_command": ["python", "-m", "pytest"], "requirement_ids": ["R1"]}], "commands": {"red": {"argv": ["python", "-m", "pytest"], "requirement_ids": ["R1"]}, "green": {"argv": ["python", "-m", "pytest"], "requirement_ids": ["R1"]}}}
    design = {"observable_outcome": "widget appears"}
    prompt = claude_worker.build_prompt(run=run, plan=plan, design=design, stage="red", profile="dev-contract", task_id="task-red", brief_hash="a" * 64, worktree_path="/repo/.worktrees/hcw-run-1-1")
    assert "does not advance" in prompt.lower()
    assert "orchestrator" in prompt.lower()


@pytest.mark.parametrize("stage,expected", [
    ("red", ["Read", "Write", "Edit", "Grep", "Glob", "Bash"]),
    ("green", ["Read", "Write", "Edit", "Grep", "Glob", "Bash"]),
    ("quality-review", ["Read", "Grep", "Glob"]),
    ("complete", ["Read"]),
])
def test_build_argv_tools_flag_restricts_available_tools_per_stage(stage: str, expected: list[str]) -> None:
    argv = claude_worker.build_argv("/usr/local/bin/claude", stage)
    assert "--tools" in argv
    assert argv[argv.index("--tools") + 1:argv.index("--allowedTools")] == expected


def test_build_argv_never_uses_unrestricted_bash_for_quality_review_or_complete() -> None:
    for stage in ("quality-review", "complete"):
        argv = claude_worker.build_argv("/usr/local/bin/claude", stage)
        assert "Bash" not in argv[argv.index("--tools") + 1:argv.index("--allowedTools")]


@pytest.mark.parametrize("argv,expected_pattern", [
    (["npm", "test"], "Bash(npm test)"),
    (["cargo", "test", "--release"], "Bash(cargo test --release)"),
    (["uv", "run", "pytest"], "Bash(uv run pytest)"),
    (["/usr/bin/python3.11", "-m", "pytest", "tests/"], "Bash(/usr/bin/python3.11 -m pytest tests/)"),
])
def test_declared_command_patterns_derive_the_exact_argv_for_npm_cargo_uv_and_absolute_python(argv: list[str], expected_pattern: str) -> None:
    plan = {"commands": {"red": {"argv": argv, "requirement_ids": ["R1"]}}}
    patterns = claude_worker.declared_command_patterns("red", plan)
    assert patterns == [expected_pattern]


def test_declared_command_patterns_never_permit_an_unrelated_command() -> None:
    plan = {"commands": {"red": {"argv": ["npm", "test"], "requirement_ids": ["R1"]}}}
    patterns = claude_worker.declared_command_patterns("red", plan)
    assert not any(pattern.startswith("Bash(/bin/echo") for pattern in patterns)
    assert not any("/bin/echo" in pattern for pattern in patterns)


def test_build_argv_passes_separate_exact_matchers_and_shell_quotes_spaces_and_commas() -> None:
    plan = {"commands": {"red": {"argv": ["python", "-m", "pytest", "-k", "foo, bar"], "requirement_ids": ["R1"]}}}
    argv = claude_worker.build_argv("/usr/local/bin/claude", "red", plan)
    allowed_index = argv.index("--allowedTools")
    safe_index = argv.index("--safe-mode")
    matchers = argv[allowed_index + 1:safe_index]
    assert "Bash(python -m pytest -k 'foo, bar')" in matchers
    assert "Bash(git status)" in matchers and "Bash(git diff)" in matchers
    assert all(",Read" not in matcher and ",Bash" not in matcher for matcher in matchers)


def test_build_allowed_tools_for_red_green_includes_only_the_declared_command_and_narrow_git_reads() -> None:
    plan = {"commands": {"red": {"argv": ["npm", "test"], "requirement_ids": ["R1"]}, "green": {"argv": ["npm", "test"], "requirement_ids": ["R1"]}}}
    allowed = claude_worker.build_allowed_tools("red", plan)
    parts = allowed
    assert "Bash(npm test)" in parts
    assert "Bash(git status)" in parts
    assert "Bash(git diff)" in parts
    assert not any(part.startswith("Bash(") and part not in {"Bash(npm test)", "Bash(git status)", "Bash(git diff)"} for part in parts)


def test_build_allowed_tools_for_quality_review_and_complete_never_include_bash() -> None:
    assert "Bash" not in claude_worker.build_allowed_tools("quality-review", {})
    assert claude_worker.build_allowed_tools("complete", {}) == ["Read"]


def test_live_matcher_proof_command_documents_a_real_claude_cli_invocation() -> None:
    plan = {"commands": {"red": {"argv": ["npm", "test"], "requirement_ids": ["R1"]}}}
    argv = claude_worker.live_matcher_proof_command("/usr/local/bin/claude", "red", plan)
    assert argv[0] == "/usr/local/bin/claude"
    assert "--allowedTools" in argv
    assert "Bash(npm test)" in argv[argv.index("--allowedTools") + 1:argv.index("--safe-mode")]
    assert claude_worker.live_matcher_proof_command.__doc__
