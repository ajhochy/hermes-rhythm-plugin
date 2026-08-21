"""Machine-readable contracts for the Hermes Rhythm feature-pack campaign.

Frozen at M0 (issue #3) as the guardrails every later slice (M1+) must
satisfy: which paths Rhythm owns, which API operations it may call at each
milestone, its permission/write-capability invariants, and the first-slice
architecture rules (no renderer credentials, no arbitrary proxying, no
second agent runtime, no port-4001 dependency).

These are fitness functions, not documentation: ``validate_architecture()``
walks the real ``plugins/rhythm/`` tree so a later PR that violates a
locked decision fails a test instead of silently drifting.
"""

from __future__ import annotations

import json
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Iterable, Optional

CONTRACTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = CONTRACTS_DIR.parents[2]

_SCANNABLE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx"}

# Substrings that indicate code under plugins/rhythm/ is standing up a
# second agent process/runtime instead of reusing the host Hermes agent —
# forbidden by the locked architecture (parent issue #2).
_SECOND_AGENT_RUNTIME_MARKERS = (
    "run_agent.py",
    "from run_agent import",
    "import run_agent",
    "acp_adapter",
    "hermes-acp",
    "hermes --acp",
)

# Substrings that indicate a generic/catch-all HTTP proxy instead of the
# closed allowlist in api-operations.json.
_ARBITRARY_PROXY_MARKERS = (
    "createProxyMiddleware",
    "http-proxy-middleware",
    "app.use(['*']",
    'app.use(["*"]',
    "app.all('*'",
    'app.all("*"',
)


def load_contract(name: str) -> dict[str, Any]:
    """Load one of the frozen contract JSON files by its base name."""
    path = CONTRACTS_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def is_path_owned(relative_path: str) -> bool:
    """Return whether *relative_path* falls under the Rhythm ownership root.

    Explicitly rejects any path matching ``forbidden_paths`` (Hermes core)
    even if it would otherwise match ``owned_paths``, so a glob typo in the
    contract can't silently claim core files.
    """
    contract = load_contract("ownership")
    normalized = relative_path.replace("\\", "/")
    if any(fnmatch(normalized, pattern) for pattern in contract["forbidden_paths"]):
        return False
    return any(fnmatch(normalized, pattern) for pattern in contract["owned_paths"])


def _iter_owned_files(root: Path, owner_root: str) -> list[Path]:
    """Yield scannable product files under *owner_root*.

    Excludes ``<owner_root>/contracts/`` itself: that directory is this
    tooling (the marker strings it defines would otherwise flag its own
    source), not Rhythm product code.
    """
    owned_dir = root / owner_root
    if not owned_dir.is_dir():
        return []
    contracts_dir = owned_dir / "contracts"
    return [
        path
        for path in owned_dir.rglob("*")
        if path.is_file()
        and path.suffix in _SCANNABLE_SUFFIXES
        and contracts_dir not in path.parents
    ]


def _matches_any_glob(path: Path, root: Path, patterns: Iterable[str]) -> bool:
    rel = path.relative_to(root).as_posix()
    return any(fnmatch(rel, pattern) for pattern in patterns)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def scan_port_dependency_violations(
    root: Path, contract: Optional[dict[str, Any]] = None
) -> list[str]:
    """Flag any owned file that hardcodes a host:port dependency on a
    forbidden port (e.g. Rhythm's local dev server on 4001)."""
    contract = contract or load_contract("architecture")
    owner_root = contract["owner_root"]
    ports = contract.get("forbidden_dependencies", {}).get("ports", [])
    violations: list[str] = []
    for path in _iter_owned_files(root, owner_root):
        text = _read_text(path)
        for lineno, line in enumerate(text.splitlines(), start=1):
            for port in ports:
                if f":{port}" in line:
                    violations.append(
                        f"{path}:{lineno}: hardcoded port {port} dependency"
                    )
    return violations


def scan_renderer_credential_violations(
    root: Path, contract: Optional[dict[str, Any]] = None
) -> list[str]:
    """Flag a credential identifier referenced outside the server-owned paths.

    Credentials must remain server-side (locked architecture); a renderer-
    reachable file referencing a Rhythm credential identifier directly is a
    violation regardless of how it's used.
    """
    contract = contract or load_contract("architecture")
    owner_root = contract["owner_root"]
    server_paths = contract.get("server_owned_credential_paths", [])
    identifiers = contract.get("credential_identifiers", [])
    violations: list[str] = []
    for path in _iter_owned_files(root, owner_root):
        if _matches_any_glob(path, root, server_paths):
            continue
        text = _read_text(path)
        for lineno, line in enumerate(text.splitlines(), start=1):
            for identifier in identifiers:
                if identifier in line:
                    violations.append(
                        f"{path}:{lineno}: renderer-reachable file references {identifier}"
                    )
    return violations


def scan_second_agent_runtime_violations(
    root: Path, contract: Optional[dict[str, Any]] = None
) -> list[str]:
    """Flag any owned file that stands up a second agent runtime/process."""
    contract = contract or load_contract("architecture")
    owner_root = contract["owner_root"]
    violations: list[str] = []
    for path in _iter_owned_files(root, owner_root):
        text = _read_text(path)
        for lineno, line in enumerate(text.splitlines(), start=1):
            for marker in _SECOND_AGENT_RUNTIME_MARKERS:
                if marker in line:
                    violations.append(
                        f"{path}:{lineno}: second agent runtime marker '{marker}'"
                    )
    return violations


def scan_arbitrary_proxy_violations(
    root: Path, contract: Optional[dict[str, Any]] = None
) -> list[str]:
    """Flag any owned file wiring a generic/catch-all HTTP proxy."""
    contract = contract or load_contract("architecture")
    owner_root = contract["owner_root"]
    violations: list[str] = []
    for path in _iter_owned_files(root, owner_root):
        text = _read_text(path)
        for lineno, line in enumerate(text.splitlines(), start=1):
            for marker in _ARBITRARY_PROXY_MARKERS:
                if marker in line:
                    violations.append(
                        f"{path}:{lineno}: arbitrary proxy marker '{marker}'"
                    )
    return violations


def validate_architecture(root: Path) -> list[str]:
    """Return every architecture-contract violation found under owner_root."""
    contract = load_contract("architecture")
    violations: list[str] = []
    violations += scan_port_dependency_violations(root, contract)
    violations += scan_renderer_credential_violations(root, contract)
    violations += scan_second_agent_runtime_violations(root, contract)
    violations += scan_arbitrary_proxy_violations(root, contract)
    return violations
