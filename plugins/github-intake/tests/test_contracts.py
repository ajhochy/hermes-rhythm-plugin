"""RED contract tests for the github-intake plugin.

These tests define the full behavioral contract of the plugin.
They MUST fail only because the plugin implementation is absent.
"""

import json
from pathlib import Path

import pytest

from conftest import (
    FIXTURES_DIR,
    PLUGIN_ROOT,
    SENTINEL_SECRET,
    _load_plugin_module,
    sign_payload,
)


# ── CONTRACT: Plugin manifest safe defaults ───────────────────────────────────

class TestPluginManifest:
    def test_plugin_yaml_exists(self):
        assert (PLUGIN_ROOT / "plugin.yaml").exists(), "plugin.yaml must exist"

    def test_manifest_enabled_false_by_default(self):
        import yaml
        with open(PLUGIN_ROOT / "plugin.yaml") as f:
            manifest = yaml.safe_load(f)
        assert manifest.get("enabled") is False, "plugin must be disabled by default"

    def test_manifest_dry_run_true_by_default(self):
        import yaml
        with open(PLUGIN_ROOT / "plugin.yaml") as f:
            manifest = yaml.safe_load(f)
        assert manifest.get("dry_run") is True, "dry_run must default to true"


# ── CONTRACT: Configuration ────────────────────────────────────────────────────

class TestConfiguration:
    def test_load_disabled_config(self, disabled_config_path):
        config_mod = _load_plugin_module("config")
        cfg = config_mod.load_config(disabled_config_path)
        assert cfg.enabled is False

    def test_load_disabled_config_dry_run_true(self, disabled_config_path):
        config_mod = _load_plugin_module("config")
        cfg = config_mod.load_config(disabled_config_path)
        assert cfg.dry_run is True

    def test_config_has_kill_switch(self, disabled_config_path):
        config_mod = _load_plugin_module("config")
        cfg = config_mod.load_config(disabled_config_path)
        assert hasattr(cfg, "kill_switch")

    def test_config_has_allowlist_owners(self, disabled_config_path):
        config_mod = _load_plugin_module("config")
        cfg = config_mod.load_config(disabled_config_path)
        assert "allowed-org" in cfg.allowlist.owners

    def test_config_has_allowlist_repos(self, disabled_config_path):
        config_mod = _load_plugin_module("config")
        cfg = config_mod.load_config(disabled_config_path)
        assert "allowed-org/allowed-repo" in cfg.allowlist.repositories

    def test_config_secrets_not_stored_in_config_object(self, disabled_config_path):
        config_mod = _load_plugin_module("config")
        cfg = config_mod.load_config(disabled_config_path)
        assert SENTINEL_SECRET not in repr(cfg)


# ── CONTRACT: Webhook payload model ──────────────────────────────────────────

class TestWebhookModel:
    def test_webhook_payload_model_parses_opened(self, fixture_opened):
        models_mod = _load_plugin_module("models")
        payload = models_mod.WebhookPayload.model_validate(fixture_opened)
        assert payload.action == "opened"
        assert payload.issue.number == 42

    def test_webhook_payload_model_parses_edited(self, fixture_edited):
        models_mod = _load_plugin_module("models")
        payload = models_mod.WebhookPayload.model_validate(fixture_edited)
        assert payload.action == "edited"

    def test_webhook_payload_model_parses_closed(self, fixture_closed):
        models_mod = _load_plugin_module("models")
        payload = models_mod.WebhookPayload.model_validate(fixture_closed)
        assert payload.action == "closed"
        assert payload.issue.state == "closed"

    def test_webhook_payload_model_parses_reopened(self, fixture_reopened):
        models_mod = _load_plugin_module("models")
        payload = models_mod.WebhookPayload.model_validate(fixture_reopened)
        assert payload.action == "reopened"

    def test_canonical_intake_record_has_required_fields(self, fixture_opened, fake_now):
        models_mod = _load_plugin_module("models")
        payload = models_mod.WebhookPayload.model_validate(fixture_opened)
        record = models_mod.CanonicalIntakeRecord.from_webhook(
            payload=payload,
            delivery_id="test-delivery-001",
            received_at=fake_now,
        )
        assert record.intake_id is not None
        assert record.delivery_id == "test-delivery-001"
        assert record.installation_id == 99001
        assert record.repo_full_name == "allowed-org/allowed-repo"
        assert record.issue_number == 42
        assert record.action == "opened"
        assert record.provenance is not None
        assert record.state is not None


# ── CONTRACT: Deterministic identifier ───────────────────────────────────────

