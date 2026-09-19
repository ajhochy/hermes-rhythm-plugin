"""Deterministic M9 packaging gates, exercised only against local fixtures.

The tests catch a future packager that quietly emits split renderer chunks,
ships a second React runtime, changes the opt-in destination, or includes a
credential in operator-facing diagnostics.  They deliberately do not build,
install, sign, notarize, or publish anything.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plugins.rhythm.packaging.validate import (
    PackagingGateError,
    load_packaging_manifest,
    validate_install_doctor_fixture,
    validate_macos_bundle,
    validate_package_tree,
)
from plugins.rhythm.packaging.build import build_feature_pack, build_macos_fixture
from plugins.rhythm.packaging.lifecycle import (
    doctor_feature_pack,
    install_feature_pack,
    rollback_feature_pack,
    uninstall_feature_pack,
)


REPO_ROOT = Path(__file__).parents[3]


def _write(root: Path, relative: str, content: str = "fixture") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _manifest() -> dict:
    return load_packaging_manifest(REPO_ROOT)


def _write_complete_package(root: Path, manifest: dict) -> None:
    for relative in manifest["content"]["python_modules"]:
        _write(root, relative)
    for relative in manifest["content"]["assets"]:
        _write(root, relative)
    for relative in manifest["content"]["skills"]:
        _write(root, relative)
    _write(root, manifest["desktop"]["entry"], "export { RhythmPlugin } from '@hermes/plugin-sdk';\n")
    for license_ in manifest["licenses"]:
        _write(root, license_["path"], "MIT License\n" if license_["spdx"] == "MIT" else "ISC License\n")
    _write(root, manifest["provenance"]["path"], "Source: fixture\nRevision: fixture\nTransformation: none\n")


def test_manifest_is_deterministic_and_declares_the_unified_opt_in_tree():
    """Regression: a package silently gains a second install root or mutable plan."""
    manifest = _manifest()

    assert manifest["install"]["root"] == "<HERMES_HOME>/plugins/rhythm"
    assert manifest["install"]["opt_in"] is True
    assert manifest["status"] == "final-automated-gates"
    assert manifest["install"]["operations"] == ["install", "upgrade", "force-reinstall", "rollback", "uninstall"]
    assert manifest["desktop"]["format"] == "esm"
    assert manifest["desktop"]["artifact_count"] == 1
    assert manifest["content"]["package_data"] == [
        "contracts/*.json",
        "dashboard/manifest.json",
        "dashboard/dist/index.js",
        "dashboard/theme/rhythm.css",
        "packaging/package-manifest.json",
        "packaging/RELEASE-GATE.md",
        "packaging/LIVE-GATE.md",
        "plugin.yaml",
        "skills/rhythm/SKILL.md",
    ]
    assert manifest["release_gate"]["status"] == "pending"
    gate = (REPO_ROOT / "plugins/rhythm/packaging/RELEASE-GATE.md").read_text(encoding="utf-8")
    assert "remains pending" in gate and "does **not** assert" in gate


def test_final_builder_is_repeatable_closed_and_has_one_real_desktop_esm_artifact(tmp_path):
    """Regression: an integrated build silently relies on source-tree leftovers."""
    manifest = _manifest()
    first = build_feature_pack(REPO_ROOT, tmp_path / "first")
    second = build_feature_pack(REPO_ROOT, tmp_path / "second")

    validate_package_tree(first, manifest)
    validate_package_tree(second, manifest)
    assert {
        path.relative_to(first).as_posix(): path.read_bytes()
        for path in first.rglob("*") if path.is_file()
    } == {
        path.relative_to(second).as_posix(): path.read_bytes()
        for path in second.rglob("*") if path.is_file()
    }
    bundle = (first / manifest["desktop"]["entry"]).read_text(encoding="utf-8")
    assert 'from"react"' in bundle
    assert 'from"lucide-react"' not in bundle
    assert "from'lucide-react'" not in bundle


def test_temp_home_lifecycle_is_opt_in_reversible_and_confined_to_rhythm_tree(tmp_path):
    """Regression: a feature-pack install enables itself or mutates unrelated home state."""
    package = build_feature_pack(REPO_ROOT, tmp_path / "package")
    home = tmp_path / "home"

    first = install_feature_pack(package, home)
    target = home / "plugins" / "rhythm"
    assert first["status"] == "installed" and first["enabled"] is False
    assert {path.relative_to(home).parts[0] for path in home.rglob("*")} == {"plugins"}
    assert target.is_dir()

    same = install_feature_pack(package, home)
    assert same["status"] == "unchanged"
    forced = install_feature_pack(package, home, force_reinstall=True)
    assert forced["status"] == "reinstalled"
    upgraded = install_feature_pack(package, home, upgrade=True)
    assert upgraded["restart_required"] is True and upgraded["restart_signal"] == "hermes gateway restart"
    assert rollback_feature_pack(home)["status"] == "rolled_back"
    assert uninstall_feature_pack(home)["status"] == "uninstalled"
    assert not target.exists()


def test_doctor_reports_exact_tools_and_redacts_bounded_connection_errors(tmp_path, monkeypatch):
    """Regression: doctor leaks an upstream token or claims a partial native toolset."""
    package = build_feature_pack(REPO_ROOT, tmp_path / "package")
    home = tmp_path / "home"
    install_feature_pack(package, home)
    monkeypatch.setenv("HERMES_HOME", str(home))

    report = doctor_feature_pack(home, connection_probe=lambda: RuntimeError("Bearer " + "x" * 400))
    assert report["compatible"] is True
    assert report["tools"] == ["rhythm_complete_task", "rhythm_get_dashboard", "rhythm_list_tasks"]
    assert report["connection"]["status"] == "unavailable"
    assert "x" * 20 not in report["connection"]["error"]
    assert len(report["connection"]["error"]) <= 160


def test_lifecycle_rejects_symlinked_home_target_and_package(tmp_path):
    """No install, rollback, or uninstall path may traverse a caller-controlled symlink."""
    package = build_feature_pack(REPO_ROOT, tmp_path / "package")
    real_home = tmp_path / "real-home"
    real_home.mkdir()
    linked_home = tmp_path / "linked-home"
    linked_home.symlink_to(real_home, target_is_directory=True)
    with pytest.raises(PackagingGateError):
        install_feature_pack(package, linked_home)

    home = tmp_path / "home"
    outside = tmp_path / "outside"
    outside.mkdir()
    (home / "plugins").mkdir(parents=True)
    (home / "plugins" / "rhythm").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PackagingGateError):
        uninstall_feature_pack(home)

    unsafe_package = tmp_path / "unsafe-package"
    build_feature_pack(REPO_ROOT, unsafe_package)
    declared = unsafe_package / "plugin.yaml"
    declared.unlink()
    declared.symlink_to(REPO_ROOT / "plugins/rhythm/plugin.yaml")
    with pytest.raises(PackagingGateError):
        install_feature_pack(unsafe_package, tmp_path / "other-home")


def test_doctor_uses_installed_manifest_and_redacts_raised_probe_errors(tmp_path):
    package = build_feature_pack(REPO_ROOT, tmp_path / "package")
    home = tmp_path / "home"
    install_feature_pack(package, home)

    def failed_probe():
        raise RuntimeError("Bearer " + "s" * 300)

    report = doctor_feature_pack(home, connection_probe=failed_probe)
    assert report["connection"]["status"] == "unavailable"
    assert "s" * 20 not in report["connection"]["error"]

    manifest_path = home / "plugins/rhythm/packaging/package-manifest.json"
    installed = json.loads(manifest_path.read_text(encoding="utf-8"))
    installed["tools"] = ["rhythm_get_dashboard"]
    manifest_path.write_text(json.dumps(installed), encoding="utf-8")
    tampered = doctor_feature_pack(home)
    assert tampered["compatible"] is False
    assert tampered["tools"] == []


def test_macos_fixture_is_built_from_the_actual_feature_pack(tmp_path):
    """Regression: macOS verification exercises a hand-written archive rather than the build."""
    package = build_feature_pack(REPO_ROOT, tmp_path / "package")
    app, list_asar, read_asar = build_macos_fixture(package, tmp_path / "fixture")
    validate_macos_bundle(app, _manifest(), list_asar=list_asar, read_asar=read_asar)


def test_desktop_build_uses_production_jsx_runtime(tmp_path):
    """Regression: production Hermes exposes jsxDEV as undefined and the page crashes."""
    package = build_feature_pack(REPO_ROOT, tmp_path / "package")
    bundle = (package / "desktop/dist/rhythm.mjs").read_text(encoding="utf-8")
    assert 'react/jsx-dev-runtime' not in bundle
    assert "jsxDEV" not in bundle


def test_nix_directory_plugin_convention_accepts_the_closed_feature_pack():
    """Regression: Nix packaging drifts from Hermes's directory-plugin contract."""
    nix_module = (REPO_ROOT / "nix/moduleCommon.nix").read_text(encoding="utf-8")
    assert _manifest()["platforms"]["nix"] == "directory-plugin via services.hermes.extraPlugins"
    assert "extraPlugins = mkOption" in nix_module
    assert "plugin.yaml and __init__.py" in nix_module


