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

import ast
import json
import re
import subprocess
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Iterable, Optional

CONTRACTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = CONTRACTS_DIR.parents[2]


class RootDiscoveryError(RuntimeError):
    """Raised when the sibling Hermes worktree root set cannot be proven
    complete — never silently degrade to a partial/single-root scan."""

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


def _scan_roots(contract: dict[str, Any]) -> list[str]:
    """Directories the architecture scanners must walk.

    Always includes the contract's own ``owner_root`` (``plugins/rhythm``).
    Also includes every ``shared_seam`` declared in the ownership contract
    (e.g. ``apps/desktop/src/contrib/**``, stripped to its directory) —
    later Rhythm slices land code there too, and a violation planted in the
    shared seam is just as real as one under ``plugins/rhythm/``. This does
    NOT claim Rhythm owns the whole seam directory for ``is_path_owned``
    purposes; it only means the seam is also scanned for these specific
    architecture violations.
    """
    roots = [contract["owner_root"]]
    ownership = load_contract("ownership")
    for seam in ownership.get("shared_seams", []):
        seam_dir = seam.rstrip("*").rstrip("/")
        if seam_dir and seam_dir not in roots:
            roots.append(seam_dir)
    return roots


def _iter_owned_files(root: Path, owner_roots: Any) -> list[Path]:
    """Yield scannable product files under one or more owner roots.

    Excludes ``<owner_root>/contracts/`` itself: that directory is this
    tooling (the marker strings it defines would otherwise flag its own
    source), not Rhythm product code.

    *owner_roots* accepts either a single root string (back-compat) or a
    list of root strings.
    """
    roots = [owner_roots] if isinstance(owner_roots, str) else list(owner_roots)
    files: list[Path] = []
    seen: set[Path] = set()
    for owner_root in roots:
        owned_dir = root / owner_root
        if not owned_dir.is_dir():
            continue
        contracts_dir = owned_dir / "contracts"
        for path in owned_dir.rglob("*"):
            if (
                path.is_file()
                and path.suffix in _SCANNABLE_SUFFIXES
                and contracts_dir not in path.parents
                and path not in seen
            ):
                seen.add(path)
                files.append(path)
    return files


def _matches_any_glob(path: Path, root: Path, patterns: Iterable[str]) -> bool:
    rel = path.relative_to(root).as_posix()
    return any(fnmatch(rel, pattern) for pattern in patterns)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


# Call names that plausibly bind/open a port in Python server code, whether
# via ``socket.bind``, ``asyncio``'s ``create_server``, or a framework's
# ``app.listen``/``server.listen``. Matched on the trailing attribute or
# bare name, so both ``sock.bind(...)`` and a locally-imported ``bind(...)``
# are covered.
_BIND_LISTEN_CALL_NAMES = frozenset({"bind", "listen"})


def _ast_int_value(node: Optional[ast.AST]) -> Optional[int]:
    """Return the literal int value of *node*, in whatever base it was
    written (decimal, hex, octal, binary all parse to the same ``int`` via
    ``ast``) — or ``None`` if it isn't a plain integer literal. Booleans
    are excluded even though ``bool`` is an ``int`` subclass in Python."""
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
    ):
        return node.value
    return None


def _iter_call_port_candidates(call: ast.Call) -> list[ast.AST]:
    """Yield AST nodes from a bind()/listen()-shaped call that plausibly
    hold a port value: every positional arg (and — for the common
    ``sock.bind((host, port))`` shape — every element of a literal
    tuple/list passed positionally) plus every keyword value."""
    candidates: list[ast.AST] = []
    for arg in call.args:
        if isinstance(arg, (ast.Tuple, ast.List)):
            candidates.extend(arg.elts)
        else:
            candidates.append(arg)
    for kw in call.keywords:
        if kw.value is not None:
            candidates.append(kw.value)
    return candidates


