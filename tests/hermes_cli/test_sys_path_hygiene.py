"""The `tests/` directory must never be on sys.path.

`tests/` is a proper package (it has __init__.py) and holds subpackages whose
names collide with real importable ones: `acp`, `acp_adapter`, `state`,
`skills`, `dashboard`, `hermes_state`, `scripts`. If `tests/` ever lands on
sys.path, a bare `import acp` resolves to `tests/acp` for the REST of the
session -- and `tests/acp` has no `schema` submodule, so
`acp_adapter.tools`'s `from acp.schema import ...` dies with
ModuleNotFoundError.

That is exactly what happened: `test_web_server_host_header.py` inserted
`Path(__file__).resolve().parents[1]` (the `tests/` dir) when it meant
`parents[2]` (the repo root), and `test_kanban_review_surfaces` failed only
in a full run, never alone.

Nothing needs `tests/` on sys.path -- tests/conftest.py already inserts the
project root.
"""
from __future__ import annotations

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = TESTS_DIR.parent


def test_tests_dir_is_not_on_sys_path():
    entries = {Path(p).resolve() for p in sys.path if p}
    assert TESTS_DIR not in entries, (
        f"{TESTS_DIR} is on sys.path; it shadows real packages such as "
        f"'acp'. Something inserted parents[1] where it meant parents[2]. "
        f"sys.path = {sys.path}"
    )


def test_project_root_is_on_sys_path():
    """The thing callers actually want is already provided by conftest."""
    entries = {Path(p).resolve() for p in sys.path if p}
    assert PROJECT_ROOT in entries


def test_bare_acp_import_resolves_to_the_real_package():
    """The concrete symptom, asserted directly."""
    import acp
    import acp.schema  # noqa: F401
    assert "site-packages" in str(Path(acp.__file__).resolve()) or \
        Path(acp.__file__).resolve().parents[1] != TESTS_DIR
