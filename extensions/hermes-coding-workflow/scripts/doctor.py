"""Validate complete workflow installation through real Hermes registration paths."""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

# doctor.py always ships beside the `src/` package in this checkout (it is
# never copied into an installed profile's runtime -- see
# `scripts/install.py`'s `_build_plugin`, which stages only `plugins/`,
# `skills/`, and `dashboard/`). Prepend the sibling source tree so the real
# Claude operational/scrub constants below come from one place instead of a
# hand-kept-in-sync duplicate, exactly like the installed `runtime/bin/hcw`
# launcher prepends its own sibling `runtime/site`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from hermes_coding_workflow.claude_worker import (  # noqa: E402
    CLAUDE_CLI_ENV,
    OPERATIONAL_ENV_KEYS as CLAUDE_OPERATIONAL_ENV_KEYS,
    SUBPROCESS_SCRUB_KEYS as CLAUDE_SUBPROCESS_SCRUB_KEYS,
)

PLUGINS = ("hcw", "superpowers")
DASHBOARD_PLUGIN = "hcw-dashboard"
DESCRIPTIONS = {
    "dev-planner": "Plans bounded Hermes Coding Workflow changes after approved design; produces context-free implementation plans.",
    "dev-contract": "Writes executable acceptance contracts and records observed RED evidence before implementation.",
    "dev-builder": "Implements the assigned scoped change in an isolated worktree after valid RED evidence.",
    "dev-spec-reviewer": "Independently reviews an immutable candidate for approved-spec compliance; read-only reviewer.",
    "dev-quality-reviewer": "Independently reviews an immutable candidate for correctness, simplicity, and security; read-only reviewer.",
    "dev-verifier": "Runs fresh deterministic, security, and live behavior verification and records bounded evidence.",
    "dev-recorder": "Records draft-PR/manual-merge handoff and durable project-state evidence without changing implementation.",
}
# red/green, quality-review, and complete are no longer Hermes-native Anthropic
# profiles: they are executed by an external, Hermes-dispatched Claude Code CLI
# subprocess authenticated by its own account/Team login (see
# hermes_coding_workflow.contracts.CLAUDE_TIER_MODELS). Every Hermes profile,
# including these four, stays on the OpenAI account-OAuth tier; no profile is
# ever configured with provider "anthropic".
ACCOUNT_OAUTH_TIERS = {
    "dev-planner": ("openai-codex", "gpt-5.6-sol", "codex_responses"),
    "dev-contract": ("openai-codex", "gpt-5.6-sol", "codex_responses"),
    "dev-builder": ("openai-codex", "gpt-5.6-sol", "codex_responses"),
    "dev-spec-reviewer": ("openai-codex", "gpt-5.6-sol", "codex_responses"),
    "dev-quality-reviewer": ("openai-codex", "gpt-5.6-sol", "codex_responses"),
    "dev-verifier": ("openai-codex", "gpt-5.6-terra", "codex_responses"),
    "dev-recorder": ("openai-codex", "gpt-5.6-sol", "codex_responses"),
}
SAFE_HERMES_TOOL_DISPATCH_PROVIDERS = frozenset({"openai", "gemini", "google", "openrouter", "nous"})
# The exact `claude auth status --text` "Login method:" values (lowercased)
# for a personal Claude Team/Pro/Max account-subscription login. Deliberately
# a closed set matched by equality, not by substring: unknown/organization-
# only labels such as "Unknown Team account" or a generic "Claude.ai account"
# must fail closed rather than pass because they happen to contain one of
# these words.
#
# Evidence: "claude team account" was independently confirmed by running
# `claude auth status --text` against a real, live, authenticated Team
# account, which printed exactly `Login method: Claude Team account`. No
# Pro- or Max-tier authenticated session has been available to confirm those
# two the same way; "claude pro account" / "claude max account" are contract
# values inferred from the CLI's own naming convention (the same
# "Claude <Tier> account" shape the Team entry uses), not independently
# live-verified. If the real CLI's wording for Pro/Max ever differs even in
# case or phrasing, this fails closed (readiness reports not-active) rather
# than open, per the module's fail-closed posture -- but before shipping to
# Pro/Max users, confirm these two live (or against authoritative Anthropic
# CLI documentation) and record the evidence here the same way.
CLAUDE_ACCOUNT_LOGIN_METHODS = frozenset({
    "claude team account", "claude pro account", "claude max account",
})


def _claude_probe_env(source: dict[str, str]) -> dict[str, str]:
    env = {
        key: value for key, value in source.items()
        if key in CLAUDE_OPERATIONAL_ENV_KEYS or key.startswith("LC_")
    }
    if source.get(CLAUDE_CLI_ENV):
        env[CLAUDE_CLI_ENV] = source[CLAUDE_CLI_ENV]
    env["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"] = ",".join(CLAUDE_SUBPROCESS_SCRUB_KEYS)
    return env