def _scan_python_ast_ports(path: Path, ports: set) -> list[tuple]:
    """Find forbidden-port dependencies a line-oriented text scan cannot
    see: numeric literals in any base, function-default port arguments,
    and bind()/listen()-shaped calls that pass a same-file named constant
    instead of a literal. Returns ``(lineno, port, detail)`` tuples.

    This is real source-level analysis (Python's own ``ast``), not another
    regex pattern: literal values are compared as the integers the
    interpreter would actually see, so ``0xFA1`` and ``4001`` are
    recognized as the same value with no special-casing of source syntax,
    and a bind/listen call is resolved back to its argument's value via a
    same-file constant table rather than string matching.

    Cross-file dataflow (a constant imported from outside the scanned
    roots) is out of scope — the ownership contract only scans Rhythm's
    own owned files, and following arbitrary imports would mean auditing
    code Rhythm doesn't own.
    """
    try:
        tree = ast.parse(_read_text(path), filename=str(path))
    except (SyntaxError, ValueError):
        return []

    # Same-file constant table: every simple `NAME = <int literal>` (module,
    # class, or function scope) so a bind()/listen() call elsewhere in this
    # file that only passes the constant's *name* can still be resolved.
    constants: dict = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            value = _ast_int_value(node.value)
            if isinstance(target, ast.Name) and value is not None:
                constants[target.id] = value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            value = _ast_int_value(node.value)
            if isinstance(node.target, ast.Name) and value is not None:
                constants[node.target.id] = value

    hits: list[tuple] = []

    for node in ast.walk(tree):
        value = _ast_int_value(node)
        if value is not None and value in ports:
            hits.append((node.lineno, value, "hardcoded port literal"))

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = node.args
        positional = list(args.posonlyargs) + list(args.args)
        defaulted = positional[len(positional) - len(args.defaults):] if args.defaults else []
        for arg, default in list(zip(defaulted, args.defaults)) + list(
            zip(args.kwonlyargs, args.kw_defaults)
        ):
            value = _ast_int_value(default)
            if value is not None and value in ports:
                hits.append((
                    node.lineno,
                    value,
                    f"function '{node.name}' default arg '{arg.arg}'",
                ))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            call_name = func.attr
        elif isinstance(func, ast.Name):
            call_name = func.id
        else:
            call_name = None
        if call_name not in _BIND_LISTEN_CALL_NAMES:
            continue
        for candidate in _iter_call_port_candidates(node):
            if isinstance(candidate, ast.Name) and candidate.id in constants:
                value = constants[candidate.id]
                if value in ports:
                    hits.append((
                        node.lineno,
                        value,
                        f"{call_name}() call uses named constant "
                        f"'{candidate.id}' (indirect port dependency)",
                    ))
            else:
                value = _ast_int_value(candidate)
                if value is not None and value in ports:
                    hits.append((node.lineno, value, f"{call_name}() call passes port directly"))

    return hits


