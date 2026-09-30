"""Hermetic test fixtures for the github-intake plugin.

Invariants:
- Temporary HERMES_HOME per test — no real ~/.hermes access.
- Temporary local Kanban board directory — no real board writes.
- Fake clock — deterministic timestamps.
- Mock HCW adapter — no network or real HCW dispatch.
- No credentials in environment — no secret leakage.
"""

import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_plugin_module(name: str):
    """Load a module from the plugin root by filename (handles hyphenated dir)."""
    key = f"github_intake_{name}"
    if key in sys.modules:
        return sys.modules[key]
    path = PLUGIN_ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(key, path)
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError(
            f"Cannot find plugin module '{name}' at {path}. "
            "Has the plugin been implemented yet?"
        )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_plugin_package():
    """Load the github-intake package __init__.py."""
    path = PLUGIN_ROOT / "__init__.py"
    spec = importlib.util.spec_from_file_location("github_intake", path)
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError(
            f"Cannot find plugin __init__.py at {path}."
        )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_fixture(name: str) -> dict:
    path = FIXTURES_DIR / name
    with open(path) as f:
        return json.load(f)


# ── Canonical HMAC signing helper ───────────────────────────────────────────

SENTINEL_SECRET = "test-webhook-secret-REDACT-ME"  # noqa: S105 (test fixture)


def sign_payload(body: bytes, secret: str = SENTINEL_SECRET) -> str:
    import hmac as _hmac
    sig = _hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def tmp_hermes_home(tmp_path):
    """Isolated HERMES_HOME — no real ~/.hermes access."""
    home = tmp_path / "hermes-home"
    home.mkdir()
    old = os.environ.get("HERMES_HOME")
    os.environ["HERMES_HOME"] = str(home)
    yield home
    if old is None:
        os.environ.pop("HERMES_HOME", None)
    else:
        os.environ["HERMES_HOME"] = old


@pytest.fixture()
def tmp_kanban_board(tmp_path):
    """Temporary local Kanban board directory."""
    board = tmp_path / "kanban-board"
    board.mkdir()
    return board


@pytest.fixture()
def fake_now():
    """Fixed UTC timestamp for deterministic tests."""
    return datetime(2026, 8, 21, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def mock_hcw_adapter():
    """Mock HCW adapter — records dispatch intents without network."""
    adapter = MagicMock()
    adapter.dispatched = []

    def _record(intent):
        adapter.dispatched.append(intent)
        return {"status": "recorded", "intent": intent}

    adapter.dispatch = MagicMock(side_effect=_record)
    adapter.is_dry_run = True
    return adapter


@pytest.fixture()
def webhook_secret(tmp_hermes_home):
    """Sentinel webhook secret injected via env (not real secret)."""
    old = os.environ.get("GITHUB_INTAKE_WEBHOOK_SECRET")
    os.environ["GITHUB_INTAKE_WEBHOOK_SECRET"] = SENTINEL_SECRET
    yield SENTINEL_SECRET
    if old is None:
        os.environ.pop("GITHUB_INTAKE_WEBHOOK_SECRET", None)
    else:
        os.environ["GITHUB_INTAKE_WEBHOOK_SECRET"] = old


@pytest.fixture()
def disabled_config_path():
    return FIXTURES_DIR / "config.disabled.yaml"


@pytest.fixture()
def fixture_opened():
    return load_fixture("issues-opened.json")


@pytest.fixture()
def fixture_edited():
    return load_fixture("issues-edited.json")


@pytest.fixture()
def fixture_closed():
    return load_fixture("issues-closed.json")


@pytest.fixture()
def fixture_reopened():
    return load_fixture("issues-reopened.json")


@pytest.fixture()
def fixture_unsupported():
    return load_fixture("unsupported-event.json")