def _provider_boundary(home: Path) -> str:
    path = home / "config.yaml"
    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except yaml.YAMLError as exc:
        raise RuntimeError(f"provider boundary unreadable in {home}: {exc}") from exc
    model = config.get("model", {}) if isinstance(config, dict) else {}
    provider = str(model.get("provider", "")).strip().lower() if isinstance(model, dict) else ""
    runtime = str(model.get("openai_runtime", "")).strip().lower() if isinstance(model, dict) else ""
    api_mode = str(model.get("api_mode", "")).strip().lower() if isinstance(model, dict) else ""
    openai_safe = False
    if provider in {"openai", "openai-codex"}:
        safe_api_modes = {"", "chat_completions", "codex_responses"} if provider == "openai" else {"", "codex_responses"}
        openai_safe = runtime in {"", "auto"} and api_mode in safe_api_modes
    if (provider in {"openai", "openai-codex"} and not openai_safe) or (provider not in SAFE_HERMES_TOOL_DISPATCH_PROVIDERS and not openai_safe):
        raise RuntimeError(f"provider boundary unsafe in {home}: {provider or '<unset>'}")
    return provider


def _check_account_oauth_route(home: Path, provider: str, default: str, api_mode: str) -> None:
    config = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8")) or {}
    model = config.get("model", {}) if isinstance(config, dict) else {}
    actual = (
        str(model.get("provider", "")).strip(),
        str(model.get("default", "")).strip(),
        str(model.get("openai_runtime", "")).strip().lower(),
        str(model.get("api_mode", "")).strip().lower(),
    ) if isinstance(model, dict) else ("", "", "", "")
    if actual != (provider, default, "auto", api_mode):
        raise RuntimeError(f"account OAuth tier mismatch in {home}: expected {provider}/{default}/auto/{api_mode}")
    fallbacks = config.get("fallback_providers", []) if isinstance(config, dict) else []
    legacy_fallback = config.get("fallback_model") if isinstance(config, dict) else None
    if fallbacks or legacy_fallback:
        raise RuntimeError(f"account OAuth tier has non-OAuth fallbacks in {home}")


