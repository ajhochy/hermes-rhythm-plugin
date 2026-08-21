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


# ── Port scanner: boundary-aware matching (F4) ─────────────────────────


class TestPortScannerBoundaryAware:
    @pytest.mark.parametrize(
        "syntax_name,ext,line",
        [
            ("url", "ts", "const base = 'http://localhost:4001/api';"),
            ("ts_object_key", "ts", "const config = { port: 4001 };"),
            ("json_key", "ts", '{"port": 4001}'),
            ("python_assignment", "py", "PORT = 4001"),
        ],
    )
    def test_detects_port_4001_across_syntaxes(self, tmp_path, syntax_name, ext, line):
        from plugins.rhythm.contracts.validate import scan_port_dependency_violations

        target = tmp_path / "plugins" / "rhythm" / "server" / f"{syntax_name}.{ext}"
        target.parent.mkdir(parents=True)
        target.write_text(line + "\n")

        violations = scan_port_dependency_violations(tmp_path)

        assert violations, f"expected a violation for syntax {syntax_name!r}: {line!r}"
        assert "4001" in violations[0]

    @pytest.mark.parametrize(
        "syntax_name,ext,line",
        [
            ("url", "ts", "const base = 'http://localhost:{port}/api';"),
            ("ts_object_key", "ts", "const config = {{ port: {port} }};"),
            ("json_key", "ts", '{{"port": {port}}}'),
            ("python_assignment", "py", "PORT = {port}"),
        ],
    )
    @pytest.mark.parametrize("port", [4097, 4098])
    def test_detects_each_forbidden_port_across_syntaxes(
        self, tmp_path, syntax_name, ext, line, port
    ):
        from plugins.rhythm.contracts.validate import scan_port_dependency_violations

        target = tmp_path / "plugins" / "rhythm" / "server" / f"{syntax_name}_{port}.{ext}"
        target.parent.mkdir(parents=True)
        target.write_text(line.format(port=port) + "\n")

        violations = scan_port_dependency_violations(tmp_path)

        assert violations
        assert str(port) in violations[0]

    def test_does_not_false_positive_on_longer_number_containing_port(self, tmp_path):
        """``14001`` embeds the substring ``4001`` but is not port 4001; a
        naive substring/colon check must not flag it."""
        from plugins.rhythm.contracts.validate import scan_port_dependency_violations

        target = tmp_path / "plugins" / "rhythm" / "server" / "unrelated.ts"
        target.parent.mkdir(parents=True)
        target.write_text("const buildNumber = 14001;\nconst other = 40010;\n")

        assert scan_port_dependency_violations(tmp_path) == []

    @pytest.mark.parametrize(
        "syntax_name,ext,line",
        [
            ("ipv6_bracket_url", "ts", "const base = 'http://[::1]:4001/api';"),
            ("ipv6_bracket_bare", "py", "ADDR = '[::1]:4001'"),
            ("wildcard_host", "py", "ADDR = '0.0.0.0:4001'"),
            ("wildcard_star", "ts", "const addr = '*:4001';"),
            ("hostname", "ts", "const addr = 'rhythm.local:4001';"),
        ],
    )
    def test_detects_port_regardless_of_host_syntax(self, tmp_path, syntax_name, ext, line):
        """The port literal must be caught no matter what address form
        (bracketed IPv6, wildcard, hostname) precedes it — the scanner
        keys on the port number, not the host shape."""
        from plugins.rhythm.contracts.validate import scan_port_dependency_violations

        target = tmp_path / "plugins" / "rhythm" / "server" / f"{syntax_name}.{ext}"
        target.parent.mkdir(parents=True)
        target.write_text(line + "\n")

        violations = scan_port_dependency_violations(tmp_path)

        assert violations, f"expected a violation for {syntax_name!r}: {line!r}"
        assert "4001" in violations[0]


# ── Port scanner: AST/dataflow, not regex shortcuts (F7) ────────────────


