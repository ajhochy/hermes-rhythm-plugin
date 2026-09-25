"""Rhythm plugin-native registration."""

from __future__ import annotations

import threading
import weakref

_registration_lock = threading.RLock()
_registered_contexts: weakref.WeakSet = weakref.WeakSet()
_process_registered = False


def register_tools(ctx) -> None:
    from .tools import register_tools as register_legacy_tools

    register_legacy_tools(ctx)


def register_bridge_tools(ctx) -> None:
    from .bridge_tools import register_bridge_tools as register_shared_tools

    register_shared_tools(ctx)


def register_shared_agent_provider() -> None:
    from .shared_agents import register_shared_agent_provider as register_provider

    register_provider()


def start_delegation_worker():
    from .delegation_worker import start_delegation_worker as start_worker

    return start_worker()


def register(ctx) -> None:
    global _process_registered
    with _registration_lock:
        if ctx in _registered_contexts:
            return
        if not _process_registered:
            register_shared_agent_provider()
            start_delegation_worker()
            _process_registered = True
        register_tools(ctx)
        register_bridge_tools(ctx)
        _registered_contexts.add(ctx)


def _reset_shared_agent_registration_for_tests() -> None:
    global _process_registered, _registered_contexts
    with _registration_lock:
        _process_registered = False
        _registered_contexts = weakref.WeakSet()