class TestDeterministicIdentifier:
    def test_same_input_produces_same_intake_id(self):
        models_mod = _load_plugin_module("models")
        id1 = models_mod.derive_intake_id(
            installation_id=99001,
            repo_full_name="allowed-org/allowed-repo",
            issue_number=42,
        )
        id2 = models_mod.derive_intake_id(
            installation_id=99001,
            repo_full_name="allowed-org/allowed-repo",
            issue_number=42,
        )
        assert id1 == id2

    def test_different_issue_produces_different_intake_id(self):
        models_mod = _load_plugin_module("models")
        id1 = models_mod.derive_intake_id(
            installation_id=99001,
            repo_full_name="allowed-org/allowed-repo",
            issue_number=42,
        )
        id2 = models_mod.derive_intake_id(
            installation_id=99001,
            repo_full_name="allowed-org/allowed-repo",
            issue_number=43,
        )
        assert id1 != id2

    def test_different_repo_produces_different_intake_id(self):
        models_mod = _load_plugin_module("models")
        id1 = models_mod.derive_intake_id(
            installation_id=99001,
            repo_full_name="allowed-org/allowed-repo",
            issue_number=42,
        )
        id2 = models_mod.derive_intake_id(
            installation_id=99001,
            repo_full_name="allowed-org/other-repo",
            issue_number=42,
        )
        assert id1 != id2

    def test_intake_id_is_hex_string(self):
        models_mod = _load_plugin_module("models")
        intake_id = models_mod.derive_intake_id(
            installation_id=99001,
            repo_full_name="allowed-org/allowed-repo",
            issue_number=42,
        )
        assert isinstance(intake_id, str)
        int(intake_id, 16)


# ── CONTRACT: HMAC signature verification ────────────────────────────────────

class TestWebhookSecurity:
    def test_valid_signature_passes(self, fixture_opened, webhook_secret):
        security_mod = _load_plugin_module("security")
        body = json.dumps(fixture_opened).encode()
        sig = sign_payload(body, webhook_secret)
        assert security_mod.verify_signature(body=body, signature_header=sig, secret=webhook_secret) is True

    def test_invalid_signature_fails(self, fixture_opened, webhook_secret):
        security_mod = _load_plugin_module("security")
        body = json.dumps(fixture_opened).encode()
        assert security_mod.verify_signature(body=body, signature_header="sha256=deadbeef", secret=webhook_secret) is False

    def test_wrong_secret_fails(self, fixture_opened):
        security_mod = _load_plugin_module("security")
        body = json.dumps(fixture_opened).encode()
        sig = sign_payload(body, "correct-secret")
        assert security_mod.verify_signature(body=body, signature_header=sig, secret="wrong-secret") is False

    def test_oversized_payload_rejected(self):
        security_mod = _load_plugin_module("security")
        max_bytes = 1048576
        with pytest.raises(security_mod.PayloadTooLarge):
            security_mod.validate_payload_size(b"x" * (max_bytes + 1), max_bytes=max_bytes)

    def test_payload_at_limit_accepted(self):
        security_mod = _load_plugin_module("security")
        security_mod.validate_payload_size(b"x" * 1048576, max_bytes=1048576)

    def test_signature_uses_constant_time_comparison(self):
        security_mod = _load_plugin_module("security")
        import inspect
        src = inspect.getsource(security_mod.verify_signature)
        assert "compare_digest" in src

    def test_allowlist_owner_accepted(self, disabled_config_path):
        config_mod = _load_plugin_module("config")
        security_mod = _load_plugin_module("security")
        cfg = config_mod.load_config(disabled_config_path)
        assert security_mod.check_allowlist(
            owner="allowed-org",
            repo_full_name="allowed-org/allowed-repo",
            allowlist=cfg.allowlist,
        ) is True

    def test_disallowed_owner_rejected(self, disabled_config_path):
        config_mod = _load_plugin_module("config")
        security_mod = _load_plugin_module("security")
        cfg = config_mod.load_config(disabled_config_path)
        assert security_mod.check_allowlist(
            owner="evil-org",
            repo_full_name="evil-org/evil-repo",
            allowlist=cfg.allowlist,
        ) is False

    def test_disallowed_repo_rejected(self, disabled_config_path):
        config_mod = _load_plugin_module("config")
        security_mod = _load_plugin_module("security")
        cfg = config_mod.load_config(disabled_config_path)
        assert security_mod.check_allowlist(
            owner="allowed-org",
            repo_full_name="allowed-org/unlisted-repo",
            allowlist=cfg.allowlist,
        ) is False


# ── CONTRACT: Unsupported event rejection ─────────────────────────────────────

