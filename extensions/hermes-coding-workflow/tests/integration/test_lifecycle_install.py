"""Public lifecycle contracts against an isolated, real Hermes home."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import importlib.util
import pytest

ROOT = Path(__file__).parents[2]
HERMES_SOURCE = Path("/Users/ajhochhalter/.hermes/hermes-agent")
ROLES = ("dev-planner", "dev-contract", "dev-builder", "dev-spec-reviewer", "dev-quality-reviewer", "dev-verifier", "dev-recorder")

spec = importlib.util.spec_from_file_location("hcw_install", ROOT / "scripts" / "install.py")
installer = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = installer
spec.loader.exec_module(installer)

doctor_spec = importlib.util.spec_from_file_location("hcw_doctor", ROOT / "scripts" / "doctor.py")
assert doctor_spec and doctor_spec.loader
doctor = importlib.util.module_from_spec(doctor_spec)
doctor_spec.loader.exec_module(doctor)


def call(home: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(argv), env={**os.environ, "HERMES_HOME": str(home), "PYTHONPATH": str(HERMES_SOURCE)}, text=True, capture_output=True, check=True)


def test_root_control_plane_installs_native_payloads_in_every_role_home(tmp_path: Path) -> None:
    assert HERMES_SOURCE.is_dir(), "mandatory lifecycle test requires local Hermes v0.20 source"
    assert shutil.which("hermes"), "mandatory lifecycle test requires local Hermes CLI"
    home = tmp_path / "hermes"; home.mkdir()
    call(home, "hermes", "profile", "create", "dev", "--no-alias")
    # This is configuration only: it performs no provider/model call.
    call(home, "hermes", "config", "set", "model.provider", "openai")
    call(home, "hermes", "config", "set", "model.default", "gpt-4o-mini")
    call(home / "profiles" / "dev", "hermes", "config", "set", "model.provider", "openai")
    call(home / "profiles" / "dev", "hermes", "config", "set", "model.default", "gpt-4o-mini")
    call(home, sys.executable, str(ROOT / "scripts" / "install.py"), "--hermes-home", str(home), "--source-profile", "dev", "--account-oauth-tiers")
    assert (home / "plugins" / "hcw-dashboard" / "dashboard" / "plugin_api.py").is_file()
    assert not (home / "plugins" / "hcw").exists()
    for target in (home / "profiles" / "dev", *(home / "profiles" / role for role in ROLES)):
        assert (target / "plugins" / "hcw" / "dashboard" / "plugin_api.py").is_file()
        assert (target / "plugins" / "hcw" / "runtime" / "bin" / "hcw").is_file()
        assert (target / "plugins" / "superpowers" / "skills").is_dir()
        assert (target / "desktop-plugins" / "hcw" / "plugin.js").is_file()
    expected_routes = {
        "dev": ("openai-codex", "gpt-5.6-sol", "codex_responses"),
        **installer.ACCOUNT_OAUTH_TIERS,
    }
    for profile, (provider, model, api_mode) in expected_routes.items():
        config = installer._read_config(home / "profiles" / profile / "config.yaml")["model"]
        assert (config["provider"], config["default"], config["openai_runtime"], config["api_mode"]) == (provider, model, "auto", api_mode)
    call(home, sys.executable, str(ROOT / "scripts" / "doctor.py"), "--hermes-home", str(home), "--account-oauth-tiers")
    call(home, sys.executable, str(ROOT / "scripts" / "uninstall.py"), "--hermes-home", str(home))
    assert not (home / "plugins" / "hcw").exists()
    assert (home / "profiles" / "dev-builder").is_dir(), "uninstall preserves profiles unless explicitly requested"


def test_installer_never_uses_a_sibling_control_plane_checkout() -> None:
    source = (ROOT / "scripts" / "install.py").read_text(encoding="utf-8")
    assert "PACKAGE_ROOT.parent / \"control-plane\"" not in source
    assert "str(PACKAGE_ROOT)" in source


def test_openai_account_oauth_defaults_to_hook_safe_responses_runtime(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "hermes"; profile = home / "profiles" / "oauth"
    profile.mkdir(parents=True)
    (profile / "config.yaml").write_text(
        "model:\n  provider: openai-codex\n  default: gpt-5.6-sol\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(installer, "_hermes", lambda: "hermes")
    installer._assert_safe_provider(profile, "OpenAI OAuth profile")


@pytest.mark.parametrize("provider", ("openai", "openai-codex"))
def test_codex_app_server_fails_closed_before_any_mutation(tmp_path: Path, monkeypatch, provider: str) -> None:
    home = tmp_path / "hermes"; profile = home / "profiles" / "unsafe"
    profile.mkdir(parents=True)
    (profile / "config.yaml").write_text(
        f"model:\n  provider: {provider}\n  default: gpt-5.6-sol\n  openai_runtime: codex_app_server\n",
        encoding="utf-8",
    )
    before = {path.relative_to(home): path.read_bytes() for path in home.rglob("*") if path.is_file()}
    monkeypatch.setattr(installer, "_hermes", lambda: "hermes")
    try:
        installer.install(home, source_profile="unsafe")
    except RuntimeError as exc:
        assert str(exc).startswith(installer.PROVIDER_BOUNDARY_ERROR)
    else:
        raise AssertionError("Codex app-server must be rejected")
    after = {path.relative_to(home): path.read_bytes() for path in home.rglob("*") if path.is_file()}
    assert after == before


def test_unknown_openai_oauth_runtime_fails_closed(tmp_path: Path) -> None:
    profile = tmp_path / "oauth"; profile.mkdir()
    (profile / "config.yaml").write_text(
        "model:\n  provider: openai-codex\n  default: gpt-5.6-sol\n  openai_runtime: future_runtime\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match=installer.PROVIDER_BOUNDARY_ERROR):
        installer._assert_safe_provider(profile, "OpenAI OAuth profile")


def test_source_profile_role_collision_fails_before_mutation(tmp_path: Path) -> None:
    home = tmp_path / "hermes"; home.mkdir()
    before = {path.relative_to(home): path.read_bytes() for path in home.rglob("*") if path.is_file()}

    with pytest.raises(RuntimeError, match="collides with a managed workflow role"):
        installer.install(home, source_profile="dev-builder", account_oauth_tiers=True)

    after = {path.relative_to(home): path.read_bytes() for path in home.rglob("*") if path.is_file()}
    assert after == before


def test_doctor_rejects_source_profile_role_collision_before_scanning(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(doctor, "_check_home", lambda *args, **kwargs: pytest.fail("scan must not start"))
    with pytest.raises(RuntimeError, match="collides with a managed workflow role"):
        doctor.doctor(tmp_path, source_profile="dev-builder", account_oauth_tiers=True)


@pytest.mark.parametrize("provider", ("openai", "openai-codex"))
def test_explicit_api_mode_codex_app_server_fails_closed(tmp_path: Path, provider: str) -> None:
    profile = tmp_path / "oauth"; profile.mkdir()
    (profile / "config.yaml").write_text(
        f"model:\n  provider: {provider}\n  default: gpt-5.6-sol\n  openai_runtime: auto\n  api_mode: codex_app_server\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match=installer.PROVIDER_BOUNDARY_ERROR):
        installer._assert_safe_provider(profile, "OpenAI OAuth profile")


def test_account_oauth_tiers_route_each_role_by_required_capability(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "hermes"
    role_homes = []
    for role in ROLES:
        target = home / "profiles" / role
        target.mkdir(parents=True)
        (target / "config.yaml").write_text("fallback_providers:\n  - provider: openrouter\n    model: test\n", encoding="utf-8")
        role_homes.append(target)
    source = home / "profiles" / "hcw-dev"
    source.mkdir(parents=True)
    (source / "config.yaml").write_text("fallback_providers:\n  - provider: openrouter\n    model: test\n", encoding="utf-8")
    calls = []
    monkeypatch.setattr(installer, "_run", lambda target, argv, **kwargs: calls.append((target, argv)))
    monkeypatch.setattr(installer, "_assert_safe_provider", lambda target, label: None)

    installer._configure_account_oauth_tiers(source, role_homes)

    expected = {
        "hcw-dev": ("openai-codex", "gpt-5.6-sol", "codex_responses"),
        **installer.ACCOUNT_OAUTH_TIERS,
    }
    for profile, (provider, model, api_mode) in expected.items():
        target = source if profile == "hcw-dev" else home / "profiles" / profile
        assert (target, ["config", "set", "model.provider", provider]) in calls
        assert (target, ["config", "set", "model.default", model]) in calls
        assert (target, ["config", "set", "model.openai_runtime", "auto"]) in calls
        assert (target, ["config", "set", "model.api_mode", api_mode]) in calls
        assert (target, ["config", "unset", "fallback_providers"]) in calls


@pytest.mark.parametrize(
    "config",
    (
        "model:\n  provider: anthropic\n  default: gpt-5.6-sol\n  openai_runtime: auto\n",
        "model:\n  provider: openai-codex\n  default: gpt-5.6-terra\n  openai_runtime: auto\n",
        "model:\n  provider: openai-codex\n  default: gpt-5.6-sol\n  openai_runtime: codex_app_server\n",
        "model:\n  provider: openai-codex\n  default: gpt-5.6-sol\n  openai_runtime: auto\nfallback_providers:\n  - provider: openrouter\n    model: test\n",
    ),
)
def test_doctor_rejects_oauth_route_or_fallback_drift(tmp_path: Path, config: str) -> None:
    (tmp_path / "config.yaml").write_text(config, encoding="utf-8")
    with pytest.raises(RuntimeError, match="account OAuth tier"):
        doctor._check_account_oauth_route(tmp_path, "openai-codex", "gpt-5.6-sol", "codex_responses")


def test_doctor_requires_active_oauth_credentials_for_both_accounts(tmp_path: Path, monkeypatch) -> None:
    outputs = {
        "openai-codex": "openai-codex (1 credential):\n  #1 chatgpt oauth browser ←\n",
        "anthropic": "anthropic (1 credential):\n  #1 anthropic-oauth-1 oauth hermes_pkce ←\n",
    }
    monkeypatch.setattr(
        doctor,
        "_run",
        lambda home, args: subprocess.CompletedProcess(args, 0, stdout=outputs[args[-1]], stderr=""),
    )
    doctor._check_account_oauth_credentials(tmp_path)

    outputs["anthropic"] = "anthropic (1 credential):\n  #1 team oauth api_key env ←\n"
    with pytest.raises(RuntimeError, match="account OAuth credential"):
        doctor._check_account_oauth_credentials(tmp_path)


@pytest.mark.parametrize("failure_point", ("after-enable", "after-doctor", "ownership-write"))
def test_post_stage_failure_restores_configs_payloads_and_created_profiles(tmp_path: Path, monkeypatch, failure_point: str) -> None:
    assert HERMES_SOURCE.is_dir() and shutil.which("hermes"), "mandatory lifecycle test requires local Hermes"
    home = tmp_path / "hermes"; home.mkdir()
    call(home, "hermes", "profile", "create", "safe", "--no-alias")
    call(home, "hermes", "config", "set", "model.provider", "openai")
    call(home, "hermes", "config", "set", "model.default", "gpt-4o-mini")
    call(home / "profiles" / "safe", "hermes", "config", "set", "model.provider", "openai")
    call(home / "profiles" / "safe", "hermes", "config", "set", "model.default", "gpt-4o-mini")
    (home / "config.yaml").write_text("plugins:\n  enabled: [unrelated]\nsecret_ref: keep\n", encoding="utf-8")
    ownership = home / ".hcw-lifecycle.json"; ownership.write_text('{"created_profiles":["other"]}\n', encoding="utf-8")
    payload = home / "plugins" / "hcw"; payload.mkdir(parents=True); (payload / "keep.txt").write_text("preserve", encoding="utf-8")
    base_config = (home / "config.yaml").read_bytes(); source_config = (home / "profiles" / "safe" / "config.yaml").read_bytes(); owned = ownership.read_bytes(); prior_payload = (payload / "keep.txt").read_bytes()
    if failure_point == "ownership-write":
        def fail_ownership(*args, **kwargs):
            raise OSError("injected ownership write failure")
        monkeypatch.setattr(installer, "_write_ownership", fail_ownership)
    try:
        installer.install(home, source_profile="safe", account_oauth_tiers=True, fail_at=failure_point if failure_point != "ownership-write" else None)
    except RuntimeError as exc:
        assert str(exc) == f"injected failure {failure_point.replace('-', ' ')}"
    except OSError as exc:
        assert failure_point == "ownership-write" and str(exc) == "injected ownership write failure"
    else:
        raise AssertionError("injected failure must escape")
    assert (home / "config.yaml").read_bytes() == base_config
    assert (home / "profiles" / "safe" / "config.yaml").read_bytes() == source_config
    assert ownership.read_bytes() == owned
    assert (home / "plugins" / "hcw" / "keep.txt").read_bytes() == prior_payload
    assert all(not (home / "profiles" / role).exists() for role in ROLES)
