from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
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


SUPPORTED_ACTIONS = frozenset({"opened", "edited", "closed", "reopened"})


class UnsupportedEventAction(Exception):
    pass


class KillSwitchActive(Exception):
    pass


@dataclass
class IngestResult:
    dry_run: bool
    intake_id: str
    outcome: str
    correlation_id: str = ""
    counters: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.correlation_id:
            self.correlation_id = self.intake_id
        if not self.counters:
            self.counters = {self.outcome: 1}


def validate_event_action(action: str) -> None:
    if action not in SUPPORTED_ACTIONS:
        raise UnsupportedEventAction(
            f"Unsupported event action: {action!r}. Supported: {sorted(SUPPORTED_ACTIONS)}"
        )


def ingest(
    event_type: str,
    delivery_id: str,
    signature: str,
    body: bytes,
    config,
    board_dir,
    hcw_adapter,
    secret: str,
    now: datetime,
) -> IngestResult:
    security = _load_dep("security")
    models = _load_dep("models")
    store_mod = _load_dep("store")
    routing = _load_dep("routing")

    if config.kill_switch:
        raise KillSwitchActive("Kill switch is active; processing halted")

    if not security.verify_signature(body=body, signature_header=signature, secret=secret):
        raise ValueError("Invalid webhook signature")

    security.validate_payload_size(body, max_bytes=config.webhook.max_payload_bytes)

    try:
        raw = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON payload: {exc}") from exc

    validate_event_action(raw.get("action", ""))

    payload = models.WebhookPayload.model_validate(raw)

    owner = payload.repository.owner.login
    repo_full_name = payload.repository.full_name

    if not security.check_allowlist(
        owner=owner,
        repo_full_name=repo_full_name,
        allowlist=config.allowlist,
    ):
        raise security.AllowlistViolation(
            f"Repository {repo_full_name!r} is not in the allowlist"
        )

    record = models.CanonicalIntakeRecord.from_webhook(
        payload=payload,
        delivery_id=delivery_id,
        received_at=now,
    )

    intent = routing.build_dispatch_intent(record, config)

    if config.dry_run:
        return IngestResult(
            dry_run=True,
            intake_id=record.intake_id,
            outcome="dry_run",
        )

    store = store_mod.IntakeStore(board_dir=board_dir)
    result = store.put(record)

    if result.outcome == "accepted":
        hcw_adapter.dispatch(intent)

    return IngestResult(
        dry_run=False,
        intake_id=record.intake_id,
        outcome=result.outcome,
    )