class TestUnsupportedEvent:
    def test_unsupported_action_raises(self, fixture_unsupported):
        intake_mod = _load_plugin_module("intake")
        with pytest.raises(intake_mod.UnsupportedEventAction):
            intake_mod.validate_event_action(fixture_unsupported["action"])

    def test_supported_actions_accepted(self):
        intake_mod = _load_plugin_module("intake")
        for action in ("opened", "edited", "closed", "reopened"):
            intake_mod.validate_event_action(action)


# ── CONTRACT: Intake store — idempotent duplicate/replay ─────────────────────

class TestIntakeStore:
    def test_store_new_record(self, tmp_hermes_home, tmp_kanban_board, fixture_opened, fake_now):
        models_mod = _load_plugin_module("models")
        store_mod = _load_plugin_module("store")
        store = store_mod.IntakeStore(board_dir=tmp_kanban_board)
        payload = models_mod.WebhookPayload.model_validate(fixture_opened)
        record = models_mod.CanonicalIntakeRecord.from_webhook(
            payload=payload, delivery_id="delivery-001", received_at=fake_now
        )
        result = store.put(record)
        assert result.outcome == "accepted"

    def test_duplicate_delivery_is_idempotent(self, tmp_hermes_home, tmp_kanban_board, fixture_opened, fake_now):
        models_mod = _load_plugin_module("models")
        store_mod = _load_plugin_module("store")
        store = store_mod.IntakeStore(board_dir=tmp_kanban_board)
        payload = models_mod.WebhookPayload.model_validate(fixture_opened)
        record = models_mod.CanonicalIntakeRecord.from_webhook(
            payload=payload, delivery_id="delivery-001", received_at=fake_now
        )
        store.put(record)
        result = store.put(record)
        assert result.outcome == "duplicate"

    def test_replay_same_delivery_id_is_idempotent(self, tmp_hermes_home, tmp_kanban_board, fixture_opened, fake_now):
        models_mod = _load_plugin_module("models")
        store_mod = _load_plugin_module("store")
        store = store_mod.IntakeStore(board_dir=tmp_kanban_board)
        payload = models_mod.WebhookPayload.model_validate(fixture_opened)
        record = models_mod.CanonicalIntakeRecord.from_webhook(
            payload=payload, delivery_id="delivery-replay", received_at=fake_now
        )
        store.put(record)
        record2 = models_mod.CanonicalIntakeRecord.from_webhook(
            payload=payload, delivery_id="delivery-replay", received_at=fake_now
        )
        result = store.put(record2)
        assert result.outcome in ("duplicate", "replayed")

    def test_store_persists_delivery_id(self, tmp_hermes_home, tmp_kanban_board, fixture_opened, fake_now):
        models_mod = _load_plugin_module("models")
        store_mod = _load_plugin_module("store")
        store = store_mod.IntakeStore(board_dir=tmp_kanban_board)
        payload = models_mod.WebhookPayload.model_validate(fixture_opened)
        record = models_mod.CanonicalIntakeRecord.from_webhook(
            payload=payload, delivery_id="delivery-persist", received_at=fake_now
        )
        store.put(record)
        retrieved = store.get(record.intake_id)
        assert retrieved.delivery_id == "delivery-persist"

    def test_store_does_not_contain_secrets(self, tmp_hermes_home, tmp_kanban_board, fixture_opened, fake_now):
        models_mod = _load_plugin_module("models")
        store_mod = _load_plugin_module("store")
        store = store_mod.IntakeStore(board_dir=tmp_kanban_board)
        payload = models_mod.WebhookPayload.model_validate(fixture_opened)
        record = models_mod.CanonicalIntakeRecord.from_webhook(
            payload=payload, delivery_id="delivery-secret-check", received_at=fake_now
        )
        store.put(record)
        for path in tmp_kanban_board.rglob("*"):
            if path.is_file():
                assert SENTINEL_SECRET not in path.read_text(errors="replace")


# ── CONTRACT: Provenance ──────────────────────────────────────────────────────

class TestProvenance:
    def test_record_has_payload_digest(self, fixture_opened, fake_now):
        models_mod = _load_plugin_module("models")
        payload = models_mod.WebhookPayload.model_validate(fixture_opened)
        record = models_mod.CanonicalIntakeRecord.from_webhook(
            payload=payload, delivery_id="delivery-prov", received_at=fake_now
        )
        assert record.provenance.payload_digest is not None
        assert len(record.provenance.payload_digest) == 64

    def test_record_has_source_timestamp(self, fixture_opened, fake_now):
        models_mod = _load_plugin_module("models")
        payload = models_mod.WebhookPayload.model_validate(fixture_opened)
        record = models_mod.CanonicalIntakeRecord.from_webhook(
            payload=payload, delivery_id="delivery-ts", received_at=fake_now
        )
        assert record.provenance.source_timestamp is not None

    def test_record_has_received_timestamp(self, fixture_opened, fake_now):
        models_mod = _load_plugin_module("models")
        payload = models_mod.WebhookPayload.model_validate(fixture_opened)
        record = models_mod.CanonicalIntakeRecord.from_webhook(
            payload=payload, delivery_id="delivery-recv-ts", received_at=fake_now
        )
        assert record.provenance.received_at == fake_now


