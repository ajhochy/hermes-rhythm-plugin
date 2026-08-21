"""Pure, local-only validation for the eventual Rhythm package artifact.

This module deliberately accepts a supplied staging directory and an injected
asar lister.  It never creates, installs, removes, signs, notarizes, uploads,
or otherwise mutates a user/plugin/release location.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable


PACKAGING_DIR = Path(__file__).resolve().parent


class PackagingGateError(ValueError):
    """Raised when a deterministic package invariant is not met."""


def load_packaging_manifest(repo_root: Path) -> dict[str, Any]:
    """Load the declarative M9 package plan without discovering any files."""
    path = repo_root / "plugins/rhythm/packaging/package-manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _required_content(manifest: dict[str, Any]) -> list[str]:
    content = manifest["content"]
    return [
        *content["python_modules"],
        *content["assets"],
        *content["skills"],
        manifest["provenance"]["path"],
        *(license_["path"] for license_ in manifest["licenses"]),
    ]


def _ensure_no_bundle_drift(root: Path, manifest: dict[str, Any]) -> None:
    desktop = manifest["desktop"]
    entry = desktop["entry"]
    artifacts = sorted(path.relative_to(root).as_posix() for path in (root / "desktop/dist").rglob("*") if path.is_file())
    if artifacts != [entry]:
        raise PackagingGateError(f"unexpected desktop artifact set: {artifacts!r}; expected [{entry!r}]")

    source = (root / entry).read_text(encoding="utf-8")
    relative_import = re.compile(r"(?:import|export)\s+(?:[^;]*?\s+from\s+)?['\"]\.{1,2}/")
    if relative_import.search(source) or re.search(r"import\s*\(\s*['\"]\.{1,2}/", source):
        raise PackagingGateError("relative import found in the single desktop artifact")
    embedded_react = re.compile(r"react\.(?:production|development)|\b(?:const|let|var)\s+React\s*=|function\s+createElement\s*\(", re.I)
    if embedded_react.search(source):
        raise PackagingGateError("embedded React runtime found in desktop artifact")


def validate_package_tree(root: Path, manifest: dict[str, Any]) -> None:
    """Validate a fully materialized package tree against a fixed manifest."""
    if manifest["install"] != {
        "root": "<HERMES_HOME>/plugins/rhythm",
        "opt_in": True,
        "operations": [],
    }:
        raise PackagingGateError("install plan must remain opt-in and non-destructive")
    desktop = manifest["desktop"]
    if desktop["format"] != "esm" or desktop["artifact_count"] != 1:
        raise PackagingGateError("desktop plan must declare exactly one ESM artifact")
    for relative in _required_content(manifest):
        if not (root / relative).is_file():
            raise PackagingGateError(f"missing declared content: {relative}")
    provenance = (root / manifest["provenance"]["path"]).read_text(encoding="utf-8").lower()
    for field in manifest["provenance"]["required_fields"]:
        if field.lower() not in provenance:
            raise PackagingGateError(f"provenance is missing required field: {field}")
    for license_ in manifest["licenses"]:
        license_text = (root / license_["path"]).read_text(encoding="utf-8")
        if license_["spdx"] == "MIT" and "MIT License" not in license_text:
            raise PackagingGateError(
                f"license evidence does not satisfy {license_['spdx']}: {license_['path']}"
            )
    _ensure_no_bundle_drift(root, manifest)


def validate_macos_bundle(
    app: Path,
    manifest: dict[str, Any],
    *,
    list_asar: Callable[[Path], set[str]],
) -> None:
    """Check both Electron payload copies without invoking platform tooling."""
    if app.name != "Hermes.app" or not app.is_dir():
        raise PackagingGateError("expected a Hermes.app bundle")
    resources = app / "Contents/Resources"
    asar = resources / "app.asar"
    unpacked = resources / "app.asar.unpacked"
    if not asar.is_file():
        raise PackagingGateError("Hermes.app is missing Contents/Resources/app.asar")
    if not unpacked.is_dir():
        raise PackagingGateError("Hermes.app is missing Contents/Resources/app.asar.unpacked")
    entry = manifest["desktop"]["entry"]
    if entry not in list_asar(asar):
        raise PackagingGateError(f"app.asar is missing desktop entry: {entry}")
    if not (unpacked / entry).is_file():
        raise PackagingGateError(f"app.asar.unpacked is missing desktop entry: {entry}")


_CREDENTIAL = re.compile(r"(?:bearer\s+\S{8,}|(?:api[_-]?key|access[_-]?token|password)\s*[:=]\s*\S{8,})", re.I)


def validate_install_doctor_fixture(fixtures: dict[str, Any], manifest: dict[str, Any]) -> None:
    """Keep non-live install/doctor/update records redacted and read-only."""
    if manifest["install"]["root"] != "<HERMES_HOME>/plugins/rhythm":
        raise PackagingGateError("fixture root does not match the unified plugin tree")
    for record in fixtures.get("records", []):
        message = record.get("message", "")
        if _CREDENTIAL.search(message):
            raise PackagingGateError("credential-shaped value found in installer/doctor fixture")
        if record.get("operation") not in {"validate", "report"}:
            raise PackagingGateError("installer/doctor fixture must not model a mutating operation")
