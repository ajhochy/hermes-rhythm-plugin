from __future__ import annotations

import importlib.util
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


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


def is_retry_eligible(exc: Exception) -> bool:
    hcw = _load_dep("hcw_adapter")
    return isinstance(exc, hcw.TransientDispatchError)


def compute_backoff(attempt: int, config) -> float:
    base = config.base_backoff_seconds
    maximum = config.max_backoff_seconds
    value = base * (2 ** (attempt - 1))
    return min(value, maximum)


@dataclass
class OperatorReplayResult:
    intake_id: str


@dataclass
class QuarantineItem:
    intake_id: str
    reason: str


class RecoveryManager:
    def __init__(self, store, audit, config):
        self._store = store
        self._audit = audit
        self._config = config

    def record_attempt(self, intake_id: str, error: Exception) -> None:
        hcw = _load_dep("hcw_adapter")
        stored = self._store.get(intake_id)

        if isinstance(error, hcw.PermanentDispatchError):
            from pydantic import BaseModel
            models = _load_dep("models")
            dead_letter = models.DeadLetterData(
                reason=str(error),
                error_type=type(error).__name__,
            )
            updated = stored.model_copy(update={
                "dispatch_state": "quarantined",
                "dead_letter": dead_letter,
            })
            self._store.update(updated)
            self._audit.append(intake_id, event="quarantined", detail={"reason": str(error)})
            return

        new_count = stored.attempt_count + 1
        if new_count >= self._config.max_attempts:
            models = _load_dep("models")
            dead_letter = models.DeadLetterData(
                reason=f"Max attempts ({self._config.max_attempts}) exceeded: {error}",
                error_type=type(error).__name__,
            )
            updated = stored.model_copy(update={
                "dispatch_state": "failed",
                "dead_letter": dead_letter,
                "attempt_count": new_count,
            })
            self._store.update(updated)
            self._audit.append(intake_id, event="failed", detail={"reason": str(error)})
        else:
            updated = stored.model_copy(update={
                "dispatch_state": "retrying",
                "attempt_count": new_count,
            })
            self._store.update(updated)
            self._audit.append(intake_id, event="retry_attempt", detail={"attempt": new_count})

    def operator_replay(self, intake_id: str, adapter) -> OperatorReplayResult:
        stored = self._store.get(intake_id)
        routing = _load_dep("routing")
        config = None
        intent = routing.DispatchIntent(
            route_key=stored.intake_id[:16],
            intake_id=stored.intake_id,
            repo_full_name=stored.repo_full_name,
            issue_number=stored.issue_number,
            action=stored.action,
        )
        adapter.dispatch(intent)

        updated = stored.model_copy(update={
            "dispatch_state": "replayed",
            "dead_letter": None,
        })
        self._store.update(updated)
        self._audit.append(intake_id, event="operator_replay", detail={"intake_id": intake_id})
        return OperatorReplayResult(intake_id=intake_id)

    def list_quarantined(self) -> List[QuarantineItem]:
        records = self._store.list_all()
        return [
            QuarantineItem(
                intake_id=r.intake_id,
                reason=r.dead_letter.reason if r.dead_letter else "",
            )
            for r in records
            if r.dispatch_state in ("quarantined", "failed")
        ]
