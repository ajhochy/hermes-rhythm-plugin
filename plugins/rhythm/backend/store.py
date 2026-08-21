"""Profile-scoped Rhythm credentials using Hermes's protected auth store."""

from __future__ import annotations

import os
import re
from typing import Any

_PROFILE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def _profile_home():
    from hermes_constants import get_hermes_home

    home = get_hermes_home().resolve()
    # A supplied profile path must be a normal, non-traversing profile segment.
    # Default custom HERMES_HOME remains valid for embeddings/tests.
    parts = home.parts
    if "profiles" in parts:
        idx = parts.index("profiles")
        if len(parts) != idx + 2 or not _PROFILE_SEGMENT.fullmatch(parts[-1]):
            raise ValueError("invalid_profile")
    return home


def _load() -> dict[str, Any]:
    _profile_home()
    from hermes_cli.auth import _load_auth_store
    value = _load_auth_store()
    return value if isinstance(value, dict) else {}


def connection() -> dict[str, Any] | None:
    data = _load().get("rhythm")
    if not isinstance(data, dict) or not isinstance(data.get("access_token"), str):
        return None
    return data


def save(access_token: str, identity: dict[str, str], workspace: dict[str, str]) -> None:
    _profile_home()
    from hermes_cli.auth import _auth_store_lock, _load_auth_store, _save_auth_store
    with _auth_store_lock():
        data = _load_auth_store()
        if not isinstance(data, dict):
            data = {}
        data["rhythm"] = {"access_token": access_token, "identity": identity, "workspace": workspace}
        _save_auth_store(data)
    # auth's writer normally handles this; make the privacy invariant explicit.
    try:
        os.chmod(_profile_home() / "auth.json", 0o600)
    except OSError:
        pass


def delete() -> bool:
    _profile_home()
    from hermes_cli.auth import _auth_store_lock, _load_auth_store, _save_auth_store
    with _auth_store_lock():
        data = _load_auth_store()
        if not isinstance(data, dict) or "rhythm" not in data:
            return False
        data.pop("rhythm", None)
        _save_auth_store(data)
    return True
