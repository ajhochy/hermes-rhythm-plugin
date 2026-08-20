from __future__ import annotations

import hashlib
import re
from pathlib import Path

MAX_EVIDENCE = 4096
SECRET = re.compile(r"(?i)(?:api[_-]?key|token|password|secret)\s*(?:=|:|\s)\s*[^\s]+|-----BEGIN [A-Z ]*PRIVATE KEY-----")


def redact(value: str) -> str:
    value = SECRET.sub("[REDACTED]", value).replace(str(Path.home()), "[HOME]")
    return value[:MAX_EVIDENCE]


def safe_relative(root: Path, candidate: str | Path) -> Path:
    path = Path(candidate)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("path_scope_violation")
    resolved_root = root.resolve()
    resolved = (root / path).resolve()
    if resolved_root != resolved and resolved_root not in resolved.parents:
        raise ValueError("path_scope_violation")
    return resolved.relative_to(resolved_root)


def digest_json(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
