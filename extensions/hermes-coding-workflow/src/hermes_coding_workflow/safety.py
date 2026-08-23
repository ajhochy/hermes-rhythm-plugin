from __future__ import annotations

import hashlib
import os
import re
import secrets
import stat
import subprocess
from pathlib import Path

MAX_EVIDENCE = 4096
SECRET = re.compile(r"(?i)(?:api[_-]?key|token|password|secret)\s*(?:=|:|\s)\s*[^\s]+|-----BEGIN [A-Z ]*PRIVATE KEY-----")


def _open_bound_parent(parent: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(parent, flags)
    except OSError as exc:
        raise ValueError("path_scope_violation") from exc
    if not stat.S_ISDIR(os.fstat(fd).st_mode) or not _parent_still_bound(parent, fd):
        os.close(fd)
        raise ValueError("path_scope_violation")
    return fd


def _parent_still_bound(parent: Path, fd: int) -> bool:
    try:
        path_stat = os.stat(parent, follow_symlinks=False)
        fd_stat = os.fstat(fd)
    except OSError:
        return False
    return stat.S_ISDIR(path_stat.st_mode) and (path_stat.st_dev, path_stat.st_ino) == (fd_stat.st_dev, fd_stat.st_ino)


def open_nofollow_write_fd(path: Path) -> int:
    """Open a regular write leaf relative to one verified parent descriptor."""
    path = Path(path)
    parent_fd = _open_bound_parent(path.parent)
    try:
        try:
            fd = os.open(
                path.name,
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=parent_fd,
            )
        except OSError as exc:
            raise ValueError("path_scope_violation") from exc
        if not stat.S_ISREG(os.fstat(fd).st_mode) or not _parent_still_bound(path.parent, parent_fd):
            os.close(fd)
            raise ValueError("path_scope_violation")
        return fd
    finally:
        os.close(parent_fd)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write `data` to `path` durably and without ever writing through a
    pre-existing symlink leaf.

    Fails closed: a leaf (or parent directory) that is already a symlink is
    rejected outright rather than replaced, even though `os.replace` would
    itself be symlink-safe (it swaps the directory entry, never the
    symlink's target). The temp file is written, `fsync`'d, and atomically
    renamed into place; the parent directory is then `fsync`'d too so the
    rename itself survives a crash.
    """
    path = Path(path)
    parent = path.parent
    parent_fd = _open_bound_parent(parent)
    temp = f".tmp-{secrets.token_hex(16)}"
    temp_created = False
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=parent_fd)
        temp_created = True
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            leaf = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            leaf = None
        if leaf is not None and not stat.S_ISREG(leaf.st_mode):
            raise ValueError("path_scope_violation")
        if not _parent_still_bound(parent, parent_fd):
            raise ValueError("path_scope_violation")
        os.replace(temp, path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        temp_created = False
        os.fsync(parent_fd)
        if not _parent_still_bound(parent, parent_fd):
            raise ValueError("path_scope_violation")
    finally:
        if temp_created:
            try:
                os.unlink(temp, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        os.close(parent_fd)


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode())


def redact(value: str) -> str:
    value = SECRET.sub("[REDACTED]", value).replace(str(Path.home()), "[HOME]")
    return value[:MAX_EVIDENCE]


def safe_relative(root: Path, candidate: str | Path) -> Path:
    path = Path(candidate)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("path_scope_violation")
    resolved_root = root.resolve()
    resolved = (root / path).resolve()
    if resolved_root != resolved and resolved_root not in resolved.parents:
        raise ValueError("path_scope_violation")
    return resolved.relative_to(resolved_root)


def digest_json(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_worktree_porcelain(output: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in output.splitlines():
        if not line:
            if current:
                entries.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        current[key] = value
    if current:
        entries.append(current)
    return entries


def validate_controlled_worktree(repo: Path, worktree_path: str, *, run_id: str, attempt: int, expected_branch: str) -> Path:
    """Reject any Claude CLI cwd that is not a real, currently-registered git
    worktree with the exact expected HCW identity.

    The only legal Claude Code cwd is a real, non-symlinked directory
    directly under ``<repo>/.worktrees`` named exactly ``hcw-<run_id>-
    <attempt>`` -- the same controlled root and naming convention
    ``create_run``/``repair`` use -- AND one that ``git worktree list
    --porcelain`` (for this exact repo) currently registers on
    ``expected_branch``. A plain ``mkdir`` under the controlled root, a
    worktree removed out-of-band, or one checked out to the wrong branch are
    all rejected: none of those are proof that this worktree is the one
    ``create_run``/``repair`` actually created and dispatch is authorized to
    use as a Claude Code CLI cwd.
    """
    controlled_root = repo / ".worktrees"
    if controlled_root.is_symlink():
        raise ValueError("path_scope_violation")
    path = Path(worktree_path)
    if path.is_symlink():
        raise ValueError("path_scope_violation")
    resolved = path.resolve()
    if resolved.parent != controlled_root.resolve() or not resolved.is_dir():
        raise ValueError("path_scope_violation")
    if resolved.name != f"hcw-{run_id}-{attempt}":
        raise ValueError("worktree_identity_mismatch")
    result = subprocess.run(["git", "-C", str(repo), "worktree", "list", "--porcelain"], text=True, capture_output=True)
    if result.returncode:
        raise ValueError("worktree_listing_failed")
    entries = _parse_worktree_porcelain(result.stdout)
    entry = next((e for e in entries if "worktree" in e and Path(e["worktree"]).resolve() == resolved), None)
    if entry is None:
        raise ValueError("worktree_not_registered")
    if entry.get("branch") != f"refs/heads/{expected_branch}":
        raise ValueError("worktree_branch_mismatch")
    return resolved