class TestPortScannerASTDataflow:
    """The boundary-aware regex scan above still misses bypasses a
    determined (or merely differently-styled) author can hit without any
    intent to evade: a port written in hex, or a bind()/listen() call that
    references a same-file named constant instead of a literal on that
    line. These require real source-level analysis (Python's ``ast``
    module) rather than another regex tweak.
    """

    def test_detects_hex_literal_port_in_python(self, tmp_path):
        from plugins.rhythm.contracts.validate import scan_port_dependency_violations

        target = tmp_path / "plugins" / "rhythm" / "server" / "hexport.py"
        target.parent.mkdir(parents=True)
        target.write_text("RHYTHM_PORT = 0xFA1\n")

        violations = scan_port_dependency_violations(tmp_path)

        assert violations
        assert "4001" in violations[0]

    def test_detects_hex_literal_port_in_typescript(self, tmp_path):
        from plugins.rhythm.contracts.validate import scan_port_dependency_violations

        target = tmp_path / "plugins" / "rhythm" / "server" / "hexport.ts"
        target.parent.mkdir(parents=True)
        target.write_text("const port = 0xFA1;\n")

        violations = scan_port_dependency_violations(tmp_path)

        assert violations
        assert "4001" in violations[0]

    @pytest.mark.parametrize("port,hexval", [(4097, "0x1001"), (4098, "0x1002")])
    def test_detects_each_forbidden_port_as_hex(self, tmp_path, port, hexval):
        from plugins.rhythm.contracts.validate import scan_port_dependency_violations

        target = tmp_path / "plugins" / "rhythm" / "server" / f"hex_{port}.py"
        target.parent.mkdir(parents=True)
        target.write_text(f"PORT = {hexval}\n")

        violations = scan_port_dependency_violations(tmp_path)

        assert violations
        assert str(port) in violations[0]

    def test_does_not_false_positive_on_unrelated_hex_literal(self, tmp_path):
        """``0x14001`` is a different integer than any forbidden port and
        must not be flagged just because its hex digits contain a
        forbidden port's hex digits as a substring."""
        from plugins.rhythm.contracts.validate import scan_port_dependency_violations

        target = tmp_path / "plugins" / "rhythm" / "server" / "unrelated_hex.py"
        target.parent.mkdir(parents=True)
        target.write_text("BUILD_ID = 0x14001\n")

        assert scan_port_dependency_violations(tmp_path) == []

    def test_detects_default_arg_hex_port(self, tmp_path):
        from plugins.rhythm.contracts.validate import scan_port_dependency_violations

        target = tmp_path / "plugins" / "rhythm" / "server" / "defarg.py"
        target.parent.mkdir(parents=True)
        target.write_text("def start_server(port=0xFA1):\n    pass\n")

        violations = scan_port_dependency_violations(tmp_path)

        assert violations
        assert "4001" in violations[0]

    def test_detects_indirect_bind_via_same_file_named_constant(self, tmp_path):
        """The literal ``4001`` only ever appears on the constant's own
        assignment line; the ``sock.bind(...)`` call three lines later
        references only the *name*. A per-line text/regex scan cannot see
        this — it requires resolving the name back to its value."""
        from plugins.rhythm.contracts.validate import scan_port_dependency_violations

        target = tmp_path / "plugins" / "rhythm" / "server" / "indirect_bind.py"
        target.parent.mkdir(parents=True)
        target.write_text(
            "DEFAULT_PORT = 4001\n"
            "\n"
            "def start(sock):\n"
            "    sock.bind(('0.0.0.0', DEFAULT_PORT))\n"
        )

        violations = scan_port_dependency_violations(tmp_path)

        bind_call_violations = [v for v in violations if ":4:" in v]
        assert bind_call_violations, (
            f"expected a violation attributed to the bind() call line "
            f"(line 4), got: {violations!r}"
        )
        assert "DEFAULT_PORT" in bind_call_violations[0]
        assert "4001" in bind_call_violations[0]

    def test_detects_indirect_listen_via_same_file_named_constant(self, tmp_path):
        from plugins.rhythm.contracts.validate import scan_port_dependency_violations

        target = tmp_path / "plugins" / "rhythm" / "server" / "indirect_listen.py"
        target.parent.mkdir(parents=True)
        target.write_text(
            "RHYTHM_DEV_PORT = 4097\n"
            "\n"
            "def run(server):\n"
            "    server.listen(RHYTHM_DEV_PORT)\n"
        )

        violations = scan_port_dependency_violations(tmp_path)

        listen_call_violations = [v for v in violations if ":4:" in v]
        assert listen_call_violations
        assert "RHYTHM_DEV_PORT" in listen_call_violations[0]
        assert "4097" in listen_call_violations[0]

    def test_does_not_false_positive_on_unrelated_named_constant_in_bind(self, tmp_path):
        """A constant that isn't a forbidden port must not be flagged just
        because it's passed to bind()/listen()."""
        from plugins.rhythm.contracts.validate import scan_port_dependency_violations

        target = tmp_path / "plugins" / "rhythm" / "server" / "unrelated_bind.py"
        target.parent.mkdir(parents=True)
        target.write_text(
            "ALLOWED_PORT = 8080\n"
            "\n"
            "def start(sock):\n"
            "    sock.bind(('0.0.0.0', ALLOWED_PORT))\n"
        )

        assert scan_port_dependency_violations(tmp_path) == []

    def test_syntax_error_python_file_does_not_crash_the_scan(self, tmp_path):
        """A malformed/partially-written ``.py`` file must degrade to the
        textual scan, not blow up the whole architecture validator."""
        from plugins.rhythm.contracts.validate import scan_port_dependency_violations

        target = tmp_path / "plugins" / "rhythm" / "server" / "broken.py"
        target.parent.mkdir(parents=True)
        target.write_text("def start(:\n    PORT = 4001\n")

        violations = scan_port_dependency_violations(tmp_path)

        assert violations
        assert "4001" in violations[0]

    def test_current_repo_tree_is_clean_under_ast_scanner(self):
        """Sanity: the AST/dataflow pass must not introduce false
        positives against the actual repo."""
        from plugins.rhythm.contracts.validate import scan_port_dependency_violations

        assert scan_port_dependency_violations(REPO_ROOT) == []

    @pytest.mark.parametrize(
        "filename,source",
        [
            ("separator.ts", "server.listen(4_001);\n"),
            ("hex_separator.js", "server.listen(0xF_A1);\n"),
            ("expression.ts", "server.listen(4000 + 1);\n"),
            ("constant.ts", "const PORT = 4000 + 1;\nserver.listen(PORT);\n"),
            ("ipv4.ts", "server.listen('127.0.0.1:4000+1');\n"),
            ("ipv6.ts", "server.listen('[::1]:4000+1');\n"),
            ("hostname.ts", "server.listen('rhythm.local:4_001');\n"),
        ],
    )
    def test_detects_javascript_port_expression_bypasses(self, tmp_path, filename, source):
        from plugins.rhythm.contracts.validate import scan_port_dependency_violations

        target = tmp_path / "plugins" / "rhythm" / "server" / filename
        target.parent.mkdir(parents=True)
        target.write_text(source)

        assert scan_port_dependency_violations(tmp_path), source

    def test_javascript_scanner_ignores_strings_and_comments(self, tmp_path):
        from plugins.rhythm.contracts.validate import scan_port_dependency_violations

        target = tmp_path / "plugins" / "rhythm" / "server" / "fixtures.ts"
        target.parent.mkdir(parents=True)
        target.write_text(
            "// server.listen(4_001)\n"
            "const example = 'server.listen(4000 + 1)';\n"
            "/* const PORT = 0xF_A1; */\n"
        )

        assert scan_port_dependency_violations(tmp_path) == []


