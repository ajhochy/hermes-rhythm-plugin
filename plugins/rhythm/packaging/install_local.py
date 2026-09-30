"""Explicit operator-only install of a validated, already-built feature pack."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tarfile
import tempfile

from .validate import PackagingGateError, validate_package_tree


BACKUP_SUFFIX = ".bak-20260918"


def _check_path(path: Path, *, tree: bool = False) -> None:
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise PackagingGateError("install paths must not traverse symlinks")
    if path.exists() and not path.is_dir():
        raise PackagingGateError("install paths must be directories")
    if tree and path.exists() and any(part.is_symlink() for part in path.rglob("*")):
        raise PackagingGateError("install trees must not contain symlinks")


def install_local(package: Path, home: Path) -> None:
    """Copy both loader entries, snapshot once, and leave activation to Hermes."""
    package, home = package.absolute(), home.absolute()
    _check_path(package, tree=True)
    _check_path(home)
    if home == package or home in package.parents or package in home.parents:
        raise PackagingGateError("package and Hermes home must be separate trees")
    manifest = json.loads((package / "packaging/package-manifest.json").read_text(encoding="utf-8"))
    validate_package_tree(package, manifest)
    targets = [home / "plugins/rhythm", home / "desktop-plugins/rhythm"]
    # Validate every destination before any backup or replacement occurs.
    for target in targets:
        _check_path(target, tree=True)
        backup = target.with_name(target.name + BACKUP_SUFFIX)
        _check_path(backup, tree=True)
        if backup.exists() and not (backup / "backup.tar").is_file():
            raise PackagingGateError("existing dated backup is not an inert backup.tar snapshot; preserve it and inspect manually")

    staged: list[tuple[Path, Path]] = []
    replaced: list[tuple[Path, Path]] = []
    try:
        for index, target in enumerate(targets):
            target.parent.mkdir(parents=True, exist_ok=True)
            stage = Path(tempfile.mkdtemp(prefix=".rhythm-stage-", dir=target.parent))
            staged.append((stage, target))
            if index == 0:
                shutil.copytree(package, stage / "payload")
            else:
                (stage / "payload").mkdir()
                shutil.copyfile(package / manifest["desktop"]["entry"], stage / "payload/plugin.js")
        for target in targets:
            backup = target.with_name(target.name + BACKUP_SUFFIX)
            if target.exists() and not backup.exists():
                # A copied plugin.js/plugin.yaml under the watched roots would
                # activate a duplicate plugin. An archive keeps the backup inert.
                with tempfile.TemporaryDirectory(prefix=".rhythm-backup-", dir=target.parent) as temporary:
                    snapshot = Path(temporary) / "snapshot"
                    snapshot.mkdir(mode=0o700)
                    archive_path = snapshot / "backup.tar"
                    with tarfile.open(archive_path, "w") as archive:
                        archive.add(target, arcname="rhythm")
                    archive_path.chmod(0o600)
                    snapshot.rename(backup)
        for stage, target in staged:
            previous = stage / "previous"
            if target.exists():
                target.rename(previous)
            try:
                (stage / "payload").rename(target)
                replaced.append((stage, target))
            except OSError:
                if previous.exists():
                    previous.rename(target)
                raise
    except OSError:
        for stage, target in reversed(replaced):
            shutil.rmtree(target)
            previous = stage / "previous"
            if previous.exists():
                previous.rename(target)
        raise
    finally:
        for stage, _ in staged:
            shutil.rmtree(stage)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--home", type=Path, default=Path.home() / ".hermes")
    args = parser.parse_args()
    install_local(args.package, args.home)
    print(f"Installed validated Rhythm package in {args.home}; config/auth unchanged.")
    print("Run in the same Hermes profile:")
    for command in (
        "hermes plugins doctor rhythm --ci", "hermes doctor",
        "hermes plugins enable rhythm --no-allow-tool-override", "hermes plugins reload rhythm",
    ):
        print(command)
    print("In Hermes Desktop: Settings > Plugins > Rhythm > Enable; fully restart the app/backend after replacement.")
    print("See packaging/LIVE-GATE.md for disable/remove and live verification.")


if __name__ == "__main__":
    main()
