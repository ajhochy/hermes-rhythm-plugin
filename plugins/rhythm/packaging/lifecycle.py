"""Temp-home-safe Rhythm feature-pack install and diagnostics helpers."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Callable

from .validate import PackagingGateError, load_packaging_manifest, validate_package_tree

_STATE = ".rhythm-feature-pack.json"
_BACKUP = ".rhythm-rollback"
_SECRET = re.compile(r"(?:bearer\s+\S+|(?:token|secret|password|api[_-]?key)\s*[:=]\s*\S+)", re.I)
_RESTART_SIGNAL = "hermes gateway restart"


def _target(home: Path) -> Path:
    if not home.is_absolute():
        raise ValueError("feature-pack home must be an explicit absolute temporary home")
    return home / "plugins" / "rhythm"


def _fingerprint(package: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(path for path in package.rglob("*") if path.is_file()):
        digest.update(path.relative_to(package).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _state(target: Path) -> dict:
    path = target / _STATE
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _write_state(target: Path, fingerprint: str) -> None:
    (target / _STATE).write_text(json.dumps({"enabled": False, "fingerprint": fingerprint}, sort_keys=True), encoding="utf-8")


def install_feature_pack(package: Path, home: Path, *, upgrade: bool = False, force_reinstall: bool = False) -> dict:
    """Install only into ``<home>/plugins/rhythm`` and keep it disabled."""
    manifest = load_packaging_manifest(package.parents[1]) if (package.parents[1] / "plugins/rhythm/packaging/package-manifest.json").exists() else json.loads((package / "packaging/package-manifest.json").read_text())
    validate_package_tree(package, manifest)
    target = _target(home)
    fingerprint = _fingerprint(package)
    if target.exists() and not upgrade and not force_reinstall and _state(target).get("fingerprint") == fingerprint:
        return {"status": "unchanged", "enabled": False, "restart_required": False}
    target.parent.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    if target.exists():
        backup = Path(tempfile.mkdtemp(prefix="rhythm-rollback-")) / "previous"
        shutil.copytree(target, backup, ignore=shutil.ignore_patterns(_BACKUP))
        shutil.rmtree(target)
    shutil.copytree(package, target)
    if backup is not None:
        shutil.copytree(backup, target / _BACKUP)
        shutil.rmtree(backup.parent)
    _write_state(target, fingerprint)
    return {"status": "reinstalled" if force_reinstall else "upgraded" if upgrade else "installed", "enabled": False, "restart_required": True, "restart_signal": _RESTART_SIGNAL}


def rollback_feature_pack(home: Path) -> dict:
    target = _target(home)
    backup = target / _BACKUP
    if not backup.is_dir():
        raise PackagingGateError("no Rhythm feature-pack rollback is available")
    with tempfile.TemporaryDirectory(prefix="rhythm-restore-") as temporary:
        previous = Path(temporary) / "previous"
        shutil.copytree(backup, previous)
        shutil.rmtree(target)
        shutil.copytree(previous, target)
    return {"status": "rolled_back", "restart_required": True, "restart_signal": _RESTART_SIGNAL}


def uninstall_feature_pack(home: Path) -> dict:
    target = _target(home)
    if target.exists():
        shutil.rmtree(target)
        return {"status": "uninstalled", "restart_required": True, "restart_signal": _RESTART_SIGNAL}
    return {"status": "absent", "restart_required": False}


def _redact(value: object) -> str:
    text = _SECRET.sub("[redacted]", str(value)).replace("\n", " ")
    return text[:160]


def doctor_feature_pack(home: Path, *, connection_probe: Callable[[], object] | None = None) -> dict:
    """Return bounded, credential-safe compatibility/connection/tool status."""
    target = _target(home)
    compatible = False
    if target.is_dir():
        try:
            manifest = json.loads((target / "packaging/package-manifest.json").read_text(encoding="utf-8"))
            validate_package_tree(target, manifest, allow_install_metadata=True)
            compatible = True
        except (OSError, ValueError, PackagingGateError):
            compatible = False
    connection = {"status": "not_configured"}
    if connection_probe is not None:
        result = connection_probe()
        if isinstance(result, BaseException):
            connection = {"status": "unavailable", "error": _redact(result)}
        else:
            connection = {"status": "ok"}
    from plugins.rhythm.tools import _TOOLS

    return {"compatible": compatible, "connection": connection, "tools": sorted(_TOOLS), "enabled": bool(_state(target).get("enabled", False)) if target.exists() else False}
