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
    call(home, sys.executable, str(ROOT / "scripts" / "install.py"), "--hermes-home", str(home), "--source-profile", "dev")
    assert (home / "plugins" / "hcw-dashboard" / "dashboard" / "plugin_api.py").is_file()
    assert not (home / "plugins" / "hcw").exists()
    for target in (home / "profiles" / "dev", *(home / "profiles" / role for role in ROLES)):
        assert (target / "plugins" / "hcw" / "dashboard" / "plugin_api.py").is_file()
        assert (target / "plugins" / "hcw" / "runtime" / "bin" / "hcw").is_file()
        assert (target / "plugins" / "superpowers" / "skills").is_dir()
        assert (target / "desktop-plugins" / "hcw" / "plugin.js").is_file()
    call(home, sys.executable, str(ROOT / "scripts" / "doctor.py"), "--hermes-home", str(home))
    call(home, sys.executable, str(ROOT / "scripts" / "uninstall.py"), "--hermes-home", str(home))
    assert not (home / "plugins" / "hcw").exists()
    assert (home / "profiles" / "dev-builder").is_dir(), "uninstall preserves profiles unless explicitly requested"


def test_installer_never_uses_a_sibling_control_plane_checkout() -> None:
    source = (ROOT / "scripts" / "install.py").read_text(encoding="utf-8")
    assert "PACKAGE_ROOT.parent / \"control-plane\"" not in source
    assert "str(PACKAGE_ROOT)" in source


def test_unsafe_worker_provider_fails_closed_before_any_mutation(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "hermes"; profile = home / "profiles" / "unsafe"
    profile.mkdir(parents=True)
    (profile / "config.yaml").write_text("model:\n  provider: openai-codex\n", encoding="utf-8")
    before = {path.relative_to(home): path.read_bytes() for path in home.rglob("*") if path.is_file()}
    monkeypatch.setattr(installer, "_hermes", lambda: "hermes")
    try:
        installer.install(home, source_profile="unsafe")
    except RuntimeError as exc:
        assert str(exc).startswith(installer.PROVIDER_BOUNDARY_ERROR)
    else:
        raise AssertionError("unsafe direct-code provider must be rejected")
    after = {path.relative_to(home): path.read_bytes() for path in home.rglob("*") if path.is_file()}
    assert after == before


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
    base_config = (home / "config.yaml").read_bytes(); owned = ownership.read_bytes(); prior_payload = (payload / "keep.txt").read_bytes()
    if failure_point == "ownership-write":
        def fail_ownership(*args, **kwargs):
            raise OSError("injected ownership write failure")
        monkeypatch.setattr(installer, "_write_ownership", fail_ownership)
    try:
        installer.install(home, source_profile="safe", fail_at=failure_point if failure_point != "ownership-write" else None)
    except RuntimeError as exc:
        assert str(exc) == f"injected failure {failure_point.replace('-', ' ')}"
    except OSError as exc:
        assert failure_point == "ownership-write" and str(exc) == "injected ownership write failure"
    else:
        raise AssertionError("injected failure must escape")
    assert (home / "config.yaml").read_bytes() == base_config
    assert ownership.read_bytes() == owned
    assert (home / "plugins" / "hcw" / "keep.txt").read_bytes() == prior_payload
    assert all(not (home / "profiles" / role).exists() for role in ROLES)
