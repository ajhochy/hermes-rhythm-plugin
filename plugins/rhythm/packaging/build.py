"""Deterministic local builder for the self-contained Rhythm feature pack.

The builder has no network, signing, install, or release side effects.  It
materializes an explicitly supplied staging directory from the source tree.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from .validate import BUNDLE_EXTERNALS, PackagingGateError, load_packaging_manifest, validate_package_tree


def _copy_declared(source: Path, output: Path, manifest: dict) -> None:
    content = manifest["content"]
    paths = [*content["python_modules"], *content["assets"], *content["skills"], manifest["provenance"]["path"], *(item["path"] for item in manifest["licenses"])]
    for relative in paths:
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)


def _desktop_entry(source: Path, work: Path) -> Path:
    """Prepare the accepted workspace artifact as the bundle input.

    The accepted vendor artifact already contains ``lucide-react``;
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


def _build_bundle(entry: Path, target: Path, work: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    metadata = work / "bundle-meta.json"
    command = [
        "bun", "build", str(entry), "--outfile", str(target), "--format=esm",
        "--target=browser", "--minify", "--production", "--sourcemap=none",
        "--env=disable", f"--metafile={metadata}",
    ]
    for external in BUNDLE_EXTERNALS:
        command.extend(["--external", external])
    # Run outside the checkout: Bun must never load a developer's .env/bunfig.
    result = subprocess.run(command, cwd=work, capture_output=True, text=True, check=False)
    if result.returncode:
        raise PackagingGateError(f"feature-pack build failed: {result.stderr.strip()[:400]}")
    graph = json.loads(metadata.read_text(encoding="utf-8"))
    for name in graph["inputs"]:
        if re.search(r"(?:^|/)node_modules/(?:react|react-dom)(?:/|$)", name):
            raise PackagingGateError("embedded React runtime found in build graph")
    for bundle in graph["outputs"].values():
        for dependency in bundle.get("imports", []):
            if not dependency.get("external") or dependency["path"] not in BUNDLE_EXTERNALS:
                raise PackagingGateError("unexpected dependency in build graph")


def _build_desktop(source: Path, output: Path, entry_relative: str) -> None:
    with tempfile.TemporaryDirectory(prefix="rhythm-build-") as temporary:
        work = Path(temporary)
        entry = _desktop_entry(source, work)
        _build_bundle(entry, output / entry_relative, work)


def _build_dashboard(source: Path, output: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="rhythm-dashboard-build-") as temporary:
        work = Path(temporary)
        entry = work / "entry.js"
        shutil.copyfile(source / "dashboard/src/index.js", entry)
        _build_bundle(entry, output / "dashboard/dist/index.js", work)


def build_feature_pack(repo_root: Path, output: Path) -> Path:
    """Build a closed Rhythm package into an empty caller-owned directory."""
    repo_root = repo_root.resolve()
    source = repo_root / "plugins/rhythm"
    # A typo must never turn the builder's cleanup into a source-tree deletion.
    if output.is_symlink():
        raise PackagingGateError("build output must not be a symlink")
    output = output.resolve()
    if output == repo_root or output in repo_root.parents or source == output or source in output.parents:
        raise PackagingGateError("build output must be outside the plugin source tree")
    manifest = load_packaging_manifest(repo_root)
    if output.exists():
        if any(output.iterdir()):
            raise PackagingGateError("build output must be empty; choose a fresh staging directory")
    output.mkdir(parents=True, exist_ok=True)
    _copy_declared(source, output, manifest)
    _build_desktop(source, output, manifest["desktop"]["entry"])
    _build_dashboard(source, output)
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Empty staging directory (never a Hermes home)")
    args = parser.parse_args()
    package = build_feature_pack(Path(__file__).resolve().parents[3], args.output)
    for relative in ("desktop/dist/rhythm.mjs", "dashboard/dist/index.js"):
        print(f"{relative}: {(package / relative).stat().st_size} bytes")
    print("Allowed externals: " + ", ".join(BUNDLE_EXTERNALS))
    print(f"Validated package: {package}")
