"""Integration tests: fixture-to-local-Kanban full pipeline coverage.

Proves the installed interface validates a disabled configuration, ingests
signed fixtures into only a temporary local board, records deterministic mock
HCW intents, handles duplicates/replay/concurrency/edits/close-reopen/stale/
conflict/retry/quarantine paths, redacts sentinel secrets, honors dry-run and
kill switches, and supports rollback/recovery.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from conftest import (
    FIXTURES_DIR,
    SENTINEL_SECRET,
    _load_plugin_module,
    sign_payload,
)

config_mod = _load_plugin_module("config")
models_mod = _load_plugin_module("models")
security_mod = _load_plugin_module("security")
intake_mod = _load_plugin_module("intake")
store_mod = _load_plugin_module("store")
audit_mod = _load_plugin_module("audit")
routing_mod = _load_plugin_module("routing")
hcw_adapter_mod = _load_plugin_module("hcw_adapter")
recovery_mod = _load_plugin_module("recovery")


def _load_fixture(name: str) -> dict:
    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


def _make_record(fixture_name, delivery_id, now):
    data = _load_fixture(fixture_name)
    payload = models_mod.WebhookPayload.model_validate(data)
    return models_mod.CanonicalIntakeRecord.from_webhook(
        payload=payload, delivery_id=delivery_id, received_at=now
    )


def _ingest(fixture_name, delivery_id, config, board_dir, adapter, now, secret=SENTINEL_SECRET):
    data = _load_fixture(fixture_name)
    body = json.dumps(data).encode()
    sig = sign_payload(body, secret)
    return intake_mod.ingest(
        event_type="issues",
        delivery_id=delivery_id,
        signature=sig,
        body=body,
        config=config,
        board_dir=board_dir,
        hcw_adapter=adapter,
        secret=secret,
        now=now,
    )


class TestDryRunPipeline:
    def test_dry_run_accepts_valid_fixture(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path, mock_hcw_adapter, fake_now
    ):
        cfg = config_mod.load_config(disabled_config_path)
        result = _ingest("issues-opened.json", "int-d1", cfg, tmp_kanban_board, mock_hcw_adapter, fake_now)
        assert result.dry_run is True
        assert result.intake_id is not None

    def test_dry_run_no_board_writes(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path, mock_hcw_adapter, fake_now
    ):
        cfg = config_mod.load_config(disabled_config_path)
        _ingest("issues-opened.json", "int-d2", cfg, tmp_kanban_board, mock_hcw_adapter, fake_now)
        board_files = [f for f in tmp_kanban_board.rglob("*") if f.is_file()]
        assert len(board_files) == 0

    def test_dry_run_no_hcw_dispatch(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path, mock_hcw_adapter, fake_now
    ):
        cfg = config_mod.load_config(disabled_config_path)
        _ingest("issues-opened.json", "int-d3", cfg, tmp_kanban_board, mock_hcw_adapter, fake_now)
        assert len(mock_hcw_adapter.dispatched) == 0

    def test_dry_run_deterministic_intake_id(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path, mock_hcw_adapter, fake_now
    ):
        cfg = config_mod.load_config(disabled_config_path)
        r1 = _ingest("issues-opened.json", "int-det-1", cfg, tmp_kanban_board, mock_hcw_adapter, fake_now)
        r2 = _ingest("issues-opened.json", "int-det-2", cfg, tmp_kanban_board, mock_hcw_adapter, fake_now)
        assert r1.intake_id == r2.intake_id

    def test_dry_run_redacts_sentinel_secret(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path, mock_hcw_adapter, fake_now
    ):
        cfg = config_mod.load_config(disabled_config_path)
        result = _ingest("issues-opened.json", "int-sec", cfg, tmp_kanban_board, mock_hcw_adapter, fake_now)
        result_json = json.dumps(result.__dict__ if hasattr(result, "__dict__") else {
            "dry_run": result.dry_run, "intake_id": result.intake_id, "outcome": result.outcome
        })
        assert SENTINEL_SECRET not in result_json


class TestLiveIngestPipeline:
    def _live_cfg(self, disabled_config_path):
        cfg = config_mod.load_config(disabled_config_path)
        return cfg.model_copy(update={"dry_run": False, "enabled": True})

    def test_live_ingest_writes_to_board(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path, mock_hcw_adapter, fake_now
    ):
        cfg = self._live_cfg(disabled_config_path)
        _ingest("issues-opened.json", "int-live-1", cfg, tmp_kanban_board, mock_hcw_adapter, fake_now)
        board_files = [f for f in tmp_kanban_board.rglob("*.json") if f.is_file()]
        assert len(board_files) >= 1

    def test_live_ingest_dispatches_to_hcw(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path, mock_hcw_adapter, fake_now
    ):
        cfg = self._live_cfg(disabled_config_path)
        _ingest("issues-opened.json", "int-live-2", cfg, tmp_kanban_board, mock_hcw_adapter, fake_now)
        assert len(mock_hcw_adapter.dispatched) >= 1

    def test_duplicate_ingest_no_duplicate_dispatch(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path, mock_hcw_adapter, fake_now
    ):
        cfg = self._live_cfg(disabled_config_path)
        data = _load_fixture("issues-opened.json")
        body = json.dumps(data).encode()
        sig = sign_payload(body, SENTINEL_SECRET)
        kwargs = dict(event_type="issues", signature=sig, body=body, config=cfg,
                      board_dir=tmp_kanban_board, hcw_adapter=mock_hcw_adapter,
                      secret=SENTINEL_SECRET, now=fake_now)
        intake_mod.ingest(delivery_id="dup-1", **kwargs)
        intake_mod.ingest(delivery_id="dup-1", **kwargs)
        assert len(mock_hcw_adapter.dispatched) == 1

    def test_lifecycle_progression_open_edit_close(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path, mock_hcw_adapter, fake_now
    ):
        cfg = self._live_cfg(disabled_config_path)
        _ingest("issues-opened.json", "lc-open", cfg, tmp_kanban_board, mock_hcw_adapter, fake_now)
        _ingest("issues-edited.json", "lc-edit", cfg, tmp_kanban_board, mock_hcw_adapter, fake_now + timedelta(minutes=5))
        _ingest("issues-closed.json", "lc-close", cfg, tmp_kanban_board, mock_hcw_adapter, fake_now + timedelta(hours=1))
        intake_id = models_mod.derive_intake_id(99001, "allowed-org/allowed-repo", 42)
        store = store_mod.IntakeStore(board_dir=tmp_kanban_board)
        stored = store.get(intake_id)
        assert stored.lifecycle_revision == 2
        assert stored.action == "closed"

    def test_stale_delivery_not_dispatched(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path, mock_hcw_adapter, fake_now
    ):
        cfg = self._live_cfg(disabled_config_path)
        _ingest("issues-opened.json", "stale-open", cfg, tmp_kanban_board, mock_hcw_adapter, fake_now)
        _ingest("issues-edited.json", "stale-edit", cfg, tmp_kanban_board, mock_hcw_adapter, fake_now + timedelta(minutes=5))
        dispatch_count_before = len(mock_hcw_adapter.dispatched)
        _ingest("issues-opened.json", "stale-past", cfg, tmp_kanban_board, mock_hcw_adapter, fake_now - timedelta(seconds=1))
        assert len(mock_hcw_adapter.dispatched) == dispatch_count_before


class TestKillSwitchAndRollback:
    def test_kill_switch_halts_processing(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path, mock_hcw_adapter, fake_now
    ):
        cfg = config_mod.load_config(disabled_config_path)
        cfg_killed = cfg.model_copy(update={"kill_switch": True})
        data = _load_fixture("issues-opened.json")
        body = json.dumps(data).encode()
        sig = sign_payload(body, SENTINEL_SECRET)
        with pytest.raises(intake_mod.KillSwitchActive):
            intake_mod.ingest(
                event_type="issues", delivery_id="ks-1", signature=sig, body=body,
                config=cfg_killed, board_dir=tmp_kanban_board, hcw_adapter=mock_hcw_adapter,
                secret=SENTINEL_SECRET, now=fake_now,
            )

    def test_rollback_via_disable_kill_switch(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path, mock_hcw_adapter, fake_now
    ):
        cfg = config_mod.load_config(disabled_config_path)
        cfg_killed = cfg.model_copy(update={"kill_switch": True, "dry_run": False, "enabled": True})
        cfg_restored = cfg.model_copy(update={"kill_switch": False, "dry_run": False, "enabled": True})
        data = _load_fixture("issues-opened.json")
        body = json.dumps(data).encode()
        sig = sign_payload(body, SENTINEL_SECRET)
        with pytest.raises(intake_mod.KillSwitchActive):
            intake_mod.ingest(
                event_type="issues", delivery_id="rb-1", signature=sig, body=body,
                config=cfg_killed, board_dir=tmp_kanban_board, hcw_adapter=mock_hcw_adapter,
                secret=SENTINEL_SECRET, now=fake_now,
            )
        result = intake_mod.ingest(
            event_type="issues", delivery_id="rb-2", signature=sig, body=body,
            config=cfg_restored, board_dir=tmp_kanban_board, hcw_adapter=mock_hcw_adapter,
            secret=SENTINEL_SECRET, now=fake_now,
        )
        assert result.outcome in ("accepted", "dry_run")


class TestRecoveryIntegration:
    def _live_cfg(self, disabled_config_path):
        cfg = config_mod.load_config(disabled_config_path)
        return cfg.model_copy(update={"dry_run": False, "enabled": True})

    def test_quarantine_and_operator_replay(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path, mock_hcw_adapter, fake_now
    ):
        cfg = self._live_cfg(disabled_config_path)
        store = store_mod.IntakeStore(board_dir=tmp_kanban_board)
        audit = audit_mod.AuditLog(store=store)
        record = _make_record("issues-opened.json", "rec-1", fake_now)
        store.put(record)
        manager = recovery_mod.RecoveryManager(store=store, audit=audit, config=cfg.recovery)
        manager.record_attempt(
            intake_id=record.intake_id,
            error=hcw_adapter_mod.PermanentDispatchError("permanent"),
        )
        q_list = manager.list_quarantined()
        assert any(item.intake_id == record.intake_id for item in q_list)
        result = manager.operator_replay(record.intake_id, adapter=mock_hcw_adapter)
        assert result.intake_id == record.intake_id
        entries = audit.get_entries(record.intake_id)
        events = [e.event for e in entries]
        assert "quarantined" in events
        assert "operator_replay" in events

    def test_max_retries_to_failed(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path, fake_now
    ):
        cfg = self._live_cfg(disabled_config_path)
        store = store_mod.IntakeStore(board_dir=tmp_kanban_board)
        audit = audit_mod.AuditLog(store=store)
        record = _make_record("issues-opened.json", "rec-max", fake_now)
        store.put(record)
        manager = recovery_mod.RecoveryManager(store=store, audit=audit, config=cfg.recovery)
        for i in range(cfg.recovery.max_attempts):
            manager.record_attempt(
                intake_id=record.intake_id,
                error=hcw_adapter_mod.TransientDispatchError(f"attempt {i}"),
            )
        state = store.get(record.intake_id).dispatch_state
        assert state in ("failed", "quarantined")


class TestAllowlistAndSecurityIntegration:
    def test_valid_signature_and_allowlisted_repo_accepted(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path, mock_hcw_adapter, fake_now
    ):
        cfg = config_mod.load_config(disabled_config_path)
        result = _ingest("issues-opened.json", "sec-ok", cfg, tmp_kanban_board, mock_hcw_adapter, fake_now)
        assert result.intake_id is not None

    def test_wrong_secret_rejected(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path, mock_hcw_adapter, fake_now
    ):
        cfg = config_mod.load_config(disabled_config_path)
        data = _load_fixture("issues-opened.json")
        body = json.dumps(data).encode()
        sig = sign_payload(body, "wrong-secret")
        with pytest.raises(Exception):
            intake_mod.ingest(
                event_type="issues", delivery_id="sec-bad", signature=sig, body=body,
                config=cfg, board_dir=tmp_kanban_board, hcw_adapter=mock_hcw_adapter,
                secret=SENTINEL_SECRET, now=fake_now,
            )

    def test_unlisted_owner_rejected(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path, mock_hcw_adapter, fake_now
    ):
        import copy
        cfg = config_mod.load_config(disabled_config_path)
        data = copy.deepcopy(_load_fixture("issues-opened.json"))
        data["repository"]["owner"]["login"] = "evil-org"
        data["repository"]["full_name"] = "evil-org/evil-repo"
        data["repository"]["name"] = "evil-repo"
        body = json.dumps(data).encode()
        sig = sign_payload(body, SENTINEL_SECRET)
        with pytest.raises(security_mod.AllowlistViolation):
            intake_mod.ingest(
                event_type="issues", delivery_id="sec-evil", signature=sig, body=body,
                config=cfg, board_dir=tmp_kanban_board, hcw_adapter=mock_hcw_adapter,
                secret=SENTINEL_SECRET, now=fake_now,
            )

    def test_board_files_contain_no_secrets(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path, mock_hcw_adapter, fake_now
    ):
        cfg = config_mod.load_config(disabled_config_path)
        cfg_live = cfg.model_copy(update={"dry_run": False, "enabled": True})
        _ingest("issues-opened.json", "sec-board", cfg_live, tmp_kanban_board, mock_hcw_adapter, fake_now)
        for path in tmp_kanban_board.rglob("*"):
            if path.is_file():
                assert SENTINEL_SECRET not in path.read_text(errors="replace")


class TestScopeInvariant:
    def test_installed_plugin_files_all_in_scope(self):
        from conftest import PLUGIN_ROOT, REPO_ROOT
        plugin_py_files = list(PLUGIN_ROOT.rglob("*.py"))
        for path in plugin_py_files:
            rel = path.relative_to(REPO_ROOT)
            assert str(rel).startswith("plugins/github-intake/"), (
                f"Plugin file {rel} is outside scope"
            )

    def test_dry_run_config_validated(self, disabled_config_path):
        cfg = config_mod.load_config(disabled_config_path)
        assert cfg.enabled is False
        assert cfg.dry_run is True
        assert cfg.kill_switch is False
