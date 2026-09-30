"""RED lifecycle tests for the github-intake plugin.

Tests monotonic lifecycle transitions for opened/edited/closed/reopened
and stale/conflict outcomes under concurrent deliveries.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from conftest import FIXTURES_DIR, _load_plugin_module


def _make_record(fixture_name, delivery_id, now):
    with open(FIXTURES_DIR / fixture_name) as f:
        data = json.load(f)
    models_mod = _load_plugin_module("models")
    payload = models_mod.WebhookPayload.model_validate(data)
    return models_mod.CanonicalIntakeRecord.from_webhook(
        payload=payload,
        delivery_id=delivery_id,
        received_at=now,
    )


class TestIssueLifecycle:
    def test_opened_creates_record_with_revision_0(self, tmp_hermes_home, tmp_kanban_board, fake_now):
        store_mod = _load_plugin_module("store")
        store = store_mod.IntakeStore(board_dir=tmp_kanban_board)
        record = _make_record("issues-opened.json", "d-open-1", fake_now)
        store.put(record)
        stored = store.get(record.intake_id)
        assert stored.lifecycle_revision == 0
        assert stored.action == "opened"

    def test_edit_increments_lifecycle_revision(self, tmp_hermes_home, tmp_kanban_board, fake_now):
        store_mod = _load_plugin_module("store")
        models_mod = _load_plugin_module("models")
        store = store_mod.IntakeStore(board_dir=tmp_kanban_board)
        store.put(_make_record("issues-opened.json", "d-open-2", fake_now))
        store.put(_make_record("issues-edited.json", "d-edit-2", fake_now + timedelta(minutes=5)))
        intake_id = models_mod.derive_intake_id(
            installation_id=99001, repo_full_name="allowed-org/allowed-repo", issue_number=42
        )
        stored = store.get(intake_id)
        assert stored.lifecycle_revision == 1
        assert stored.action == "edited"

    def test_close_increments_revision_past_edit(self, tmp_hermes_home, tmp_kanban_board, fake_now):
        store_mod = _load_plugin_module("store")
        models_mod = _load_plugin_module("models")
        store = store_mod.IntakeStore(board_dir=tmp_kanban_board)
        store.put(_make_record("issues-opened.json", "d-open-3", fake_now))
        store.put(_make_record("issues-edited.json", "d-edit-3", fake_now + timedelta(minutes=5)))
        store.put(_make_record("issues-closed.json", "d-close-3", fake_now + timedelta(hours=1)))
        intake_id = models_mod.derive_intake_id(
            installation_id=99001, repo_full_name="allowed-org/allowed-repo", issue_number=42
        )
        stored = store.get(intake_id)
        assert stored.lifecycle_revision == 2
        assert stored.action == "closed"

    def test_reopen_follows_close(self, tmp_hermes_home, tmp_kanban_board, fake_now):
        store_mod = _load_plugin_module("store")
        models_mod = _load_plugin_module("models")
        store = store_mod.IntakeStore(board_dir=tmp_kanban_board)
        store.put(_make_record("issues-opened.json", "d-open-4", fake_now))
        store.put(_make_record("issues-closed.json", "d-close-4", fake_now + timedelta(hours=1)))
        store.put(_make_record("issues-reopened.json", "d-reopen-4", fake_now + timedelta(hours=2)))
        intake_id = models_mod.derive_intake_id(
            installation_id=99001, repo_full_name="allowed-org/allowed-repo", issue_number=42
        )
        stored = store.get(intake_id)
        assert stored.action == "reopened"
        assert stored.lifecycle_revision == 2

    def test_stale_delivery_produces_stale_outcome(self, tmp_hermes_home, tmp_kanban_board, fake_now):
        store_mod = _load_plugin_module("store")
        store = store_mod.IntakeStore(board_dir=tmp_kanban_board)
        store.put(_make_record("issues-opened.json", "d-open-5", fake_now))
        store.put(_make_record("issues-edited.json", "d-edit-5", fake_now + timedelta(minutes=5)))
        stale = _make_record("issues-opened.json", "d-open-stale", fake_now - timedelta(seconds=1))
        result = store.put(stale)
        assert result.outcome == "stale"

    def test_concurrent_cas_conflict_produces_conflict_outcome(self, tmp_hermes_home, tmp_kanban_board, fake_now):
        store_mod = _load_plugin_module("store")
        store = store_mod.IntakeStore(board_dir=tmp_kanban_board)
        store.put(_make_record("issues-opened.json", "d-open-cas", fake_now))
        edit_a = _make_record("issues-edited.json", "d-edit-cas-a", fake_now + timedelta(minutes=5))
        edit_b = _make_record("issues-edited.json", "d-edit-cas-b", fake_now + timedelta(minutes=5))
        store.put(edit_a)
        result_b = store.put(edit_b)
        assert result_b.outcome in ("conflict", "duplicate")

    def test_lifecycle_ordering_monotonic(self, tmp_hermes_home, tmp_kanban_board, fake_now):
        store_mod = _load_plugin_module("store")
        models_mod = _load_plugin_module("models")
        store = store_mod.IntakeStore(board_dir=tmp_kanban_board)
        for name, did, dt in [
            ("issues-opened.json", "d-mono-open", fake_now),
            ("issues-edited.json", "d-mono-edit", fake_now + timedelta(minutes=5)),
            ("issues-closed.json", "d-mono-close", fake_now + timedelta(hours=1)),
            ("issues-reopened.json", "d-mono-reopen", fake_now + timedelta(hours=2)),
        ]:
            store.put(_make_record(name, did, dt))
        intake_id = models_mod.derive_intake_id(
            installation_id=99001, repo_full_name="allowed-org/allowed-repo", issue_number=42
        )
        stored = store.get(intake_id)
        assert stored.lifecycle_revision == 3


class TestOrderingAndConcurrency:
    def test_out_of_order_delivery_before_current_is_stale(self, tmp_hermes_home, tmp_kanban_board, fake_now):
        store_mod = _load_plugin_module("store")
        store = store_mod.IntakeStore(board_dir=tmp_kanban_board)
        store.put(_make_record("issues-opened.json", "d-order-open", fake_now))
        store.put(_make_record("issues-edited.json", "d-order-edit", fake_now + timedelta(minutes=5)))
        past = _make_record("issues-opened.json", "d-order-past", fake_now - timedelta(seconds=10))
        result = store.put(past)
        assert result.outcome == "stale"
