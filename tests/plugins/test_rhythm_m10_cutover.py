"""M10 final cutover evidence is deterministic, fixture-backed, and local-only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plugins.rhythm.packaging.cutover import (
    APPROVED_DESTINATIONS,
    POLICY_DISABLED_ACTIONS,
    CutoverError,
    run_fixture_cutover,
    validate_cutover_ledger,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_issue_14_c1_final_fixture_cutover_exercises_every_approved_destination_and_only_three_tools(tmp_path):
    """Regression: a final dogfood report claims a screen/tool that the fixture cycle did not execute."""
    ledger = run_fixture_cutover(REPO_ROOT, tmp_path / "hermes-home" / "profiles" / "m10")

    assert [row["module"] for row in ledger["modules"]] == list(APPROVED_DESTINATIONS)
    assert all(row["fixture"] and row["canonical_reads"] for row in ledger["modules"])
    assert all(row["responsive_a11y"] and row["failure_state"] for row in ledger["modules"])
    assert ledger["native_tools"]["exercised"] == [
        "rhythm_complete_task", "rhythm_get_dashboard", "rhythm_list_tasks",
    ]
    assert ledger["lifecycle"]["statuses"] == ["installed", "reinstalled", "upgraded", "rolled_back", "uninstalled"]
    assert ledger["lifecycle"]["restart_signal"] == "hermes gateway restart"
    assert ledger["external_credentialed_live_read"] == "pending_manual"


def test_issue_14_c2_ledger_rejects_missing_proof_secret_leaks_or_unapproved_writes(tmp_path):
    """Regression: a ledger accepts hand-waved evidence, credentials, or an action outside the approved policy."""
    ledger = run_fixture_cutover(REPO_ROOT, tmp_path / "hermes-home" / "profiles" / "m10")
    ledger["modules"][0]["canonical_reads"] = []
    with pytest.raises(CutoverError, match="canonical read"):
        validate_cutover_ledger(ledger)

    ledger = run_fixture_cutover(REPO_ROOT, tmp_path / "hermes-home" / "profiles" / "m10b")
    ledger["modules"][0]["failure_state"] = "Bearer " + "fixture-" + "secret-" + "token"
    with pytest.raises(CutoverError, match="credential-shaped"):
        validate_cutover_ledger(ledger)

    ledger = run_fixture_cutover(REPO_ROOT, tmp_path / "hermes-home" / "profiles" / "m10c")
    ledger["modules"][0]["allowed_write_confirmation"] = {"operation": "messages.send"}
    with pytest.raises(CutoverError, match="unapproved write"):
        validate_cutover_ledger(ledger)


def test_issue_14_c3_auth_expiry_restart_profile_generation_uncertain_and_performance_are_recorded(tmp_path):
    """Regression: lifecycle or authorization failures are omitted from a superficially green cutover record."""
    ledger = run_fixture_cutover(REPO_ROOT, tmp_path / "hermes-home" / "profiles" / "m10")
    checks = ledger["safety_checks"]
    assert checks["auth_expiry"] == "unauthorized"
    assert checks["profile_switch_generation_invalidation"] == "zero_patch"
    assert checks["uncertain_write"] == "no_retry_no_false_success"
    assert checks["secret_redaction"] == "pass"
    assert checks["performance"]["elapsed_ms"] <= checks["performance"]["budget_ms"]
    assert checks["restart_signal"] == "hermes gateway restart"


def test_issue_14_c4_policy_disabled_actions_are_explicit_and_proven_absent(tmp_path):
    """Regression: a prohibited agent/navigation/message action quietly becomes part of M10 cutover."""
    ledger = run_fixture_cutover(REPO_ROOT, tmp_path / "hermes-home" / "profiles" / "m10")
    assert ledger["policy_disabled_actions"] == list(POLICY_DISABLED_ACTIONS)
    assert ledger["policy_disabled_proof"] == "absent_from_adapter_and_native_tool_surface"
    assert "agent_navigation" in ledger["policy_disabled_actions"]
    assert "messages.send" in ledger["policy_disabled_actions"]


def test_issue_14_c5_committed_machine_ledger_matches_the_validated_fixture_shape():
    """Regression: committed cutover evidence drifts from the generated, reviewable record."""
    ledger = json.loads((REPO_ROOT / "docs/ai/rhythm-m10-cutover-ledger.json").read_text(encoding="utf-8"))
    validate_cutover_ledger(ledger)
    assert ledger["evidence_mode"] == "sanitized_canonical_fixture_transport"
    assert ledger["automated_acceptance"] == "pass"
    assert ledger["manual_gates"] == ["AJ cutover and merge", "signed/notarized release"]
