from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


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
class AuditEntry:
    event: str
    timestamp: str


class AuditLog:
    def __init__(self, store):
        self._store = store
        self._audits_dir = store._board_dir / "audits"
        self._audits_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, intake_id: str) -> Path:
        return self._audits_dir / f"{intake_id}.jsonl"

    def append(self, intake_id: str, event: str, detail: Dict[str, Any]) -> None:
        entry = {
            "event": event,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
        with open(self._path(intake_id), "a") as f:
            f.write(json.dumps(entry) + "\n")

    def get_entries(self, intake_id: str) -> List[AuditEntry]:
        path = self._path(intake_id)
        if not path.exists():
            return []
        entries = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if line:
                data = json.loads(line)
                entries.append(AuditEntry(
                    event=data.get("event", ""),
                    timestamp=data.get("timestamp", ""),
                ))
        return entries