def test_package_gate_accepts_one_self_contained_esm_artifact(tmp_path):
    """Regression: the final bundle drifts from one external-React ESM entry."""
    manifest = _manifest()
    _write_complete_package(tmp_path, manifest)

    validate_package_tree(tmp_path, manifest)


@pytest.mark.parametrize(
    ("relative", "content", "message"),
    [
        ("desktop/dist/chunk-extra.js", "export {};\n", "unexpected desktop artifact"),
        ("desktop/dist/rhythm.mjs", "import './chunk-extra.js';\n", "relative import"),
        ("desktop/dist/rhythm.mjs", "const React = { createElement() {} };\n", "embedded React runtime"),
    ],
)
def test_package_gate_rejects_bundle_drift(tmp_path, relative, content, message):
    """Regression: split chunks or a second React graph ship undetected."""
    manifest = _manifest()
    _write_complete_package(tmp_path, manifest)
    _write(tmp_path, relative, content)

    with pytest.raises(PackagingGateError, match=message):
        validate_package_tree(tmp_path, manifest)


def test_package_gate_requires_enumerated_content_provenance_and_license(tmp_path):
    """Regression: sealed wheels omit Python/data/skill files or their evidence."""
    manifest = _manifest()
    _write_complete_package(tmp_path, manifest)
    (tmp_path / manifest["content"]["python_modules"][0]).unlink()

    with pytest.raises(PackagingGateError, match="missing declared content"):
        validate_package_tree(tmp_path, manifest)