def _run(home: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    hermes = shutil.which("hermes")
    if not hermes:
        raise RuntimeError("Hermes CLI is required for doctor")
    return subprocess.run([hermes, *args], env={**os.environ, "HERMES_HOME": str(home)}, text=True, capture_output=True, check=True)


def _check_account_oauth_credentials(home: Path) -> None:
    """Require the active OpenAI account-provider credential to be OAuth.

    Only openai-codex is checked here: no Hermes profile is ever configured
    with provider "anthropic" any more, so there is no Hermes-side Anthropic
    OAuth credential to verify. Claude Code CLI readiness/account-login is
    verified independently by `_check_claude_cli_ready`.
    """
    for provider in ("openai-codex",):
        output = _run(home, ["auth", "list", provider]).stdout
        active = next((line for line in output.splitlines() if "←" in line), "")
        # `auth list` ends every active row with `<auth_type> <source> ←`.
        # Parse from the right because labels are user-controlled and may be
        # multi-word or contain the literal word "oauth".
        fields = active.replace("←", "").split()
        auth_type = fields[-2].lower() if len(fields) >= 4 else ""
        if auth_type != "oauth":
            raise RuntimeError(f"account OAuth credential is not active for {provider}")


def _check_claude_cli_ready() -> None:
    """Verify account-subscription auth and print-mode readiness without logging identity details."""
    executable = os.environ.get(CLAUDE_CLI_ENV) or shutil.which("claude")
    if not executable:
        raise RuntimeError("claude CLI is not installed or not on PATH; run `claude` account/Team login and retry")
    probe_env = _claude_probe_env(dict(os.environ))
    auth = subprocess.run(
        [executable, "auth", "status", "--text"], text=True, capture_output=True, env=probe_env, timeout=30,
    )
    login_line = next((line for line in auth.stdout.splitlines() if line.strip().lower().startswith("login method:")), "")
    method = login_line.split(":", 1)[1].strip().lower() if ":" in login_line else ""
    if auth.returncode != 0 or method not in CLAUDE_ACCOUNT_LOGIN_METHODS:
        raise RuntimeError("claude CLI account subscription is not active; use Claude Team/Pro/Max account login")
    result = subprocess.run(
        [executable, "-p", "--output-format", "json", "--model", "claude-haiku-4-5", "--max-turns", "1", "--safe-mode", "--no-session-persistence"],
        input="ping", text=True, capture_output=True, env=probe_env, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI print-mode readiness probe failed: exit {result.returncode}")


def _check_home(home: Path, *, worker_home: bool = False, dashboard_only: bool = False) -> None:
    if worker_home:
        _provider_boundary(home)
    for plugin in ((DASHBOARD_PLUGIN,) if dashboard_only else PLUGINS):
        package = home / "plugins" / plugin
        if not (package / "plugin.yaml").is_file():
            raise RuntimeError(f"missing {plugin} package in {home}")
        _run(home, ["plugins", "doctor", str(package), "--ci"])
    if dashboard_only:
        if (home / "plugins" / "hcw").exists() or (home / "plugins" / "superpowers").exists(): raise RuntimeError("base home must not contain enforcement hooks")
        return
    hcw = home / "plugins" / "hcw"
    launcher = hcw / "runtime" / "bin" / "hcw"
    if not launcher.is_file() or subprocess.run([str(launcher), "--help"], text=True, capture_output=True).returncode:
        raise RuntimeError(f"hcw launcher failed in {home}")
    if not (hcw / "dashboard" / "plugin_api.py").is_file():
        raise RuntimeError(f"dashboard API missing in {home}")
    api_spec = importlib.util.spec_from_file_location("hcw_installed_dashboard", hcw / "dashboard" / "plugin_api.py")
    if api_spec is None or api_spec.loader is None:
        raise RuntimeError("dashboard API cannot be imported")
    api = importlib.util.module_from_spec(api_spec)
    api_spec.loader.exec_module(api)
    if not getattr(api, "router", None):
        raise RuntimeError("dashboard API router is not registered")
    desktop = home / "desktop-plugins" / "hcw" / "plugin.js"
    if not desktop.is_file() or "export default plugin" not in desktop.read_text(encoding="utf-8"):
        raise RuntimeError(f"Desktop ESM payload missing in {home}")
    spec = importlib.util.spec_from_file_location("hcw_installed_plugin", hcw / "__init__.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("hcw plugin cannot be imported")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    bootstrap = module._build_bootstrap()
    required_commands = ("create-run", "approve-design", "approve-plan", "check", "commit", "review", "verify", "complete")
    expected_launcher = str(launcher.resolve())
    if module.BOOTSTRAP_MARKER not in bootstrap or expected_launcher not in bootstrap or any(f"hcw {command}" not in bootstrap and f"{expected_launcher} {command}" not in bootstrap for command in required_commands):
        raise RuntimeError("hcw bootstrap contract mismatch")
    remote_branding = hcw.parent / "superpowers" / "skills" / "brainstorming" / "scripts" / "server.cjs"
    if remote_branding.is_file() and ("primeradiant.com" in remote_branding.read_text(encoding="utf-8") or "SUPERPOWERS_BRAND_IMAGE_URL" in remote_branding.read_text(encoding="utf-8")):
        raise RuntimeError("remote branding present in pinned Superpowers payload")


def doctor(home: Path, *, source_profile: str = "dev", account_oauth_tiers: bool = False, verify_account_oauth: bool = False, verify_claude_cli: bool = False) -> int:
    home = Path(home).resolve()
    if source_profile in DESCRIPTIONS:
        raise RuntimeError(
            f"source profile '{source_profile}' collides with a managed workflow role; "
            "the orchestrator and role profiles must have distinct names"
        )
    # Every installed home is independently scanned: provider route, plugin
    # registration, launcher, dashboard and desktop payload all remain local.
    _check_home(home, dashboard_only=True)
    if verify_account_oauth:
        _check_account_oauth_credentials(home)
    if verify_claude_cli:
        _check_claude_cli_ready()
    source = home / "profiles" / source_profile
    if not source.is_dir():
        raise RuntimeError(f"missing source profile {source_profile}")
    _check_home(source, worker_home=True)
    if account_oauth_tiers:
        _check_account_oauth_route(source, "openai-codex", "gpt-5.6-sol", "codex_responses")
    for role, description in DESCRIPTIONS.items():
        profile_home = home / "profiles" / role
        if not profile_home.is_dir():
            raise RuntimeError(f"missing role profile {role}")
        shown = _run(home, ["profile", "describe", role]).stdout
        if description not in shown:
            raise RuntimeError(f"profile description mismatch for {role}")
        _check_home(profile_home, worker_home=True)
        if account_oauth_tiers:
            _check_account_oauth_route(profile_home, *ACCOUNT_OAUTH_TIERS[role])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-home", required=True)
    parser.add_argument("--source-profile", default="dev", help="installed workflow source profile; defaults to dev")
    parser.add_argument("--account-oauth-tiers", action="store_true", help="verify exact OpenAI account OAuth tier routing for every Hermes profile")
    parser.add_argument("--verify-account-oauth", action="store_true", help="verify the active OpenAI provider credential is account OAuth, not an API key")
    parser.add_argument("--verify-claude-cli", action="store_true", help="verify the external Claude Code CLI is installed and print-mode ready (never required for isolated installs)")
    args = parser.parse_args()
    try:
        return doctor(
            Path(args.hermes_home),
            source_profile=args.source_profile,
            account_oauth_tiers=args.account_oauth_tiers,
            verify_account_oauth=args.verify_account_oauth,
            verify_claude_cli=args.verify_claude_cli,
        )
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"hcw doctor: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
