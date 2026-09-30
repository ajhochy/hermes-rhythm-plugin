"""RED CLI tests for the github-intake plugin.

Tests the `hermes github-intake` CLI subcommands:
validate-config, ingest-fixture, replay, quarantine-list, audit, status, dry-run.
All mutating operations require explicit board; dry-run emits redacted JSON only.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (
    FIXTURES_DIR,
    PLUGIN_ROOT,
    REPO_ROOT,
    SENTINEL_SECRET,
    _load_plugin_module,
    sign_payload,
)

cli_mod = _load_plugin_module("cli")


def _run_cli(*args, env=None, input_data=None):
    import os
    base_env = os.environ.copy()
    if env:
        base_env.update(env)
    result = subprocess.run(
        [sys.executable, str(PLUGIN_ROOT / "cli.py"), *args],
        capture_output=True,
        text=True,
        env=base_env,
        input=input_data,
    )
    return result


class TestValidateConfigSubcommand:
    def test_validate_config_disabled_exits_0(self, disabled_config_path):
        result = _run_cli("validate-config", str(disabled_config_path))
        assert result.returncode == 0

    def test_validate_config_nonexistent_file_exits_nonzero(self, tmp_path):
        result = _run_cli("validate-config", str(tmp_path / "nonexistent.yaml"))
        assert result.returncode != 0

    def test_validate_config_enabled_false_reported(self, disabled_config_path):
        result = _run_cli("validate-config", str(disabled_config_path))
        assert "enabled" in result.stdout.lower() or "disabled" in result.stdout.lower()


class TestIngestFixtureSubcommand:
    def test_ingest_fixture_dry_run_exits_0(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path, webhook_secret
    ):
        fixture_path = FIXTURES_DIR / "issues-opened.json"
        result = _run_cli(
            "ingest-fixture",
            "--config", str(disabled_config_path),
            "--fixture", str(fixture_path),
            "--board", str(tmp_kanban_board),
            "--event-type", "issues",
            "--dry-run",
            env={"GITHUB_INTAKE_WEBHOOK_SECRET": SENTINEL_SECRET},
        )
        assert result.returncode == 0

    def test_ingest_fixture_dry_run_produces_json_output(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path, webhook_secret
    ):
        fixture_path = FIXTURES_DIR / "issues-opened.json"
        result = _run_cli(
            "ingest-fixture",
            "--config", str(disabled_config_path),
            "--fixture", str(fixture_path),
            "--board", str(tmp_kanban_board),
            "--event-type", "issues",
            "--dry-run",
            env={"GITHUB_INTAKE_WEBHOOK_SECRET": SENTINEL_SECRET},
        )
        output = json.loads(result.stdout)
        assert output.get("dry_run") is True

    def test_ingest_fixture_dry_run_no_board_writes(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path, webhook_secret
    ):
        fixture_path = FIXTURES_DIR / "issues-opened.json"
        _run_cli(
            "ingest-fixture",
            "--config", str(disabled_config_path),
            "--fixture", str(fixture_path),
            "--board", str(tmp_kanban_board),
            "--event-type", "issues",
            "--dry-run",
            env={"GITHUB_INTAKE_WEBHOOK_SECRET": SENTINEL_SECRET},
        )
        board_files = [f for f in tmp_kanban_board.rglob("*") if f.is_file()]
        assert len(board_files) == 0

    def test_ingest_fixture_redacts_secret_in_output(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path, webhook_secret
    ):
        fixture_path = FIXTURES_DIR / "issues-opened.json"
        result = _run_cli(
            "ingest-fixture",
            "--config", str(disabled_config_path),
            "--fixture", str(fixture_path),
            "--board", str(tmp_kanban_board),
            "--event-type", "issues",
            "--dry-run",
            env={"GITHUB_INTAKE_WEBHOOK_SECRET": SENTINEL_SECRET},
        )
        assert SENTINEL_SECRET not in result.stdout
        assert SENTINEL_SECRET not in result.stderr

    def test_ingest_fixture_unsupported_event_exits_nonzero(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path, webhook_secret
    ):
        fixture_path = FIXTURES_DIR / "unsupported-event.json"
        result = _run_cli(
            "ingest-fixture",
            "--config", str(disabled_config_path),
            "--fixture", str(fixture_path),
            "--board", str(tmp_kanban_board),
            "--event-type", "issues",
            "--dry-run",
            env={"GITHUB_INTAKE_WEBHOOK_SECRET": SENTINEL_SECRET},
        )
        assert result.returncode != 0


class TestStatusSubcommand:
    def test_status_shows_plugin_disabled(self, disabled_config_path, tmp_kanban_board):
        result = _run_cli(
            "status",
            "--config", str(disabled_config_path),
            "--board", str(tmp_kanban_board),
        )
        assert result.returncode == 0
        assert "disabled" in result.stdout.lower() or "false" in result.stdout.lower()


class TestAuditSubcommand:
    def test_audit_requires_board_argument(self, disabled_config_path):
        result = _run_cli("audit", "--config", str(disabled_config_path))
        assert result.returncode != 0

    def test_audit_empty_board_exits_0(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path
    ):
        result = _run_cli(
            "audit",
            "--config", str(disabled_config_path),
            "--board", str(tmp_kanban_board),
        )
        assert result.returncode == 0


class TestQuarantineListSubcommand:
    def test_quarantine_list_empty_board_exits_0(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path
    ):
        result = _run_cli(
            "quarantine-list",
            "--config", str(disabled_config_path),
            "--board", str(tmp_kanban_board),
        )
        assert result.returncode == 0

    def test_quarantine_list_output_is_json(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path
    ):
        result = _run_cli(
            "quarantine-list",
            "--config", str(disabled_config_path),
            "--board", str(tmp_kanban_board),
        )
        output = json.loads(result.stdout)
        assert isinstance(output, list)


class TestCLICounters:
    def test_dry_run_output_includes_outcome_counters(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path, webhook_secret
    ):
        fixture_path = FIXTURES_DIR / "issues-opened.json"
        result = _run_cli(
            "ingest-fixture",
            "--config", str(disabled_config_path),
            "--fixture", str(fixture_path),
            "--board", str(tmp_kanban_board),
            "--event-type", "issues",
            "--dry-run",
            env={"GITHUB_INTAKE_WEBHOOK_SECRET": SENTINEL_SECRET},
        )
        output = json.loads(result.stdout)
        assert "counters" in output or "outcome" in output

    def test_dry_run_output_includes_correlation_id(
        self, tmp_hermes_home, tmp_kanban_board, disabled_config_path, webhook_secret
    ):
        fixture_path = FIXTURES_DIR / "issues-opened.json"
        result = _run_cli(
            "ingest-fixture",
            "--config", str(disabled_config_path),
            "--fixture", str(fixture_path),
            "--board", str(tmp_kanban_board),
            "--event-type", "issues",
            "--dry-run",
            env={"GITHUB_INTAKE_WEBHOOK_SECRET": SENTINEL_SECRET},
        )
        output = json.loads(result.stdout)
        assert "correlation_id" in output or "intake_id" in output