def test_package_gate_rejects_undeclared_content_and_invalid_package_data(tmp_path):
    """Regression: a wheel adds unreviewed data or a package-data glob names no payload."""
    manifest = _manifest()
    _write_complete_package(tmp_path, manifest)
    _write(tmp_path, "dashboard/dist/unreviewed.js", "export {};\n")

    with pytest.raises(PackagingGateError, match="undeclared package content"):
        validate_package_tree(tmp_path, manifest)

    manifest["content"]["package_data"].append("dashboard/theme/*.svg")
    with pytest.raises(PackagingGateError, match="package_data pattern matches no declared content"):
        validate_package_tree(tmp_path, manifest)


def test_package_gate_rejects_incomplete_provenance(tmp_path):
    """Regression: a copied package loses the source transformation record."""
    manifest = _manifest()
    _write_complete_package(tmp_path, manifest)
    _write(tmp_path, manifest["provenance"]["path"], "Source: fixture\nRevision: fixture\n")

    with pytest.raises(PackagingGateError, match="provenance is missing required field: transformation"):
        validate_package_tree(tmp_path, manifest)


def test_macos_gate_inspects_app_asar_and_unpacked_payloads(tmp_path):
    """Regression: macOS validates only one Electron copy and ships a torn app."""
    manifest = _manifest()
    app = tmp_path / "Hermes.app"
    asar = app / "Contents/Resources/app.asar"
    unpacked = app / "Contents/Resources/app.asar.unpacked"
    asar.parent.mkdir(parents=True)
    asar.write_text("archive", encoding="utf-8")
    _write(unpacked, f'{manifest["desktop"]["entry"]}')

    seen: list[Path] = []

    def list_asar(path: Path) -> set[str]:
        seen.append(path)
        return {manifest["desktop"]["entry"]}

    validate_macos_bundle(
        app,
        manifest,
        list_asar=list_asar,
        read_asar=lambda _, __: "export { RhythmPlugin } from '@hermes/plugin-sdk';\n",
    )

    assert seen == [asar]
    assert (unpacked / manifest["desktop"]["entry"]).is_file()


