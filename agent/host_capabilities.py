"""One-shot host capabilities delivered by a trusted parent process."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import stat
import threading
from collections.abc import Mapping
from typing import Any


_HANDOFF_ENV = "HERMES_HOST_CAPABILITIES_FILE"
_MAX_HANDOFF_BYTES = 4096
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")
_ORIGIN_RE = re.compile(r"^http://127\.0\.0\.1:([1-9][0-9]{0,4})$")
_lock = threading.RLock()
_capabilities: dict[str, "HostCapability"] = {}
_serving_process = False


@dataclass(frozen=True)
class HostCapability:
    token: str
    origin: str


def _parse_capabilities(value: Any) -> dict[str, HostCapability]:
    if not isinstance(value, Mapping):
        raise ValueError("invalid host capabilities")
    parsed: dict[str, HostCapability] = {}
    for name, raw in value.items():
        if name != "rhythm_bridge" or not isinstance(raw, Mapping) or set(raw) != {"token", "origin"}:
            raise ValueError("invalid host capability")
        token = raw.get("token")
        origin = raw.get("origin")
        if not isinstance(token, str) or _TOKEN_RE.fullmatch(token) is None:
            raise ValueError("invalid host capability token")
        if not isinstance(origin, str) or (match := _ORIGIN_RE.fullmatch(origin)) is None:
            raise ValueError("invalid host capability origin")
        if int(match.group(1)) > 65535:
            raise ValueError("invalid host capability origin")
        parsed[str(name)] = HostCapability(token=token, origin=origin)
    return parsed


def load_from_handoff() -> None:
    """Consume, validate, and unlink the capability file named in the env."""
    path = os.environ.pop(_HANDOFF_ENV, None)
    if not path:
        return
    fd = -1
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, flags)
        except OSError as exc:
            raise ValueError("invalid host capability handoff") from exc
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("invalid host capability handoff")
        if hasattr(os, "geteuid") and info.st_uid != os.geteuid():
            raise ValueError("invalid host capability handoff owner")
        if stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("invalid host capability handoff mode")
        if info.st_size <= 0 or info.st_size > _MAX_HANDOFF_BYTES:
            raise ValueError("invalid host capability handoff size")
        chunks = []
        remaining = _MAX_HANDOFF_BYTES + 1
        while remaining:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) != info.st_size or len(raw) > _MAX_HANDOFF_BYTES:
            raise ValueError("invalid host capability handoff size")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid host capability handoff JSON") from exc
        if not isinstance(payload, Mapping) or set(payload) != {"version", "capabilities"} or payload.get("version") != 1:
            raise ValueError("invalid host capability handoff schema")
        capabilities = _parse_capabilities(payload.get("capabilities"))
        with _lock:
            _capabilities.clear()
            _capabilities.update(capabilities)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def get(name: str) -> HostCapability | None:
    with _lock:
        return _capabilities.get(name)


def export_for_child() -> dict:
    with _lock:
        return {
            name: {"token": capability.token, "origin": capability.origin}
            for name, capability in _capabilities.items()
        }


def install_from_parent(mapping: dict) -> None:
    capabilities = _parse_capabilities(mapping)
    with _lock:
        _capabilities.clear()
        _capabilities.update(capabilities)


def mark_serving_process() -> None:
    global _serving_process
    _serving_process = True


def is_serving_process() -> bool:
    return _serving_process
