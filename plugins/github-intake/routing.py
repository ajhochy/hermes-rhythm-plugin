from __future__ import annotations

import hashlib
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path


def _load_dep(name: str):
    key = f"github_intake_{name}"
    if key in sys.modules:
        return sys.modules[key]
    path = Path(__file__).parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(key, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


@dataclass
class DispatchIntent:
    route_key: str
    intake_id: str
    repo_full_name: str
    issue_number: int
    action: str


def derive_route_key(record, config) -> str:
    raw = f"{record.repo_full_name}:{record.issue_number}:{record.action}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def build_dispatch_intent(record, config) -> DispatchIntent:
    route_key = derive_route_key(record, config)
    return DispatchIntent(
        route_key=route_key,
        intake_id=record.intake_id,
        repo_full_name=record.repo_full_name,
        issue_number=record.issue_number,
        action=record.action,
    )
