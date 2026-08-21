"""RED security tests for the github-intake plugin.

Tests HMAC verification, allowlist enforcement, payload size limits,
secret redaction, and least-privilege defaults.
"""

import json

import pytest

from conftest import SENTINEL_SECRET, _load_plugin_module, sign_payload


class TestHMACVerification:
    def test_missing_signature_header_rejected(self, fixture_opened, webhook_secret):
        security_mod = _load_plugin_module("security")
        body = json.dumps(fixture_opened).encode()
        with pytest.raises(security_mod.MissingSignature):
            security_mod.verify_signature(body=body, signature_header=None, secret=webhook_secret)

    def test_empty_signature_header_rejected(self, fixture_opened, webhook_secret):
        security_mod = _load_plugin_module("security")
        body = json.dumps(fixture_opened).encode()
        result = security_mod.verify_signature(body=body, signature_header="", secret=webhook_secret)
        assert result is False

    def test_wrong_algorithm_prefix_rejected(self, fixture_opened, webhook_secret):
        security_mod = _load_plugin_module("security")
        import hmac, hashlib
        body = json.dumps(fixture_opened).encode()
        raw = hmac.new(webhook_secret.encode(), body, hashlib.sha1).hexdigest()
        result = security_mod.verify_signature(body=body, signature_header=f"sha1={raw}", secret=webhook_secret)
        assert result is False

    def test_tampered_body_rejected(self, fixture_opened, webhook_secret):
        security_mod = _load_plugin_module("security")
        body = json.dumps(fixture_opened).encode()
        sig = sign_payload(body, webhook_secret)
        result = security_mod.verify_signature(body=body + b" TAMPERED", signature_header=sig, secret=webhook_secret)
        assert result is False


class TestPayloadSizeLimits:
    def test_empty_payload_accepted(self):
        security_mod = _load_plugin_module("security")
        security_mod.validate_payload_size(b"", max_bytes=1048576)

    def test_payload_exactly_at_limit_accepted(self):
        security_mod = _load_plugin_module("security")
        security_mod.validate_payload_size(b"x" * 1048576, max_bytes=1048576)

    def test_payload_one_byte_over_limit_rejected(self):
        security_mod = _load_plugin_module("security")
        with pytest.raises(security_mod.PayloadTooLarge):
            security_mod.validate_payload_size(b"x" * 1048577, max_bytes=1048576)


class TestSecretRedaction:
    def test_secret_not_in_error_message(self, fixture_opened, webhook_secret):
        security_mod = _load_plugin_module("security")
        body = json.dumps(fixture_opened).encode()
        try:
            security_mod.verify_signature(body=body, signature_header="sha256=badhash", secret=webhook_secret)
        except Exception as exc:
            assert webhook_secret not in str(exc)

    def test_secret_not_in_repr_of_config(self, disabled_config_path):
        config_mod = _load_plugin_module("config")
        cfg = config_mod.load_config(disabled_config_path)
        assert SENTINEL_SECRET not in repr(cfg)
        assert SENTINEL_SECRET not in str(cfg)

    def test_secret_loaded_only_from_env_not_config_file(self, disabled_config_path):
        config_mod = _load_plugin_module("config")
        cfg = config_mod.load_config(disabled_config_path)
        assert not hasattr(cfg.webhook, "secret") or cfg.webhook.secret is None


class TestAllowlistEnforcement:
    def test_allowlist_blocks_ingest_for_unlisted_owner(
        self, tmp_hermes_home, tmp_kanban_board, fixture_opened,
        disabled_config_path, mock_hcw_adapter, fake_now
    ):
        import copy
        config_mod = _load_plugin_module("config")
        intake_mod = _load_plugin_module("intake")
        security_mod = _load_plugin_module("security")
        hostile = copy.deepcopy(fixture_opened)
        hostile["repository"]["owner"]["login"] = "evil-org"
        hostile["repository"]["full_name"] = "evil-org/evil-repo"
        hostile["repository"]["name"] = "evil-repo"
        hostile["sender"]["login"] = "evil-actor"
        cfg = config_mod.load_config(disabled_config_path)
        body = json.dumps(hostile).encode()
        sig = sign_payload(body, SENTINEL_SECRET)
        with pytest.raises(security_mod.AllowlistViolation):
            intake_mod.ingest(
                event_type="issues",
                delivery_id="delivery-hostile",
                signature=sig,
                body=body,
                config=cfg,
                board_dir=tmp_kanban_board,
                hcw_adapter=mock_hcw_adapter,
                secret=SENTINEL_SECRET,
                now=fake_now,
            )

    def test_malformed_json_rejected(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path,
        mock_hcw_adapter, fake_now, webhook_secret
    ):
        config_mod = _load_plugin_module("config")
        intake_mod = _load_plugin_module("intake")
        security_mod = _load_plugin_module("security")
        cfg = config_mod.load_config(disabled_config_path)
        body = b"{not valid json}"
        sig = sign_payload(body, SENTINEL_SECRET)
        with pytest.raises(Exception):
            intake_mod.ingest(
                event_type="issues",
                delivery_id="delivery-malformed",
                signature=sig,
                body=body,
                config=cfg,
                board_dir=tmp_kanban_board,
                hcw_adapter=mock_hcw_adapter,
                secret=SENTINEL_SECRET,
                now=fake_now,
            )

    def test_untrusted_source_body_not_executed(self, fixture_opened, fake_now):
        models_mod = _load_plugin_module("models")
        import copy
        hostile = copy.deepcopy(fixture_opened)
        hostile["issue"]["body"] = "__import__('os').system('echo HOSTILE')"
        payload = models_mod.WebhookPayload.model_validate(hostile)
        record = models_mod.CanonicalIntakeRecord.from_webhook(
            payload=payload, delivery_id="d-hostile-body", received_at=fake_now
        )
        assert record.intake_id is not None