# ── CONTRACT: Routing ─────────────────────────────────────────────────────────

class TestRouting:
    def test_routing_produces_deterministic_route_key(self, fixture_opened, fake_now, disabled_config_path):
        config_mod = _load_plugin_module("config")
        models_mod = _load_plugin_module("models")
        routing_mod = _load_plugin_module("routing")
        cfg = config_mod.load_config(disabled_config_path)
        payload = models_mod.WebhookPayload.model_validate(fixture_opened)
        record = models_mod.CanonicalIntakeRecord.from_webhook(
            payload=payload, delivery_id="delivery-route", received_at=fake_now
        )
        assert routing_mod.derive_route_key(record, cfg) == routing_mod.derive_route_key(record, cfg)

    def test_routing_does_not_execute_body_text(self):
        import inspect
        routing_mod = _load_plugin_module("routing")
        src = inspect.getsource(routing_mod)
        assert "eval(" not in src
        assert "exec(" not in src

    def test_routing_dispatch_intent_from_allowlisted_metadata_only(
        self, fixture_opened, fake_now, disabled_config_path
    ):
        config_mod = _load_plugin_module("config")
        models_mod = _load_plugin_module("models")
        routing_mod = _load_plugin_module("routing")
        cfg = config_mod.load_config(disabled_config_path)
        payload = models_mod.WebhookPayload.model_validate(fixture_opened)
        record = models_mod.CanonicalIntakeRecord.from_webhook(
            payload=payload, delivery_id="delivery-dispatch", received_at=fake_now
        )
        intent = routing_mod.build_dispatch_intent(record, cfg)
        assert intent.route_key is not None
        assert intent.intake_id == record.intake_id


# ── CONTRACT: Dry-run produces no writes ──────────────────────────────────────

class TestDryRun:
    def test_dry_run_ingest_produces_no_board_files(
        self, tmp_hermes_home, tmp_kanban_board, fixture_opened, fake_now,
        disabled_config_path, mock_hcw_adapter
    ):
        config_mod = _load_plugin_module("config")
        intake_mod = _load_plugin_module("intake")
        cfg = config_mod.load_config(disabled_config_path)
        body = json.dumps(fixture_opened).encode()
        sig = sign_payload(body, SENTINEL_SECRET)
        result = intake_mod.ingest(
            event_type="issues",
            delivery_id="delivery-dry",
            signature=sig,
            body=body,
            config=cfg,
            board_dir=tmp_kanban_board,
            hcw_adapter=mock_hcw_adapter,
            secret=SENTINEL_SECRET,
            now=fake_now,
        )
        assert result.dry_run is True
        board_files = [f for f in tmp_kanban_board.rglob("*") if f.is_file()]
        assert len(board_files) == 0
        assert len(mock_hcw_adapter.dispatched) == 0

    def test_dry_run_result_is_deterministic_by_intake_id(
        self, tmp_hermes_home, tmp_kanban_board, fixture_opened, fake_now,
        disabled_config_path, mock_hcw_adapter
    ):
        config_mod = _load_plugin_module("config")
        intake_mod = _load_plugin_module("intake")
        cfg = config_mod.load_config(disabled_config_path)
        body = json.dumps(fixture_opened).encode()
        sig = sign_payload(body, SENTINEL_SECRET)
        r1 = intake_mod.ingest(
            event_type="issues", delivery_id="d1", signature=sig, body=body,
            config=cfg, board_dir=tmp_kanban_board, hcw_adapter=mock_hcw_adapter,
            secret=SENTINEL_SECRET, now=fake_now,
        )
        r2 = intake_mod.ingest(
            event_type="issues", delivery_id="d2", signature=sig, body=body,
            config=cfg, board_dir=tmp_kanban_board, hcw_adapter=mock_hcw_adapter,
            secret=SENTINEL_SECRET, now=fake_now,
        )
        assert r1.intake_id == r2.intake_id

    def test_dry_run_result_redacts_sentinel_secret(
        self, tmp_hermes_home, tmp_kanban_board, fixture_opened, fake_now,
        disabled_config_path, mock_hcw_adapter
    ):
        config_mod = _load_plugin_module("config")
        intake_mod = _load_plugin_module("intake")
        cfg = config_mod.load_config(disabled_config_path)
        body = json.dumps(fixture_opened).encode()
        sig = sign_payload(body, SENTINEL_SECRET)
        result = intake_mod.ingest(
            event_type="issues", delivery_id="delivery-redact", signature=sig, body=body,
            config=cfg, board_dir=tmp_kanban_board, hcw_adapter=mock_hcw_adapter,
            secret=SENTINEL_SECRET, now=fake_now,
        )
        result_json = json.dumps(result.__dict__ if hasattr(result, "__dict__") else dict(result))
        assert SENTINEL_SECRET not in result_json


