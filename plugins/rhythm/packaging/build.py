"""Deterministic local builder for the self-contained Rhythm feature pack.

The builder has no network, signing, install, or release side effects.  It
materializes an explicitly supplied staging directory from the source tree.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from .validate import PackagingGateError, load_packaging_manifest, validate_package_tree


def _copy_declared(source: Path, output: Path, manifest: dict) -> None:
    content = manifest["content"]
    paths = [*content["python_modules"], *content["assets"], *content["skills"], manifest["provenance"]["path"], *(item["path"] for item in manifest["licenses"])]
    for relative in paths:
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)


def _desktop_entry(source: Path, work: Path) -> Path:
    """Prepare the accepted workspace artifact as the bundle input.

    Bun resolves and bundles the package's real ``lucide-react`` dependency;
    React and the Hermes SDK remain explicit host externals.  The builder never
    substitutes a second or simplified screen implementation.
    """
    vendor = (source / "desktop/vendor/rhythm-workspace-ui/dist/index.js").read_text(encoding="utf-8")
    (work / "vendor.mjs").write_text(vendor, encoding="utf-8")
    shutil.copyfile(source / "desktop/src/route-state.ts", work / "route-state.ts")
    plugin = (source / "desktop/src/plugin.tsx").read_text(encoding="utf-8")
    plugin = plugin.replace("../vendor/rhythm-workspace-ui/dist/index.js", "./vendor.mjs")
    plugin = plugin.replace("import '../vendor/rhythm-workspace-ui/dist/styles/rhythm.css'\n", "")
    css = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((source / "desktop/vendor/rhythm-workspace-ui/dist/styles").rglob("*.css"))
    )
    # Every imported stylesheet is concatenated above; leave no browser-time
    # relative CSS resolution behind in the single-file artifact.
    css = re.sub(r"^\s*@import\s+[^;]+;\s*$", "", css, flags=re.MULTILINE)
    style = (
        "const __rhythmCss = " + json.dumps(css, ensure_ascii=False, separators=(",", ":")) + ";\n"
        "if (typeof document !== 'undefined' && !document.querySelector('style[data-rhythm-feature-pack]')) {"
        "const style = document.createElement('style'); style.dataset.rhythmFeaturePack = 'true'; style.textContent = __rhythmCss; document.head.append(style);}\n"
    )
    entry = work / "entry.tsx"
    entry.write_text(style + plugin, encoding="utf-8")
    return entry


def _build_desktop(source: Path, output: Path, entry_relative: str) -> None:
    with tempfile.TemporaryDirectory(prefix="rhythm-build-") as temporary:
        entry = _desktop_entry(source, Path(temporary))
        target = output / entry_relative
        target.parent.mkdir(parents=True, exist_ok=True)
        command = [
            "bun", "build", str(entry), "--outfile", str(target), "--format=esm", "--target=browser", "--minify", "--production",
            "--external", "react", "--external", "react-dom", "--external", "react/*",
            "--external", "@hermes/plugin-sdk",
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode:
            raise PackagingGateError(f"desktop feature-pack build failed: {result.stderr.strip()[:400]}")


def build_feature_pack(repo_root: Path, output: Path) -> Path:
    """Build a closed Rhythm package into an empty caller-owned directory."""
    source = repo_root / "plugins/rhythm"
    manifest = load_packaging_manifest(repo_root)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    _copy_declared(source, output, manifest)
    _build_desktop(source, output, manifest["desktop"]["entry"])
    validate_package_tree(output, manifest)
    return output


def build_macos_fixture(package: Path, root: Path) -> tuple[Path, Callable[[Path], set[str]], Callable[[Path, str], str]]:
    """Create a deterministic *unsigned* package fixture for local checks.

    This is intentionally not a release artifact: its ``app.asar`` is a JSON
    fixture consumed by injected readers, while the unpacked payload is a real
    copy.  Codesigning/notarization/stapling remain a separate manual gate.
    """
    app = root / "Hermes.app"
    resources = app / "Contents/Resources"
    unpacked = resources / "app.asar.unpacked"
    shutil.rmtree(root, ignore_errors=True)
    unpacked.mkdir(parents=True)
    archive: dict[str, str] = {}
    for path in package.rglob("*"):
        if path.is_file():
            relative = path.relative_to(package).as_posix()
            archive[relative] = path.read_text(encoding="utf-8")
            target = unpacked / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    asar = resources / "app.asar"
    asar.write_text(json.dumps(archive, sort_keys=True, separators=(",", ":")), encoding="utf-8")

    def list_asar(path: Path) -> set[str]:
        return set(json.loads(path.read_text(encoding="utf-8")))

    def read_asar(path: Path, relative: str) -> str:
        return json.loads(path.read_text(encoding="utf-8"))[relative]

    return app, list_asar, read_asar
