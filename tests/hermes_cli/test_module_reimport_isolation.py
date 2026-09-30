"""`reimported_hermes_cli()` must leave sys.modules exactly as it found it.

Four kanban fixtures needed a fresh HERMES_HOME to be re-resolved at import
time, so each did:

    for mod in list(sys.modules):
        if mod.startswith("hermes_cli") or ...:
            del sys.modules[mod]
    from hermes_cli import kanban_db

and never restored anything. The re-import installs a NEW module object for
the rest of the session, so any later test that captured a reference at its
own import time — or any autouse fixture that patched the old object — was
silently operating on a dead module. That is what made 9 kanban tests fail
only in a full `-k kanban` run while passing in isolation: `tests/conftest`'s
`_kanban_write_guard` patched one `kanban_db` object while
`test_kanban_write_guard` exercised another, so the guard "DID NOT RAISE".
"""
from __future__ import annotations

import sys

import tests.conftest as _conftest


PREFIXES = ("hermes_cli", "hermes_state")
EXTRA = {"hermes_constants"}


def _snapshot() -> dict:
    return {
        name: mod for name, mod in sys.modules.items()
        if name.startswith(PREFIXES) or name in EXTRA
    }


def test_module_objects_are_identical_after_the_context_exits():
    import hermes_cli.kanban_db  # noqa: F401  (ensure something is loaded)
    before = _snapshot()
    assert before, "expected hermes_cli modules to be imported already"

    with _conftest.reimported_hermes_cli():
        from hermes_cli import kanban_db as fresh
        # Inside the context the caller genuinely gets a NEW object, which is
        # the whole point of the purge.
        assert fresh is not before["hermes_cli.kanban_db"]

    after = _snapshot()
    assert set(after) == set(before)
    for name, mod in before.items():
        assert after[name] is mod, f"{name} was not restored to its original object"


def test_modules_imported_inside_the_context_do_not_leak():
    before = _snapshot()
    with _conftest.reimported_hermes_cli():
        from hermes_cli import kanban_decompose  # noqa: F401
    after = _snapshot()
    assert set(after) == set(before)


def test_restores_even_when_the_body_raises():
    before = _snapshot()
    try:
        with _conftest.reimported_hermes_cli():
            from hermes_cli import kanban_db  # noqa: F401
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    after = _snapshot()
    assert set(after) == set(before)
    for name, mod in before.items():
        assert after[name] is mod
