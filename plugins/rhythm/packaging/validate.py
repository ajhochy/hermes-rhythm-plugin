"""Pure, local-only validation for the eventual Rhythm package artifact.

This module deliberately accepts a supplied staging directory and an injected
asar lister.  It never creates, installs, removes, signs, notarizes, uploads,
or otherwise mutates a user/plugin/release location.
"""

from __future__ import annotations

import json
import re
from fnmatch import fnmatch
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


def _validate_package_data(manifest: dict[str, Any]) -> None:
    content = manifest["content"]
    declared_data = [*content["assets"], *content["skills"]]
    covered: list[str] = []
    for pattern in content["package_data"]:
        matches = [path for path in declared_data if fnmatch(path, pattern)]
        if not matches:
            raise PackagingGateError(f"package_data pattern matches no declared content: {pattern}")
        covered.extend(matches)
    if len(covered) != len(set(covered)):
        raise PackagingGateError("package_data patterns must not overlap")
    if set(covered) != set(declared_data):
        raise PackagingGateError("package_data must declare every packaged asset and skill exactly once")


def _ensure_single_desktop_artifact(
    artifacts: list[str], entry: str, read_source: Callable[[str], str]
) -> None:
    if artifacts != [entry]:
        raise PackagingGateError(f"unexpected desktop artifact set: {artifacts!r}; expected [{entry!r}]")
    source = read_source(entry)
    relative_import = re.compile(r"(?:import|export)\s+(?:[^;]*?\s+from\s+)?['\"]\.{1,2}/")
    if relative_import.search(source) or re.search(r"import\s*\(\s*['\"]\.{1,2}/", source):
        raise PackagingGateError("relative import found in the single desktop artifact")
    embedded_react = re.compile(r"react\.(?:production|development)|\b(?:const|let|var)\s+React\s*=|function\s+createElement\s*\(", re.I)
    if embedded_react.search(source):
        raise PackagingGateError("embedded React runtime found in desktop artifact")


def _ensure_no_bundle_drift(root: Path, manifest: dict[str, Any]) -> None:
    desktop = manifest["desktop"]
    entry = desktop["entry"]
    artifacts = sorted(path.relative_to(root).as_posix() for path in (root / "desktop/dist").rglob("*") if path.is_file())
    _ensure_single_desktop_artifact(artifacts, entry, lambda path: (root / path).read_text(encoding="utf-8"))


def validate_package_tree(root: Path, manifest: dict[str, Any], *, allow_install_metadata: bool = False) -> None:
    """Validate a fully materialized package tree against a fixed manifest."""
    if root.is_symlink() or any(path.is_symlink() for path in root.rglob("*")):
        raise PackagingGateError("package tree must not contain symlinks")
    install = manifest["install"]
    if install.get("root") != "<HERMES_HOME>/plugins/rhythm" or install.get("opt_in") is not True or install.get("operations") != ["install", "upgrade", "force-reinstall", "rollback", "uninstall"]:
        raise PackagingGateError("install plan must remain opt-in and non-destructive")
    desktop = manifest["desktop"]
    if desktop["format"] != "esm" or desktop["artifact_count"] != 1 or not desktop["entry"].endswith(".mjs"):
        raise PackagingGateError("desktop plan must declare exactly one ESM artifact")
    _validate_package_data(manifest)
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
    declared = set(_required_content(manifest)) | {desktop["entry"]}
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    extra = actual - declared
    if allow_install_metadata:
        extra = {path for path in extra if not path.startswith(".rhythm-")}
    if extra:
        raise PackagingGateError(f"undeclared package content: {sorted(extra)!r}")


def validate_macos_bundle(
    app: Path,
    manifest: dict[str, Any],
    *,
    list_asar: Callable[[Path], set[str]],
    read_asar: Callable[[Path, str], str],
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
    asar_desktop = sorted(path for path in list_asar(asar) if path.startswith("desktop/dist/"))
    if entry not in asar_desktop:
        raise PackagingGateError(f"app.asar is missing desktop entry: {entry}")
    _ensure_single_desktop_artifact(asar_desktop, entry, lambda path: read_asar(asar, path))
    unpacked_desktop = sorted(
        path.relative_to(unpacked).as_posix() for path in (unpacked / "desktop/dist").rglob("*") if path.is_file()
    )
    if entry not in unpacked_desktop:
        raise PackagingGateError(f"app.asar.unpacked is missing desktop entry: {entry}")
    _ensure_single_desktop_artifact(
        unpacked_desktop, entry, lambda path: (unpacked / path).read_text(encoding="utf-8")
    )


_CREDENTIAL = re.compile(
    r"(?:\bbearer\s+\S+|\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password)\s*[:=]\s*\S+)",
    re.I,
)
_CREDENTIAL_FIELD = re.compile(
    r"(?:^|[_-])(?:api[_-]?key|access[_-]?token|refresh[_-]?token|authorization|token|secret|password)(?:[_-]|$)",
    re.I,
)


def _credential_field_name(key: object) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", str(key)).lower()


def _has_credential_field(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            (_CREDENTIAL_FIELD.search(_credential_field_name(key)) and isinstance(item, str) and bool(item.strip()))
            or _has_credential_field(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_has_credential_field(item) for item in value)
    return False


def validate_install_doctor_fixture(fixtures: dict[str, Any], manifest: dict[str, Any]) -> None:
    """Keep non-live install/doctor/update records redacted and read-only."""
    if manifest["install"]["root"] != "<HERMES_HOME>/plugins/rhythm":
        raise PackagingGateError("fixture root does not match the unified plugin tree")
    for record in fixtures.get("records", []):
        message = record.get("message", "")
        if _CREDENTIAL.search(message) or _has_credential_field(record):
            raise PackagingGateError("credential-shaped value found in installer/doctor fixture")
        if record.get("operation") not in {"validate", "report"}:
            raise PackagingGateError("installer/doctor fixture must not model a mutating operation")
