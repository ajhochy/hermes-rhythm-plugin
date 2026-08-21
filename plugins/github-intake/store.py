from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


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
class StoreResult:
    outcome: str
    intake_id: str = ""


class IntakeStore:
    def __init__(self, board_dir: Path):
        self._board_dir = Path(board_dir)
        self._intakes_dir = self._board_dir / "intakes"
        self._intakes_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, intake_id: str) -> Path:
        return self._intakes_dir / f"{intake_id}.json"

    def _write(self, record) -> None:
        data = record.model_dump(mode="json")
        self._path(record.intake_id).write_text(json.dumps(data, indent=2))

    def _read(self, intake_id: str):
        models = _load_dep("models")
        path = self._path(intake_id)
        data = json.loads(path.read_text())
        return models.CanonicalIntakeRecord.model_validate(data)

    def put(self, record) -> StoreResult:
        path = self._path(record.intake_id)

        if not path.exists():
            self._write(record)
            return StoreResult(outcome="accepted", intake_id=record.intake_id)

        stored = self._read(record.intake_id)

        if stored.delivery_id == record.delivery_id:
            return StoreResult(outcome="duplicate", intake_id=record.intake_id)

        if record.provenance.received_at < stored.provenance.received_at:
            return StoreResult(outcome="stale", intake_id=record.intake_id)

        if stored.provenance.payload_digest == record.provenance.payload_digest:
            return StoreResult(outcome="duplicate", intake_id=record.intake_id)

        updated = stored.model_copy(update={
            "delivery_id": record.delivery_id,
            "action": record.action,
            "provenance": record.provenance,
            "state": record.state,
            "lifecycle_revision": stored.lifecycle_revision + 1,
        })
        self._write(updated)
        return StoreResult(outcome="accepted", intake_id=record.intake_id)

    def get(self, intake_id: str):
        return self._read(intake_id)

    def update(self, record) -> None:
        self._write(record)

    def list_all(self):
        models = _load_dep("models")
        results = []
        for path in self._intakes_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                results.append(models.CanonicalIntakeRecord.model_validate(data))
            except Exception:
                pass
        return results
