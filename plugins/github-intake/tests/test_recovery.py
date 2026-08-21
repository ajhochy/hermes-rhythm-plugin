"""RED recovery tests for the github-intake plugin.

Tests retry eligibility, capped exponential backoff, terminal failed/quarantined
states, dead-letter metadata, operator replay, and durable audit correlation.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from conftest import (
    SENTINEL_SECRET,
    _load_plugin_module,
    sign_payload,
)

models_mod = _load_plugin_module("models")
store_mod = _load_plugin_module("store")
recovery_mod = _load_plugin_module("recovery")
routing_mod = _load_plugin_module("routing")
hcw_adapter_mod = _load_plugin_module("hcw_adapter")
audit_mod = _load_plugin_module("audit")
config_mod = _load_plugin_module("config")

FIXTURES_DIR = __import__("conftest").FIXTURES_DIR


def _make_record(fixture_name, delivery_id, now):
    import json as _j
    with open(FIXTURES_DIR / fixture_name) as f:
        data = _j.load(f)
    payload = models_mod.WebhookPayload.model_validate(data)
    return models_mod.CanonicalIntakeRecord.from_webhook(
        payload=payload,
        delivery_id=delivery_id,
        received_at=now,
    )


class TestRetryEligibility:
    def test_transient_error_is_retry_eligible(self):
        exc = hcw_adapter_mod.TransientDispatchError("network timeout")
        assert recovery_mod.is_retry_eligible(exc) is True

    def test_permanent_error_is_not_retry_eligible(self):
        exc = hcw_adapter_mod.PermanentDispatchError("schema validation failed")
        assert recovery_mod.is_retry_eligible(exc) is False

    def test_unknown_error_is_not_retry_eligible(self):
        exc = ValueError("unexpected")
        assert recovery_mod.is_retry_eligible(exc) is False


class TestExponentialBackoff:
    def test_backoff_increases_with_attempt(self, disabled_config_path):
        cfg = config_mod.load_config(disabled_config_path)
        b1 = recovery_mod.compute_backoff(attempt=1, config=cfg.recovery)
        b2 = recovery_mod.compute_backoff(attempt=2, config=cfg.recovery)
        b3 = recovery_mod.compute_backoff(attempt=3, config=cfg.recovery)
        assert b1 < b2 < b3

    def test_backoff_capped_at_max(self, disabled_config_path):
        cfg = config_mod.load_config(disabled_config_path)
        b_high = recovery_mod.compute_backoff(attempt=100, config=cfg.recovery)
        assert b_high <= cfg.recovery.max_backoff_seconds

    def test_backoff_starts_at_base(self, disabled_config_path):
        cfg = config_mod.load_config(disabled_config_path)
        b1 = recovery_mod.compute_backoff(attempt=1, config=cfg.recovery)
        assert b1 >= cfg.recovery.base_backoff_seconds


class TestTerminalStates:
    def test_exceeded_max_attempts_moves_to_failed(
        self, tmp_hermes_home, tmp_kanban_board, fake_now, disabled_config_path
    ):
        cfg = config_mod.load_config(disabled_config_path)
        store = store_mod.IntakeStore(board_dir=tmp_kanban_board)
        audit = audit_mod.AuditLog(store=store)
        record = _make_record("issues-opened.json", "d-maxretry", fake_now)
        store.put(record)

        manager = recovery_mod.RecoveryManager(
            store=store, audit=audit, config=cfg.recovery
        )
        for _ in range(cfg.recovery.max_attempts):
            manager.record_attempt(
                intake_id=record.intake_id,
                error=hcw_adapter_mod.TransientDispatchError("fail"),
            )

        state = store.get(record.intake_id).dispatch_state
        assert state in ("failed", "quarantined")

    def test_permanent_error_immediately_quarantines(
        self, tmp_hermes_home, tmp_kanban_board, fake_now, disabled_config_path
    ):
        cfg = config_mod.load_config(disabled_config_path)
        store = store_mod.IntakeStore(board_dir=tmp_kanban_board)
        audit = audit_mod.AuditLog(store=store)
        record = _make_record("issues-opened.json", "d-permanent", fake_now)
        store.put(record)

        manager = recovery_mod.RecoveryManager(
            store=store, audit=audit, config=cfg.recovery
        )
        manager.record_attempt(
            intake_id=record.intake_id,
            error=hcw_adapter_mod.PermanentDispatchError("invalid schema"),
        )

        state = store.get(record.intake_id).dispatch_state
        assert state == "quarantined"

    def test_quarantined_record_has_dead_letter_metadata(
        self, tmp_hermes_home, tmp_kanban_board, fake_now, disabled_config_path
    ):
        cfg = config_mod.load_config(disabled_config_path)
        store = store_mod.IntakeStore(board_dir=tmp_kanban_board)
        audit = audit_mod.AuditLog(store=store)
        record = _make_record("issues-opened.json", "d-quarantine-meta", fake_now)
        store.put(record)

        manager = recovery_mod.RecoveryManager(
            store=store, audit=audit, config=cfg.recovery
        )
        manager.record_attempt(
            intake_id=record.intake_id,
            error=hcw_adapter_mod.PermanentDispatchError("permanent failure"),
        )

        stored = store.get(record.intake_id)
        assert stored.dead_letter is not None
        assert stored.dead_letter.reason is not None


class TestOperatorReplay:
    def test_operator_replay_from_quarantined(
        self, tmp_hermes_home, tmp_kanban_board, fake_now, disabled_config_path,
        mock_hcw_adapter
    ):
        cfg = config_mod.load_config(disabled_config_path)
        store = store_mod.IntakeStore(board_dir=tmp_kanban_board)
        audit = audit_mod.AuditLog(store=store)
        record = _make_record("issues-opened.json", "d-replay-op", fake_now)
        store.put(record)

        manager = recovery_mod.RecoveryManager(
            store=store, audit=audit, config=cfg.recovery
        )
        manager.record_attempt(
            intake_id=record.intake_id,
            error=hcw_adapter_mod.PermanentDispatchError("first failure"),
        )

        result = manager.operator_replay(record.intake_id, adapter=mock_hcw_adapter)
        assert result is not None
        assert result.intake_id == record.intake_id

    def test_replay_appends_audit_entry(
        self, tmp_hermes_home, tmp_kanban_board, fake_now, disabled_config_path,
        mock_hcw_adapter
    ):
        cfg = config_mod.load_config(disabled_config_path)
        store = store_mod.IntakeStore(board_dir=tmp_kanban_board)
        audit = audit_mod.AuditLog(store=store)
        record = _make_record("issues-opened.json", "d-replay-audit", fake_now)
        store.put(record)

        manager = recovery_mod.RecoveryManager(
            store=store, audit=audit, config=cfg.recovery
        )
        manager.record_attempt(
            intake_id=record.intake_id,
            error=hcw_adapter_mod.PermanentDispatchError("force quarantine"),
        )
        manager.operator_replay(record.intake_id, adapter=mock_hcw_adapter)

        entries = audit.get_entries(record.intake_id)
        events = [e.event for e in entries]
        assert "operator_replay" in events


class TestQuarantineList:
    def test_quarantine_list_returns_quarantined_records(
        self, tmp_hermes_home, tmp_kanban_board, fake_now, disabled_config_path
    ):
        cfg = config_mod.load_config(disabled_config_path)
        store = store_mod.IntakeStore(board_dir=tmp_kanban_board)
        audit = audit_mod.AuditLog(store=store)

        record = _make_record("issues-opened.json", "d-qlist", fake_now)
        store.put(record)

        manager = recovery_mod.RecoveryManager(
            store=store, audit=audit, config=cfg.recovery
        )
        manager.record_attempt(
            intake_id=record.intake_id,
            error=hcw_adapter_mod.PermanentDispatchError("quarantine me"),
        )

        q_list = manager.list_quarantined()
        assert any(item.intake_id == record.intake_id for item in q_list)