def test_macos_gate_rejects_missing_unpacked_entry(tmp_path):
    """Regression: an archive-only desktop package passes despite runtime lookup failure."""
    manifest = _manifest()
    app = tmp_path / "Hermes.app"
    asar = app / "Contents/Resources/app.asar"
    asar.parent.mkdir(parents=True)
    asar.write_text("archive", encoding="utf-8")
    (app / "Contents/Resources/app.asar.unpacked").mkdir(parents=True)

    with pytest.raises(PackagingGateError, match="app.asar.unpacked"):
        validate_macos_bundle(
            app,
            manifest,
            list_asar=lambda _: {manifest["desktop"]["entry"]},
            read_asar=lambda _, __: "export {};\n",
        )


@pytest.mark.parametrize(
    ("asar_paths", "asar_source", "unpacked_relative", "unpacked_source", "message"),
    [
        ({"desktop/dist/rhythm.mjs", "desktop/dist/chunk-extra.js"}, "export {};\n", None, None, "unexpected desktop artifact"),
        ({"desktop/dist/rhythm.mjs"}, "export {};\n", "desktop/dist/chunk-extra.js", "export {};\n", "unexpected desktop artifact"),
        ({"desktop/dist/rhythm.mjs"}, "import './chunk-extra.js';\n", None, None, "relative import"),
        ({"desktop/dist/rhythm.mjs"}, "export {};\n", None, "const React = { createElement() {} };\n", "embedded React runtime"),
    ],
)
def test_macos_gate_rejects_bundle_drift_in_both_electron_payloads(
    tmp_path, asar_paths, asar_source, unpacked_relative, unpacked_source, message
):
    """Regression: a macOS copy gains chunks, relative imports, or a second React runtime."""
    manifest = _manifest()
    app = tmp_path / "Hermes.app"
    asar = app / "Contents/Resources/app.asar"
    unpacked = app / "Contents/Resources/app.asar.unpacked"
    asar.parent.mkdir(parents=True)
    asar.write_text("archive", encoding="utf-8")
    _write(unpacked, manifest["desktop"]["entry"], unpacked_source or "export {} from 'rhythm-host';\n")
    if unpacked_relative:
        _write(unpacked, unpacked_relative, "export {};\n")

    with pytest.raises(PackagingGateError, match=message):
        validate_macos_bundle(
            app,
            manifest,
            list_asar=lambda _: asar_paths,
            read_asar=lambda _, __: asar_source,
        )


def test_install_and_doctor_fixtures_are_redacted_and_non_destructive():
    """Regression: installer/doctor errors leak bearer/API credentials or mutate installs."""
    fixtures = json.loads((REPO_ROOT / "plugins/rhythm/packaging/install-doctor-fixtures.json").read_text(encoding="utf-8"))

    validate_install_doctor_fixture(fixtures, _manifest())


@pytest.mark.parametrize(
    "leak",
    [
        "Bearer secret-token-123",
        "api_key=abcdefghijklmno",
        "token=abcdefghijklmno",
        "secret=abcdefghijklmno",
        "access_token=abcdefghijklmno",
        "refresh_token=abcdefghijklmno",
        "password=abcdefghijklmno",
    ],
)
def test_install_and_doctor_fixture_gate_rejects_credential_shaped_values(leak):
    """Regression: a new operator message includes a token-shaped diagnostic value."""
    fixtures = {"records": [{"kind": "doctor-error", "operation": "validate", "message": leak}]}

    with pytest.raises(PackagingGateError, match="credential-shaped"):
        validate_install_doctor_fixture(fixtures, _manifest())