# ── Architecture validator scans shared seams too (F5) ─────────────────


class TestArchitectureScansSharedSeams:
    """The ownership contract declares apps/desktop/src/contrib/** as a
    shared seam where later Rhythm slices (M2) land code. The architecture
    validator must scan that seam too, not just plugins/rhythm/**, without
    claiming arbitrary ownership of the rest of apps/desktop."""

    def test_shared_seam_is_declared_in_ownership_contract(self):
        from plugins.rhythm.contracts.validate import load_contract

        contract = load_contract("ownership")
        assert "apps/desktop/src/contrib/**" in contract["shared_seams"]

    def test_detects_renderer_credential_in_shared_seam(self, tmp_path):
        from plugins.rhythm.contracts.validate import (
            scan_renderer_credential_violations,
        )

        target = tmp_path / "apps" / "desktop" / "src" / "contrib" / "widget.tsx"
        target.parent.mkdir(parents=True)
        target.write_text("const key = process.env.RHYTHM_API_KEY;\n")

        violations = scan_renderer_credential_violations(tmp_path)

        assert violations
        assert "RHYTHM_API_KEY" in violations[0]

    def test_detects_second_agent_runtime_in_shared_seam(self, tmp_path):
        from plugins.rhythm.contracts.validate import (
            scan_second_agent_runtime_violations,
        )

        target = tmp_path / "apps" / "desktop" / "src" / "contrib" / "bridge.ts"
        target.parent.mkdir(parents=True)
        target.write_text("import '../../../../acp_adapter';\n")

        violations = scan_second_agent_runtime_violations(tmp_path)

        assert violations

    def test_detects_arbitrary_proxy_in_shared_seam(self, tmp_path):
        from plugins.rhythm.contracts.validate import scan_arbitrary_proxy_violations

        target = tmp_path / "apps" / "desktop" / "src" / "contrib" / "gateway.ts"
        target.parent.mkdir(parents=True)
        target.write_text(
            "import { createProxyMiddleware } from 'http-proxy-middleware';\n"
        )

        violations = scan_arbitrary_proxy_violations(tmp_path)

        assert violations

    def test_detects_forbidden_port_in_shared_seam(self, tmp_path):
        from plugins.rhythm.contracts.validate import scan_port_dependency_violations

        target = tmp_path / "apps" / "desktop" / "src" / "contrib" / "client.ts"
        target.parent.mkdir(parents=True)
        target.write_text("const base = 'http://localhost:4001/api';\n")

        violations = scan_port_dependency_violations(tmp_path)

        assert violations
        assert "4001" in violations[0]

    def test_validate_architecture_covers_shared_seam(self, tmp_path):
        from plugins.rhythm.contracts.validate import validate_architecture

        target = tmp_path / "apps" / "desktop" / "src" / "contrib" / "widget.tsx"
        target.parent.mkdir(parents=True)
        target.write_text("const key = process.env.RHYTHM_API_KEY;\n")

        assert validate_architecture(tmp_path) != []

    def test_current_repo_tree_shared_seam_is_clean(self):
        """Sanity: extending the scan to the real shared seam directory
        must not introduce false positives against the actual repo."""
        from plugins.rhythm.contracts.validate import validate_architecture

        assert validate_architecture(REPO_ROOT) == []


