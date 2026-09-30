"""Portable, injectable process-identity inspection.

`os.kill(pid, 0)` alone only proves *some* process holds `pid` -- on a long-
running host, PIDs are reused, so a dead worker's PID can silently become an
unrelated live process (a shell, another test run, anything) and be mistaken
for a still-running worker forever. `inspect_process` captures two
independent, cheap-to-compare signals -- the process's exact argv and its
start timestamp -- entirely through `ps`, portable across the platforms HCW
runs on and with no `/proc` dependency. Callers never treat a PID alone as
proof of identity: proof requires both signals to match what was recorded at
dispatch time.
"""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessSnapshot:
    pid: int
    args: str
    start: str


def inspect_process(pid: int) -> ProcessSnapshot | None:
    """Return a live snapshot of `pid`'s argv + start time, or `None` if the
    process does not exist (or cannot be inspected). Never raises: an
    inspection failure must always be treated as "identity not proven", not
    as an exception a caller might mishandle into treating the PID as alive.
    """
    try:
        # `-ww`: never truncate `args` to terminal width. Without it, BSD/macOS
        # `ps` silently truncates long command lines (ours easily exceed 80
        # columns), and two truncations sampled under different environments
        # can disagree -- turning a perfectly live, matching process into a
        # false identity mismatch.
        argv_result = subprocess.run(["ps", "-ww", "-o", "args=", "-p", str(pid)], text=True, capture_output=True, timeout=5)
        start_result = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], text=True, capture_output=True, timeout=5)
    except OSError:
        return None
    if argv_result.returncode or start_result.returncode:
        return None
    args = argv_result.stdout.strip()
    start = start_result.stdout.strip()
    if not args or not start:
        return None
    return ProcessSnapshot(pid=pid, args=args, start=start)


def matches_identity(pid: int, identity: dict) -> bool:
    """Verify `pid` is still the exact process `identity` (from
    `capture_snapshot_with_retry` + a deterministic expected-args suffix)
    describes.

    Matching the trailing argv suffix rather than the full `args` string is
    deliberate: some Python distributions (notably macOS Homebrew's
    framework build) `execve` themselves into a different absolute
    interpreter path shortly after starting, which changes what `ps` reports
    for argv[0] without it being a different process at all -- the pid and
    start time stay identical, and the trailing argv (our own module +
    arguments) never changes. Matching only the interpreter-independent
    suffix avoids treating that re-exec as a lost/reused pid.
    """
    if not pid or not isinstance(identity, dict):
        return False
    snapshot = inspect_process(pid)
    if snapshot is None:
        return False
    suffix = identity.get("args_suffix")
    return isinstance(suffix, str) and bool(suffix) and snapshot.args.endswith(suffix) and snapshot.start == identity.get("start")


def capture_snapshot_with_retry(pid: int, attempts: int = 15, delay: float = 0.02) -> ProcessSnapshot | None:
    """Retry `inspect_process` briefly right after spawning `pid`.

    A freshly `Popen`'d process is not always immediately visible to `ps`
    under load; without a short retry window, that race would make dispatch
    record no verifiable identity for an entirely legitimate worker and the
    next status check would wrongly reclaim it as stale.
    """
    for attempt in range(attempts):
        snapshot = inspect_process(pid)
        if snapshot is not None:
            return snapshot
        if attempt + 1 < attempts:
            time.sleep(delay)
    return None
