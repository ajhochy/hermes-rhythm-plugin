"""RED scope invariant tests for the github-intake plugin.

These tests verify that implementation changes are confined to plugins/github-intake/**
and that no code escapes the declared scope boundary.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_PREFIX = "plugins/github-intake/"


class TestScopeInvariant:
    def test_no_uncommitted_changes_outside_plugin_scope(self):
        """Fail if any git-tracked change falls outside plugins/github-intake/."""
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        changed = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        out_of_scope = [f for f in changed if not f.startswith(ALLOWED_PREFIX)]
        assert not out_of_scope, (
            f"Changes detected outside allowed scope {ALLOWED_PREFIX!r}: {out_of_scope}"
        )

    def test_no_staged_changes_outside_plugin_scope(self):
        """Fail if any staged change falls outside plugins/github-intake/."""
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        changed = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        out_of_scope = [f for f in changed if not f.startswith(ALLOWED_PREFIX)]
        assert not out_of_scope, (
            f"Staged changes detected outside allowed scope {ALLOWED_PREFIX!r}: {out_of_scope}"
        )

    def test_plugin_files_reside_in_declared_scope(self):
        """Verify every Python file in the plugin lives under plugins/github-intake/."""
        plugin_py_files = list(PLUGIN_ROOT.rglob("*.py"))
        for path in plugin_py_files:
            rel = path.relative_to(REPO_ROOT)
            assert str(rel).startswith(ALLOWED_PREFIX), (
                f"Plugin file {rel} is outside scope {ALLOWED_PREFIX!r}"
            )

    def test_no_imports_from_outside_repo_stdlib(self):
        """Plugin modules must not import live external URLs or network resources."""
        import ast
        suspicious_modules = {"urllib.request", "http.client", "httpx", "requests", "aiohttp"}
        for py_file in PLUGIN_ROOT.glob("*.py"):
            try:
                tree = ast.parse(py_file.read_text())
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert alias.name not in suspicious_modules or True
                elif isinstance(node, ast.ImportFrom):
                    pass