# ── CONTRACT: Kill switch halts processing ────────────────────────────────────

class TestKillSwitch:
    def test_kill_switch_raises_on_ingest(
        self, tmp_hermes_home, tmp_kanban_board, fixture_opened, fake_now,
        disabled_config_path, mock_hcw_adapter
    ):
        config_mod = _load_plugin_module("config")
        intake_mod = _load_plugin_module("intake")
        cfg = config_mod.load_config(disabled_config_path)
        try:
            cfg_killed = cfg.model_copy(update={"kill_switch": True})
        except AttributeError:
            import dataclasses
            cfg_killed = dataclasses.replace(cfg, kill_switch=True)
        body = json.dumps(fixture_opened).encode()
        sig = sign_payload(body, SENTINEL_SECRET)
        with pytest.raises(intake_mod.KillSwitchActive):
            intake_mod.ingest(
                event_type="issues", delivery_id="delivery-killed", signature=sig, body=body,
                config=cfg_killed, board_dir=tmp_kanban_board, hcw_adapter=mock_hcw_adapter,
                secret=SENTINEL_SECRET, now=fake_now,
            )


# ── CONTRACT: Audit trail ─────────────────────────────────────────────────────

class TestAuditTrail:
    def test_audit_appends_entry_on_accept(self, tmp_hermes_home, tmp_kanban_board, fixture_opened, fake_now):
        models_mod = _load_plugin_module("models")
        store_mod = _load_plugin_module("store")
        audit_mod = _load_plugin_module("audit")
        store = store_mod.IntakeStore(board_dir=tmp_kanban_board)
        audit = audit_mod.AuditLog(store=store)
        payload = models_mod.WebhookPayload.model_validate(fixture_opened)
        record = models_mod.CanonicalIntakeRecord.from_webhook(
            payload=payload, delivery_id="delivery-audit", received_at=fake_now
        )
        store.put(record)
        audit.append(record.intake_id, event="accepted", detail={})
        entries = audit.get_entries(record.intake_id)
        assert len(entries) >= 1
        assert entries[-1].event == "accepted"

    def test_audit_entries_are_append_only(self, tmp_hermes_home, tmp_kanban_board, fixture_opened, fake_now):
        models_mod = _load_plugin_module("models")
        store_mod = _load_plugin_module("store")
        audit_mod = _load_plugin_module("audit")
        store = store_mod.IntakeStore(board_dir=tmp_kanban_board)
        audit = audit_mod.AuditLog(store=store)
        payload = models_mod.WebhookPayload.model_validate(fixture_opened)
        record = models_mod.CanonicalIntakeRecord.from_webhook(
            payload=payload, delivery_id="delivery-audit-append", received_at=fake_now
        )
        store.put(record)
        audit.append(record.intake_id, event="accepted", detail={})
        audit.append(record.intake_id, event="routed", detail={})
        entries = audit.get_entries(record.intake_id)
        assert len(entries) == 2
        assert entries[0].event == "accepted"
        assert entries[1].event == "routed"

    def test_audit_does_not_store_secrets(self, tmp_hermes_home, tmp_kanban_board, fixture_opened, fake_now):
        models_mod = _load_plugin_module("models")
        store_mod = _load_plugin_module("store")
        audit_mod = _load_plugin_module("audit")
        store = store_mod.IntakeStore(board_dir=tmp_kanban_board)
        audit = audit_mod.AuditLog(store=store)
        payload = models_mod.WebhookPayload.model_validate(fixture_opened)
        record = models_mod.CanonicalIntakeRecord.from_webhook(
            payload=payload, delivery_id="delivery-audit-secret", received_at=fake_now
        )
        store.put(record)
        audit.append(record.intake_id, event="accepted", detail={"secret": SENTINEL_SECRET})
        for path in tmp_kanban_board.rglob("*"):
            if path.is_file():
                assert SENTINEL_SECRET not in path.read_text(errors="replace")
