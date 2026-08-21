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


REPO_ROOT = Path(__file__).parents[2]


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
    _write(root, manifest["desktop"]["entry"], "export { RhythmPlugin } from 'rhythm-host';\n")
    _write(root, manifest["licenses"][0]["path"], "MIT License\n")
    _write(root, manifest["provenance"]["path"], "Source: fixture\nRevision: fixture\nTransformation: none\n")


def test_manifest_is_deterministic_and_declares_the_unified_opt_in_tree():
    """Regression: a package silently gains a second install root or mutable plan."""
    manifest = _manifest()

    assert manifest["install"]["root"] == "<HERMES_HOME>/plugins/rhythm"
    assert manifest["install"]["opt_in"] is True
    assert manifest["install"]["operations"] == []
    assert manifest["desktop"]["format"] == "esm"
    assert manifest["desktop"]["artifact_count"] == 1
    assert manifest["content"]["package_data"] == [
        "contracts/*.json",
        "dashboard/manifest.json",
        "dashboard/dist/index.js",
        "skills/rhythm/SKILL.md",
    ]
    assert manifest["release_gate"]["status"] == "pending"


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

    manifest["content"]["package_data"].append("dashboard/*.css")
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
        read_asar=lambda _, __: "export { RhythmPlugin } from 'rhythm-host';\n",
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


@pytest.mark.parametrize("field", ["token", "secret", "access_token", "refresh_token", "db_password"])
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
