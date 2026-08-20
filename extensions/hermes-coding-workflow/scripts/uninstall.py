"""Disable and remove only Hermes Coding Workflow payloads from an explicit home."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

PLUGINS = ("hcw", "superpowers", "hcw-dashboard")
ROLES = ("dev-planner", "dev-contract", "dev-builder", "dev-spec-reviewer", "dev-quality-reviewer", "dev-verifier", "dev-recorder")
OWNERSHIP_FILE = ".hcw-lifecycle.json"


def _hermes() -> str:
    executable = shutil.which("hermes")
    if not executable:
        raise RuntimeError("Hermes CLI is required for uninstall")
    return executable


def _run(home: Path, args: list[str]) -> None:
    subprocess.run([_hermes(), *args], env={**os.environ, "HERMES_HOME": str(home)}, check=True, text=True, capture_output=True)


def _homes(home: Path) -> list[Path]:
    return [home, *(home / "profiles" / role for role in ROLES if (home / "profiles" / role).is_dir())]


def _remove_tree(target: Path) -> None:
    if not target.exists():
        return
    with tempfile.TemporaryDirectory(prefix=f".{target.name}-remove-", dir=target.parent) as temporary:
        retired = Path(temporary) / target.name
        os.replace(target, retired)
        shutil.rmtree(retired)


def _owned_profiles(home: Path) -> set[str]:
    try:
        value = json.loads((home / OWNERSHIP_FILE).read_text(encoding="utf-8"))
        return set(value.get("created_profiles", [])) if isinstance(value, dict) else set()
    except (OSError, json.JSONDecodeError):
        return set()


def uninstall(home: Path, *, remove_profiles: bool = False) -> int:
    home = Path(home).resolve()
    _hermes()
    homes = _homes(home)
    # Disable first in every profile-local home; only then remove payloads.
    for target_home in homes:
        for plugin in PLUGINS:
            if (target_home / "plugins" / plugin).is_dir():
                _run(target_home, ["plugins", "disable", plugin])
    for target_home in homes:
        for plugin in PLUGINS:
            _remove_tree(target_home / "plugins" / plugin)
        _remove_tree(target_home / "desktop-plugins" / "hcw")
    if remove_profiles:
        for profile in sorted(_owned_profiles(home) & set(ROLES)):
            _run(home, ["profile", "delete", profile, "--yes"])
        (home / OWNERSHIP_FILE).unlink(missing_ok=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-home", required=True)
    parser.add_argument("--remove-profiles", action="store_true", help="remove only role profiles created by this installer")
    args = parser.parse_args()
    return uninstall(Path(args.hermes_home), remove_profiles=args.remove_profiles)


if __name__ == "__main__":
    raise SystemExit(main())