def scan_port_dependency_violations(
    root: Path, contract: Optional[dict[str, Any]] = None
) -> list[str]:
    """Flag any owned file that hardcodes a host:port dependency on a
    forbidden port (e.g. Rhythm's local dev server on 4001).

    Combines a boundary-aware textual scan (catches a decimal or hex port
    literal anywhere in the file, in any host-address syntax — bracketed
    IPv6, wildcard, hostname, all keyed on the port number alone) with a
    Python AST/dataflow pass for ``.py`` files that resolves same-file
    named constants passed into bind()/listen()-shaped calls — a bypass no
    per-line text scan can see, since the literal never appears on the
    call's own line.
    """
    contract = contract or load_contract("architecture")
    owner_root = _scan_roots(contract)
    ports = contract.get("forbidden_dependencies", {}).get("ports", [])
    port_set = set(ports)
    decimal_patterns = {
        port: re.compile(r"(?<!\d)" + re.escape(str(port)) + r"(?!\d)")
        for port in ports
    }
    hex_patterns = {
        port: re.compile(
            r"(?<![0-9a-fA-F])0x0*" + format(port, "x") + r"(?![0-9a-fA-F])",
            re.IGNORECASE,
        )
        for port in ports
    }
    violations: list[str] = []
    for path in _iter_owned_files(root, owner_root):
        text = _read_text(path)
        seen: set = set()
        for lineno, line in enumerate(text.splitlines(), start=1):
            for port, pattern in decimal_patterns.items():
                if pattern.search(line) and (lineno, port) not in seen:
                    seen.add((lineno, port))
                    violations.append(
                        f"{path}:{lineno}: hardcoded port {port} dependency"
                    )
            for port, pattern in hex_patterns.items():
                if pattern.search(line) and (lineno, port) not in seen:
                    seen.add((lineno, port))
                    violations.append(
                        f"{path}:{lineno}: hardcoded port {port} dependency (hex literal)"
                    )
        if path.suffix == ".py":
            for lineno, port, detail in _scan_python_ast_ports(path, port_set):
                if (lineno, port) in seen:
                    continue
                seen.add((lineno, port))
                violations.append(f"{path}:{lineno}: {detail} — port {port}")
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
    owner_root = _scan_roots(contract)
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
    owner_root = _scan_roots(contract)
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
    owner_root = _scan_roots(contract)
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


def discover_hermes_worktree_roots(anchor: Optional[Path] = None) -> list[Path]:
    """Enumerate every worktree sharing *anchor*'s ``.git`` via ``git
    worktree list --porcelain`` — the only source that actually PROVES the
    sibling root set, rather than guessing from a ``.hermes/worktrees/**``
    directory glob that could silently miss or over-count trees.

    A validator that only ever scans its own worktree is blind to a
    violation planted in a sibling agent slice of the same feature branch —
    code that shares this repo's history and will eventually merge into
    the same tree. Fails closed with :class:`RootDiscoveryError` whenever
    that proof is incomplete: git is unavailable, the command errors, the
    output has no parseable worktree entries, or *anchor* itself isn't
    among them (which would mean the enumeration doesn't actually cover
    the root being validated). Individual stale/prunable entries (a
    worktree directory git still lists but that no longer exists on disk)
    are skipped rather than treated as a proof failure — git itself
    tracks those as prunable, not as an enumeration error.
    """
    anchor_path = Path(anchor).resolve() if anchor is not None else REPO_ROOT.resolve()
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=anchor_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RootDiscoveryError(
            f"could not enumerate sibling Hermes worktree roots: {exc}"
        ) from exc
    if result.returncode != 0:
        raise RootDiscoveryError(
            "`git worktree list --porcelain` failed "
            f"(exit {result.returncode}): {result.stderr.strip()}"
        )

    roots: list[Path] = []
    for line in result.stdout.splitlines():
        if not line.startswith("worktree "):
            continue
        candidate = Path(line[len("worktree "):].strip())
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.is_dir() and (resolved / ".git").exists():
            roots.append(resolved)

    if not roots:
        raise RootDiscoveryError(
            "`git worktree list --porcelain` returned no live worktree "
            "entries — refusing to validate an unproven root set"
        )
    if anchor_path not in roots:
        raise RootDiscoveryError(
            f"anchor root {anchor_path} is not among the enumerated "
            f"worktrees ({[str(r) for r in roots]}) — enumeration proof "
            "is inconsistent with the root being validated"
        )
    return roots


def validate_architecture_across_hermes_roots(
    anchor: Optional[Path] = None,
) -> list[str]:
    """Run :func:`validate_architecture` against every sibling Hermes
    worktree root, not just *anchor* — a violation planted in a sibling
    slice is exactly as real as one planted here. Fails closed via
    :func:`discover_hermes_worktree_roots` rather than silently degrading
    to a single-root scan when the sibling set can't be proven.
    """
    violations: list[str] = []
    for root in discover_hermes_worktree_roots(anchor):
        violations += validate_architecture(root)
    return violations
