"""Tests for the frozen Hermes Rhythm feature-pack campaign contracts.

These are machine-readable guardrails for issue #3 (M0): ownership,
API-operation, permission, and first-slice architecture invariants that
every later slice (M1+) must satisfy. They are behavior contracts, not
snapshots — each scan-based test proves the checker actually *detects* a
violation via a synthetic fixture, not just that the current (still-empty)
``plugins/rhythm/`` tree happens to be clean.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


# ── Contract files exist, parse, and have the expected shape ──────────────


class TestContractFilesLoad:
    def test_ownership_contract_loads(self):
        from plugins.rhythm.contracts.validate import load_contract

        contract = load_contract("ownership")
        assert contract["contract"] == "rhythm-ownership"
        assert "plugins/rhythm/**" in contract["owned_paths"]
        assert contract["forbidden_paths"]

    def test_api_operations_contract_loads(self):
        from plugins.rhythm.contracts.validate import load_contract

        contract = load_contract("api-operations")
        assert contract["contract"] == "rhythm-api-operations"
        assert "milestones" in contract

    def test_permissions_contract_loads(self):
        from plugins.rhythm.contracts.validate import load_contract

        contract = load_contract("permissions")
        assert contract["contract"] == "rhythm-permissions"

    def test_architecture_contract_loads(self):
        from plugins.rhythm.contracts.validate import load_contract

        contract = load_contract("architecture")
        assert contract["contract"] == "rhythm-first-slice-architecture"
        assert contract["owner_root"] == "plugins/rhythm"


# ── Ownership contract ──────────────────────────────────────────────────


class TestOwnershipContract:
    def test_core_files_are_not_owned_by_rhythm(self):
        from plugins.rhythm.contracts.validate import is_path_owned

        assert is_path_owned("cli.py") is False
        assert is_path_owned("run_agent.py") is False
        assert is_path_owned("acp_adapter/server.py") is False

    def test_rhythm_package_paths_are_owned(self):
        from plugins.rhythm.contracts.validate import is_path_owned

        assert is_path_owned("plugins/rhythm/package/src/index.ts") is True


# ── Permission contract ────────────────────────────────────────────────


class TestPermissionsContract:
    def test_acp_never_auto_selects_persistent_approval(self):
        from plugins.rhythm.contracts.validate import load_contract

        contract = load_contract("permissions")
        assert contract["acp"]["auto_persistent_approval_allowed"] is False
        assert contract["acp"]["default_approval_mode"] == "interactive"

    def test_write_capability_requires_policy(self):
        from plugins.rhythm.contracts.validate import load_contract

        contract = load_contract("permissions")
        assert contract["acp"]["write_capability_requires_policy"] is True

    def test_ask_hermes_never_auto_sends(self):
        from plugins.rhythm.contracts.validate import load_contract

        contract = load_contract("permissions")
        assert contract["ask_hermes"]["auto_send_allowed"] is False
        assert contract["ask_hermes"]["opens_editable_draft"] is True


# ── API-operation contract ─────────────────────────────────────────────


class TestApiOperationsContract:
    def test_first_slice_is_read_only_and_bounded(self):
        from plugins.rhythm.contracts.validate import load_contract

        contract = load_contract("api-operations")
        first_slice = contract["milestones"]["M4a"]
        assert first_slice["read_only"] is True
        paths = {op["path"] for op in first_slice["allowed_operations"]}
        assert paths == {"/auth/me", "/workspaces/me"}
        methods = {op["method"] for op in first_slice["allowed_operations"]}
        assert methods == {"GET"}

    def test_arbitrary_proxying_is_forbidden(self):
        from plugins.rhythm.contracts.validate import load_contract

        contract = load_contract("api-operations")
        assert "arbitrary_proxying" in contract["forbidden"]


# ── Architecture contract: structural ───────────────────────────────────


class TestArchitectureContractStructure:
    def test_exactly_one_desktop_route_allowed(self):
        from plugins.rhythm.contracts.validate import load_contract

        contract = load_contract("architecture")
        assert contract["desktop_routes"]["allowed"] == ["/rhythm"]
        assert contract["desktop_routes"]["max_count"] == 1

    def test_electron_and_second_agent_ui_forbidden(self):
        from plugins.rhythm.contracts.validate import load_contract

        contract = load_contract("architecture")
        assert contract["embed_electron_allowed"] is False
        assert contract["embed_second_agent_ui_allowed"] is False

    def test_current_repo_tree_is_clean(self):
        from plugins.rhythm.contracts.validate import validate_architecture

        assert validate_architecture(REPO_ROOT) == []


# ── Architecture contract: scanners actually catch violations ─────────


class TestArchitectureScanners:
    def test_detects_hardcoded_port_4001_dependency(self, tmp_path):
        from plugins.rhythm.contracts.validate import scan_port_dependency_violations

        target = tmp_path / "plugins" / "rhythm" / "server" / "client.ts"
        target.parent.mkdir(parents=True)
        target.write_text("const base = 'http://localhost:4001/api';\n")

        violations = scan_port_dependency_violations(tmp_path)

        assert violations
        assert "4001" in violations[0]

    @pytest.mark.parametrize("port", [4001, 4097, 4098])
    def test_detects_each_forbidden_port_dependency(self, tmp_path, port):
        from plugins.rhythm.contracts.validate import scan_port_dependency_violations

        target = tmp_path / "plugins" / "rhythm" / "server" / f"client_{port}.ts"
        target.parent.mkdir(parents=True)
        target.write_text(f"const base = 'http://localhost:{port}/api';\n")

        violations = scan_port_dependency_violations(tmp_path)

        assert violations
        assert str(port) in violations[0]

    def test_clean_tree_has_no_port_violations(self, tmp_path):
        from plugins.rhythm.contracts.validate import scan_port_dependency_violations

        target = tmp_path / "plugins" / "rhythm" / "server" / "client.ts"
        target.parent.mkdir(parents=True)
        target.write_text("const base = process.env.RHYTHM_API_BASE_URL;\n")

        assert scan_port_dependency_violations(tmp_path) == []

    def test_detects_renderer_reachable_credential(self, tmp_path):
        from plugins.rhythm.contracts.validate import (
            scan_renderer_credential_violations,
        )

        target = tmp_path / "plugins" / "rhythm" / "src" / "widget.tsx"
        target.parent.mkdir(parents=True)
        target.write_text("const key = process.env.RHYTHM_API_KEY;\n")

        violations = scan_renderer_credential_violations(tmp_path)

        assert violations
        assert "RHYTHM_API_KEY" in violations[0]

    def test_server_owned_path_is_exempt_from_credential_scan(self, tmp_path):
        from plugins.rhythm.contracts.validate import (
            scan_renderer_credential_violations,
        )

        target = tmp_path / "plugins" / "rhythm" / "server" / "auth.ts"
        target.parent.mkdir(parents=True)
        target.write_text("const key = process.env.RHYTHM_API_KEY;\n")

        assert scan_renderer_credential_violations(tmp_path) == []

    def test_detects_second_agent_runtime_import(self, tmp_path):
        from plugins.rhythm.contracts.validate import (
            scan_second_agent_runtime_violations,
        )

        target = tmp_path / "plugins" / "rhythm" / "bridge.py"
        target.parent.mkdir(parents=True)
        target.write_text("from run_agent import AIAgent\n")

        violations = scan_second_agent_runtime_violations(tmp_path)

        assert violations

    def test_detects_arbitrary_proxy_middleware(self, tmp_path):
        from plugins.rhythm.contracts.validate import scan_arbitrary_proxy_violations

        target = tmp_path / "plugins" / "rhythm" / "server" / "gateway.ts"
        target.parent.mkdir(parents=True)
        target.write_text(
            "import { createProxyMiddleware } from 'http-proxy-middleware';\n"
        )

        violations = scan_arbitrary_proxy_violations(tmp_path)

        assert violations

    def test_validate_architecture_aggregates_all_scanners(self, tmp_path):
        from plugins.rhythm.contracts.validate import validate_architecture

        target = tmp_path / "plugins" / "rhythm" / "src" / "widget.tsx"
        target.parent.mkdir(parents=True)
        target.write_text(
            "const key = process.env.RHYTHM_API_KEY;\n"
            "const base = 'http://localhost:4001';\n"
        )

        violations = validate_architecture(tmp_path)

        assert len(violations) >= 2