@pytest.mark.parametrize("field", ["token", "secret", "access_token", "refresh_token", "db_password", "apiKey", "accessToken", "clientSecret", "authorization"])
def test_install_and_doctor_fixture_gate_rejects_credential_fields(field):
    """Regression: structured diagnostics serialize a credential outside the message text."""
    fixtures = {"records": [{"kind": "doctor-error", "operation": "validate", "message": "safe", field: "abcdefghijklmno"}]}

    with pytest.raises(PackagingGateError, match="credential-shaped"):
        validate_install_doctor_fixture(fixtures, _manifest())


@pytest.mark.parametrize("record", [
    {"kind": "doctor-error", "operation": "validate", "message": "API key label is shown without a value."},
    {"kind": "doctor-error", "operation": "validate", "message": "access_token label is unavailable."},
    {"kind": "doctor-error", "operation": "validate", "message": "password label is unavailable."},
    {"kind": "doctor-error", "operation": "validate", "message": "safe", "label": "refresh_token"},
])
def test_install_and_doctor_fixture_gate_allows_credential_labels_without_values(record):
    """Regression: redaction scanning rejects harmless labels instead of only leaked values."""
    validate_install_doctor_fixture({"records": [record]}, _manifest())


@pytest.mark.parametrize("entry", ["desktop/dist/rhythm.mjs", "dashboard/dist/index.js"])
@pytest.mark.parametrize("source", [
    "import x from 'lucide-react'; export { x };",
    "export { x } from 'https://unapproved.example/x.js';",
    "import('node:fs');",
    "export {}; //# sourceMappingURL=data:application/json;base64,e30=",
    "export {}; //# sourceMappingURL=private.js.map",
    "const config = '.env.local'; export { config };",
    "import { jsxDEV } from 'react/jsx-dev-runtime';",
    'const a = Symbol.for("react.transitional.element"); export { a };',
])
def test_package_gate_rejects_unsafe_code_in_either_bundle(tmp_path, entry, source):
    manifest = _manifest()
    _write_complete_package(tmp_path, manifest)
    _write(tmp_path, entry, source)
    with pytest.raises(PackagingGateError):
        validate_package_tree(tmp_path, manifest)


def test_build_rebuilds_both_bundles_with_only_host_imports_and_no_secret_sources(tmp_path, monkeypatch):
    from plugins.rhythm.packaging.validate import BUNDLE_EXTERNALS, bundle_imports

    sentinel = "must-not-enter-renderer-credential"
    monkeypatch.setenv("RHYTHM_BUILD_SECRET", sentinel)
    package = build_feature_pack(REPO_ROOT, tmp_path / "package")
    desktop = (package / "desktop/dist/rhythm.mjs").read_text()
    dashboard = (package / "dashboard/dist/index.js").read_text()
    assert bundle_imports(desktop) == {"@hermes/plugin-sdk", "react", "react/jsx-runtime"}
    assert bundle_imports(desktop) <= set(BUNDLE_EXTERNALS)
    assert bundle_imports(dashboard) == set()
    assert '__HERMES_PLUGINS__.register("rhythm"' in dashboard
    assert dashboard != (REPO_ROOT / "plugins/rhythm/dashboard/src/index.js").read_text()
    for source in (desktop, dashboard):
        assert sentinel not in source
        assert ".env" not in source
        assert "sourceMappingURL" not in source
        assert "jsxDEV" not in source
    assert not list(package.rglob("*.map"))
    assert not list(package.rglob(".env*"))


def test_build_refuses_to_delete_existing_output_or_plugin_sources(tmp_path):
    output = tmp_path / "package"
    output.mkdir()
    (output / "keep").write_text("untouched")
    for forbidden in (output, REPO_ROOT, REPO_ROOT / "plugins/rhythm"):
        with pytest.raises(PackagingGateError):
            build_feature_pack(REPO_ROOT, forbidden)
    assert (output / "keep").read_text() == "untouched"
