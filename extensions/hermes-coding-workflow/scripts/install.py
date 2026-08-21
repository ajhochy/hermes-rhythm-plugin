"""Install the complete, self-contained Hermes Coding Workflow lifecycle.

The repository root is the control plane.  This module deliberately never
looks for a sibling worktree: that shape is unsafe after a merge and made an
installation depend on a developer's checkout topology.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SOURCES = {"hcw": "hermes-coding-workflow", "superpowers": "superpowers-pinned"}
DASHBOARD_PLUGIN = "hcw-dashboard"
ROLE_DESCRIPTIONS = {
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
OWNERSHIP_FILE = ".hcw-lifecycle.json"

# Hermes invokes native pre_tool_call hooks only for tools dispatched by its
# own agent loop. Codex app-server and ACP hand execution to another coding
# runtime, so a plugin hook cannot police their direct file/shell tools. OpenAI
# account OAuth defaults to Hermes-owned codex_responses and is safe unless the
# profile explicitly opts into codex_app_server. Anthropic is deliberately not
# in this allowlist: no Hermes profile may hold Anthropic provider credentials;
# the four Claude-tier stages run as an external Claude Code CLI subprocess
# authenticated by its own account/Team login instead.
SAFE_HERMES_TOOL_DISPATCH_PROVIDERS = frozenset({
    "openai", "gemini", "google", "openrouter", "nous",
})
DIRECT_CODE_TOOL_PROVIDERS = frozenset({"copilot-acp", "codex", "claude-acp", "opencode-acp"})
PROVIDER_BOUNDARY_ERROR = "HCW_PROVIDER_BOUNDARY_UNSAFE"


def _hermes() -> str:
    executable = shutil.which("hermes")
    if not executable:
        raise RuntimeError("Hermes CLI is required; install Hermes and retry")
    return executable


def _env(home: Path) -> dict[str, str]:
    return {**os.environ, "HERMES_HOME": str(home)}


def _run(home: Path, argv: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run([_hermes(), *argv], env=_env(home), check=True, text=True, capture_output=capture)


def _read_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RuntimeError(f"{PROVIDER_BOUNDARY_ERROR}: unreadable config: {path}: {exc}") from exc
    return value if isinstance(value, dict) else {}


def _provider_for(home: Path) -> str:
    model = _read_config(home / "config.yaml").get("model", {})
    if isinstance(model, str):
        return ""
    return str(model.get("provider", "")).strip().lower() if isinstance(model, dict) else ""


def _assert_safe_provider(home: Path, label: str) -> None:
    config = _read_config(home / "config.yaml")
    model = config.get("model", {})
    provider = str(model.get("provider", "")).strip().lower() if isinstance(model, dict) else ""
    runtime = str(model.get("openai_runtime", "")).strip().lower()
    api_mode = str(model.get("api_mode", "")).strip().lower()
    if provider in {"openai", "openai-codex"}:
        safe_api_modes = {"", "chat_completions", "codex_responses"} if provider == "openai" else {"", "codex_responses"}
        if runtime in {"", "auto"} and api_mode in safe_api_modes:
            return
        raise RuntimeError(f"{PROVIDER_BOUNDARY_ERROR}: {label} uses provider '{provider}'")
    if provider in SAFE_HERMES_TOOL_DISPATCH_PROVIDERS:
        return
    # Prefix matching covers future ACP variants without treating ordinary
    # Claude/OpenCode model names as proof of safe Hermes dispatch.
    direct = provider in DIRECT_CODE_TOOL_PROVIDERS or provider.endswith("-acp") or provider.startswith("codex-")
    kind = "direct-code-tool" if direct else "unknown"
    raise RuntimeError(
        f"{PROVIDER_BOUNDARY_ERROR}: {label} provider '{provider or '<unset>'}' is {kind}; "
        "role workers require a Hermes-tool-dispatch provider"
    )


def _profile_metadata(home: Path, name: str) -> dict[str, Any]:
    path = home / "profiles" / name / "profile.yaml"
    if not path.is_file():
        return {}
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RuntimeError(f"invalid role metadata for '{name}': {exc}") from exc
    return value if isinstance(value, dict) else {}


def _preflight(home: Path, source_profile: str, worker_source_profile: str) -> list[Path]:
    if not home.is_dir():
        raise RuntimeError(f"Hermes home does not exist: {home}")
    if source_profile in ROLE_DESCRIPTIONS:
        raise RuntimeError(
            f"source profile '{source_profile}' collides with a managed workflow role; "
            "the orchestrator and role profiles must have distinct names"
        )
    _hermes()
    if not (home / "profiles" / source_profile).is_dir():
        raise RuntimeError(f"source profile '{source_profile}' does not exist in {home / 'profiles'}")
    worker_source = home / "profiles" / worker_source_profile
    if not worker_source.is_dir():
        raise RuntimeError(f"worker source profile '{worker_source_profile}' does not exist in {home / 'profiles'}")
    _assert_safe_provider(home / "profiles" / source_profile, f"source profile '{source_profile}'")
    _assert_safe_provider(worker_source, f"worker source profile '{worker_source_profile}'")
    required = [
        PACKAGE_ROOT / "pyproject.toml",
        PACKAGE_ROOT / "src" / "hermes_coding_workflow" / "cli.py",
        PACKAGE_ROOT / "dashboard" / "plugin_api.py",
        PACKAGE_ROOT / "desktop" / "plugin.js",
        *(PACKAGE_ROOT / "plugins" / source / "plugin.yaml" for source in (*PLUGIN_SOURCES.values(), DASHBOARD_PLUGIN)),
        PACKAGE_ROOT / "skills",
        PACKAGE_ROOT / "vendor" / "superpowers" / "skills",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError("workflow source payload is incomplete: " + ", ".join(missing))
    source_target = home / "profiles" / source_profile
    # The source/orchestrator is mutated by plugin enablement and, optionally,
    # OAuth tier routing, so its config must roll back with the base home.
    targets = [home, source_target]
    for name, description in ROLE_DESCRIPTIONS.items():
        target = home / "profiles" / name
        if target.exists() and not target.is_dir():
            raise RuntimeError(f"role profile path is not a directory: {target}")
        if target.is_dir():
            # Existing roles are user-owned.  Do not normalize them in place:
            # an unexpected identity or provider is a preflight failure.
            if _profile_metadata(home, name).get("description", "") != description:
                raise RuntimeError(f"existing role profile '{name}' has an unexpected description")
            _assert_safe_provider(target, f"existing role profile '{name}'")
            if target not in targets:
                targets.append(target)
    return targets


@dataclass
class Transaction:
    root: Path
    backups: list[tuple[Path, Path | None]] = field(default_factory=list)
    created_profiles: list[str] = field(default_factory=list)
    snapshots: list[tuple[Path, bytes | None]] = field(default_factory=list)

    def snapshot_file(self, path: Path) -> None:
        self.snapshots.append((path, path.read_bytes() if path.exists() else None))

    def replace_tree(self, source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=f".{target.name}-stage-", dir=target.parent)) / target.name
        shutil.copytree(source, stage, symlinks=True, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc"))
        backup = self.root / f"payload-{len(self.backups)}"
        if target.exists():
            os.replace(target, backup)
            prior: Path | None = backup
        else:
            prior = None
        try:
            os.replace(stage, target)
        except BaseException:
            if prior and prior.exists():
                os.replace(prior, target)
            raise
        finally:
            shutil.rmtree(stage.parent, ignore_errors=True)
        self.backups.append((target, prior))

    def rollback(self, home: Path) -> None:
        for target, backup in reversed(self.backups):
            if target.exists():
                shutil.rmtree(target)
            if backup and backup.exists():
                os.replace(backup, target)
        for name in reversed(self.created_profiles):
            target = home / "profiles" / name
            try:
                _run(home, ["profile", "delete", name, "--yes"])
            except (RuntimeError, subprocess.CalledProcessError):
                # A sandboxed Hermes may be unable to enumerate host PIDs
                # before deletion.  This directory was created in this exact
                # transaction, so removing only this resolved profile path is
                # the safe rollback fallback; never touch pre-existing roles.
                if target.is_dir():
                    shutil.rmtree(target)
        for path, contents in reversed(self.snapshots):
            if contents is None:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(contents)

    def commit(self) -> None:
        for _, backup in self.backups:
            if backup and backup.exists():
                shutil.rmtree(backup)


def _build_plugin(plugin: str, stage_root: Path) -> Path:
    source_name = DASHBOARD_PLUGIN if plugin == DASHBOARD_PLUGIN else PLUGIN_SOURCES[plugin]
    payload = stage_root / plugin
    shutil.copytree(PACKAGE_ROOT / "plugins" / source_name, payload, symlinks=True)
    if plugin in {"hcw", DASHBOARD_PLUGIN}:
        if plugin == DASHBOARD_PLUGIN:
            shutil.rmtree(payload / "dashboard", ignore_errors=True)
            shutil.copytree(PACKAGE_ROOT / "dashboard", payload / "dashboard", symlinks=True)
            return payload
        shutil.copytree(PACKAGE_ROOT / "skills", payload / "skills", symlinks=True)
        shutil.rmtree(payload / "dashboard", ignore_errors=True)
        shutil.copytree(PACKAGE_ROOT / "dashboard", payload / "dashboard", symlinks=True)
        runtime = payload / "runtime"
        site, bin_dir = runtime / "site", runtime / "bin"
        bin_dir.mkdir(parents=True)
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--target", str(site), "--no-deps", "--no-build-isolation", str(PACKAGE_ROOT)],
            check=True,
            text=True,
            capture_output=True,
        )
        launcher = bin_dir / "hcw"
        launcher.write_text(
            "#!/usr/bin/env python3\nfrom pathlib import Path\nimport sys\n"
            "sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'site'))\n"
            "from hermes_coding_workflow.cli import main\nraise SystemExit(main())\n",
            encoding="utf-8",
        )
        launcher.chmod(0o755)
    elif plugin == "superpowers":
        shutil.copytree(PACKAGE_ROOT / "vendor" / "superpowers" / "skills", payload / "skills", symlinks=True)
        shutil.copy2(PACKAGE_ROOT / "vendor" / "superpowers" / "NOTICE", payload / "NOTICE")
    return payload


def _stage_home(home: Path, transaction: Transaction) -> None:
    with tempfile.TemporaryDirectory(prefix="hcw-payload-", dir=transaction.root) as temporary:
        root = Path(temporary)
        for plugin in PLUGIN_SOURCES:
            transaction.replace_tree(_build_plugin(plugin, root), home / "plugins" / plugin)
        desktop = root / "desktop-plugin"
        desktop.mkdir()
        shutil.copy2(PACKAGE_ROOT / "desktop" / "plugin.js", desktop / "plugin.js")
        transaction.replace_tree(desktop, home / "desktop-plugins" / "hcw")

def _stage_dashboard_home(home: Path, transaction: Transaction) -> None:
    with tempfile.TemporaryDirectory(prefix="hcw-dashboard-", dir=transaction.root) as temporary:
        root = Path(temporary)
        transaction.replace_tree(_build_plugin(DASHBOARD_PLUGIN, root), home / "plugins" / DASHBOARD_PLUGIN)
        desktop = root / "desktop-plugin"; desktop.mkdir(); shutil.copy2(PACKAGE_ROOT / "desktop" / "plugin.js", desktop / "plugin.js")
        transaction.replace_tree(desktop, home / "desktop-plugins" / "hcw")


def _write_ownership(home: Path, created: list[str]) -> None:
    path = home / OWNERSHIP_FILE
    previous: dict[str, object] = {}
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    owned = set(previous.get("created_profiles", [])) if isinstance(previous.get("created_profiles"), list) else set()
    owned.update(created)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(json.dumps({"created_profiles": sorted(owned)}, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _ensure_profiles(home: Path, worker_source_profile: str, transaction: Transaction) -> list[Path]:
    profiles = home / "profiles"
    result: list[Path] = []
    for name, description in ROLE_DESCRIPTIONS.items():
        target = profiles / name
        if not target.is_dir():
            _run(home, ["profile", "create", name, "--clone-from", worker_source_profile, "--no-alias", "--description", description])
            transaction.created_profiles.append(name)
        result.append(target)
    return result


def _configure_account_oauth_tiers(source_home: Path, role_homes: list[Path]) -> None:
    routes = {source_home.name: ("openai-codex", "gpt-5.6-sol", "codex_responses"), **ACCOUNT_OAUTH_TIERS}
    for target in (source_home, *role_homes):
        provider, model, api_mode = routes[target.name]
        _run(target, ["config", "set", "model.provider", provider])
        _run(target, ["config", "set", "model.default", model])
        _run(target, ["config", "set", "model.openai_runtime", "auto"])
        _run(target, ["config", "set", "model.api_mode", api_mode])
        config = _read_config(target / "config.yaml")
        for fallback_key in ("fallback_providers", "fallback_model"):
            if fallback_key in config:
                _run(target, ["config", "unset", fallback_key])
        _assert_safe_provider(target, f"OAuth tier profile '{target.name}'")


def _enable_and_check(home: Path) -> None:
    for plugin in PLUGIN_SOURCES:
        _run(home, ["plugins", "enable", plugin, "--no-allow-tool-override"])
        _run(home, ["plugins", "doctor", str(home / "plugins" / plugin), "--ci"])

def _enable_dashboard(home: Path) -> None:
    _run(home, ["plugins", "enable", DASHBOARD_PLUGIN, "--no-allow-tool-override"])
    _run(home, ["plugins", "doctor", str(home / "plugins" / DASHBOARD_PLUGIN), "--ci"])


def install(home: Path, *, source_profile: str = "dev", worker_source_profile: str | None = None, account_oauth_tiers: bool = False, fail_at: str | None = None) -> int:
    home = Path(home).resolve()
    worker_source_profile = worker_source_profile or source_profile
    targets = _preflight(home, source_profile, worker_source_profile)
    with tempfile.TemporaryDirectory(prefix="hcw-lifecycle-", dir=home.parent) as temporary:
        transaction = Transaction(Path(temporary))
        for target in targets:
            transaction.snapshot_file(target / "config.yaml")
        transaction.snapshot_file(home / OWNERSHIP_FILE)
        try:
            profile_homes = _ensure_profiles(home, worker_source_profile, transaction)
            if account_oauth_tiers:
                _configure_account_oauth_tiers(home / "profiles" / source_profile, profile_homes)
            _stage_dashboard_home(home, transaction)
            for target_home in (home / "profiles" / source_profile, *profile_homes):
                _stage_home(target_home, transaction)
            _enable_dashboard(home)
            for target_home in (home / "profiles" / source_profile, *profile_homes):
                _enable_and_check(target_home)
                if fail_at == "after-enable":
                    raise RuntimeError("injected failure after enable")
                if fail_at == "after-doctor":
                    raise RuntimeError("injected failure after doctor")
            _write_ownership(home, transaction.created_profiles)
        except BaseException:
            transaction.rollback(home)
            raise
        transaction.commit()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-home", required=True, help="explicit Hermes home; never defaults to a user home")
    parser.add_argument("--source-profile", required=True, help="existing profile cloned into each workflow role")
    parser.add_argument("--worker-source-profile", help="safe Hermes-tool-dispatch profile cloned into role workers; defaults to --source-profile")
    parser.add_argument("--account-oauth-tiers", action="store_true", help="route the orchestrator and every role to OpenAI account OAuth tiers; no profile is ever configured with provider anthropic")
    args = parser.parse_args()
    return install(
        Path(args.hermes_home),
        source_profile=args.source_profile,
        worker_source_profile=args.worker_source_profile,
        account_oauth_tiers=args.account_oauth_tiers,
    )


if __name__ == "__main__":
    raise SystemExit(main())
