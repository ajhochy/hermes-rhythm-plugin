from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

import pytest


TOKEN = "A" * 43
ORIGIN = "http://127.0.0.1:7361"


def _module():
    import agent.host_capabilities as host_capabilities

    return importlib.reload(host_capabilities)


def _write_handoff(path: Path, payload: object, mode: int = 0o600) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(mode)


def _payload(*, token: str = TOKEN, origin: str = ORIGIN) -> dict:
    return {
        "version": 1,
        "capabilities": {
            "rhythm_bridge": {"token": token, "origin": origin},
        },
    }


def test_hp_1_secure_handoff_is_one_shot(tmp_path, monkeypatch):
    """Regression caught: a capability file remains reusable after startup."""
    module = _module()
    handoff = tmp_path / "handoff.json"
    _write_handoff(handoff, _payload())
    monkeypatch.setenv("HERMES_HOST_CAPABILITIES_FILE", str(handoff))

    module.load_from_handoff()

    assert "HERMES_HOST_CAPABILITIES_FILE" not in os.environ
    assert not handoff.exists()
    assert module.get("rhythm_bridge") == module.HostCapability(TOKEN, ORIGIN)
    assert module.export_for_child() == _payload()["capabilities"]


@pytest.mark.parametrize(
    "case",
    ["symlink", "mode", "owner", "oversize", "bad-json", "bad-origin"],
)
def test_hp_1_rejects_unsafe_handoff_material(tmp_path, monkeypatch, case):
    """Regression caught: an unsafe host-controlled file installs authority."""
    module = _module()
    handoff = tmp_path / "handoff.json"
    target = tmp_path / "target.json"

    if case == "symlink":
        _write_handoff(target, _payload())
        handoff.symlink_to(target)
    elif case == "mode":
        _write_handoff(handoff, _payload(), mode=0o640)
    elif case == "owner":
        _write_handoff(handoff, _payload())
        actual_euid = os.geteuid()
        monkeypatch.setattr(module.os, "geteuid", lambda: actual_euid + 1)
    elif case == "oversize":
        handoff.write_bytes(b" " * 4097)
        handoff.chmod(0o600)
    elif case == "bad-json":
        handoff.write_text("{", encoding="utf-8")
        handoff.chmod(0o600)
    else:
        _write_handoff(handoff, _payload(origin="https://127.0.0.1:7361"))

    monkeypatch.setenv("HERMES_HOST_CAPABILITIES_FILE", str(handoff))
    with pytest.raises(ValueError):
        module.load_from_handoff()

    assert "HERMES_HOST_CAPABILITIES_FILE" not in os.environ
    assert module.get("rhythm_bridge") is None