# ── Sibling Hermes worktree root discovery (F6) ─────────────────────────


class TestSiblingHermesRootDiscovery:
    """``validate_architecture`` only ever saw ``REPO_ROOT`` — this one
    worktree. A violation planted in a sibling Hermes worktree (a parallel
    agent slice of the same feature branch, sharing this repo's ``.git``)
    was invisible to it. ``discover_hermes_worktree_roots`` proves the
    sibling root set via ``git worktree list --porcelain`` — the only
    source that actually enumerates every worktree attached to this
    repo — instead of guessing from directory layout, and fails closed
    when that proof is incomplete.
    """

    @staticmethod
    def _fake_run(stdout: str, returncode: int = 0):
        import subprocess as _subprocess

        def _run(*args, **kwargs):
            return _subprocess.CompletedProcess(
                args=args, returncode=returncode, stdout=stdout, stderr=""
            )

        return _run

    def test_discovers_every_worktree_from_porcelain_output(
        self, tmp_path, monkeypatch
    ):
        from plugins.rhythm.contracts import validate

        primary = tmp_path / "primary"
        sibling = tmp_path / "sibling"
        for d in (primary, sibling):
            d.mkdir()
            (d / ".git").mkdir()

        porcelain = (
            f"worktree {primary}\nHEAD abc\nbranch refs/heads/main\n\n"
            f"worktree {sibling}\nHEAD def\nbranch refs/heads/feature\n"
        )
        monkeypatch.setattr(validate.subprocess, "run", self._fake_run(porcelain))

        roots = validate.discover_hermes_worktree_roots(primary)

        assert primary.resolve() in roots
        assert sibling.resolve() in roots
        assert len(roots) == 2

    def test_fails_closed_when_git_command_errors(self, tmp_path, monkeypatch):
        from plugins.rhythm.contracts import validate

        monkeypatch.setattr(
            validate.subprocess, "run", self._fake_run("", returncode=128)
        )

        with pytest.raises(validate.RootDiscoveryError):
            validate.discover_hermes_worktree_roots(tmp_path)

    def test_fails_closed_when_git_binary_missing(self, tmp_path, monkeypatch):
        from plugins.rhythm.contracts import validate

        def _raise(*a, **kw):
            raise FileNotFoundError("git not found")

        monkeypatch.setattr(validate.subprocess, "run", _raise)

        with pytest.raises(validate.RootDiscoveryError):
            validate.discover_hermes_worktree_roots(tmp_path)

    def test_fails_closed_when_porcelain_output_has_no_worktree_entries(
        self, tmp_path, monkeypatch
    ):
        from plugins.rhythm.contracts import validate

        monkeypatch.setattr(validate.subprocess, "run", self._fake_run(""))

        with pytest.raises(validate.RootDiscoveryError):
            validate.discover_hermes_worktree_roots(tmp_path)

    def test_fails_closed_when_anchor_missing_from_enumeration(
        self, tmp_path, monkeypatch
    ):
        """If git's own enumeration doesn't include the anchor we asked it
        to prove coverage for, the proof is inconsistent — this must not
        silently proceed as if the anchor were covered."""
        from plugins.rhythm.contracts import validate

        anchor = tmp_path / "anchor"
        other = tmp_path / "other"
        for d in (anchor, other):
            d.mkdir()
            (d / ".git").mkdir()

        porcelain = f"worktree {other}\nHEAD abc\nbranch refs/heads/main\n"
        monkeypatch.setattr(validate.subprocess, "run", self._fake_run(porcelain))

        with pytest.raises(validate.RootDiscoveryError):
            validate.discover_hermes_worktree_roots(anchor)

    def test_skips_stale_worktree_entries_that_no_longer_exist_on_disk(
        self, tmp_path, monkeypatch
    ):
        """git can list a prunable worktree whose directory was deleted;
        a stale entry must not crash discovery — only real, live
        worktrees count toward the proven set."""
        from plugins.rhythm.contracts import validate

        anchor = tmp_path / "anchor"
        anchor.mkdir()
        (anchor / ".git").mkdir()
        deleted = tmp_path / "deleted-worktree"

        porcelain = (
            f"worktree {anchor}\nHEAD abc\nbranch refs/heads/main\n\n"
            f"worktree {deleted}\nHEAD def\nbranch refs/heads/gone\n"
        )
        monkeypatch.setattr(validate.subprocess, "run", self._fake_run(porcelain))

        roots = validate.discover_hermes_worktree_roots(anchor)

        assert roots == [anchor.resolve()]

    def test_validate_architecture_across_hermes_roots_catches_sibling_violation(
        self, tmp_path, monkeypatch
    ):
        from plugins.rhythm.contracts import validate

        anchor = tmp_path / "anchor"
        sibling = tmp_path / "sibling"
        for d in (anchor, sibling):
            d.mkdir()
            (d / ".git").mkdir()

        bad = sibling / "plugins" / "rhythm" / "server" / "leak.ts"
        bad.parent.mkdir(parents=True)
        bad.write_text("const base = 'http://localhost:4001/api';\n")

        porcelain = (
            f"worktree {anchor}\nHEAD abc\nbranch refs/heads/main\n\n"
            f"worktree {sibling}\nHEAD def\nbranch refs/heads/other-slice\n"
        )
        monkeypatch.setattr(validate.subprocess, "run", self._fake_run(porcelain))

        violations = validate.validate_architecture_across_hermes_roots(anchor)

        assert any("4001" in v for v in violations)
        assert any(str(sibling) in v for v in violations)

    def test_real_repo_sibling_roots_are_clean(self):
        """Integration sanity: running the real discovery + scan against
        this actual repository (whatever worktrees happen to be attached
        to it right now, including just itself) must not crash and must
        find no violations."""
        from plugins.rhythm.contracts.validate import (
            validate_architecture_across_hermes_roots,
        )

        assert validate_architecture_across_hermes_roots(REPO_ROOT) == []
