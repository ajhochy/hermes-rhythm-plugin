"""Rhythm-backed native session-policy provider."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import re
import threading
import uuid
from typing import Any

from agent import host_capabilities
from agent.session_policy import UnsupportedPolicy, register_session_policy_provider

from .agent_bridge import BridgeClient, BridgeError


_INTERACTIVE_RE = re.compile(
    r"^rhythm-shared-agent:v1:([A-Za-z0-9][A-Za-z0-9._-]{0,127})@(\d{1,15})$"
)
_JOB_RE = re.compile(r"^rhythm-job:v1:([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$")
_active_claim: ContextVar[tuple[str, str] | None] = ContextVar("rhythm_worker_claim", default=None)
_registration_lock = threading.RLock()
_provider_dispose = None


def _unsupported(exc: BridgeError) -> UnsupportedPolicy:
    if exc.code in {"bridge_capability_unknown", "bridge_unavailable"}:
        return UnsupportedPolicy("bridge_unavailable")
    if exc.code == "bridge_rate_limited":
        return UnsupportedPolicy("rate_limited")
    return UnsupportedPolicy(exc.code)


@contextmanager
def worker_claim(job_id: str, lease_token: str):
    token = _active_claim.set((job_id, lease_token))
    try:
        yield
    finally:
        _active_claim.reset(token)


class RhythmSessionPolicyProvider:
    def __init__(self, client: BridgeClient | None = None):
        self._client = client or BridgeClient()

    def resolve(
        self,
        selection: str,
        *,
        session_id: str,
        profile_id: str,
        runtime_generation: str,
        transport,
        cwd: str | None = None,
    ) -> tuple[dict, str]:
        del runtime_generation
        if profile_id != "default":
            raise UnsupportedPolicy("profile_unsupported")
        if host_capabilities.get("rhythm_bridge") is None:
            raise UnsupportedPolicy("bridge_unavailable")

        interactive = _INTERACTIVE_RE.fullmatch(selection)
        delegated = _JOB_RE.fullmatch(selection)
        if interactive is not None:
            revision = int(interactive.group(2))
            if revision > 2_147_483_647:
                raise UnsupportedPolicy("selection_invalid")
            body = {
                "sessionKey": session_id,
                "cwd": cwd,
                "launchKind": "interactive",
                "acceptVersions": [2],
                "agentId": interactive.group(1),
                "expectedRevision": revision,
            }
        elif delegated is not None:
            from tui_gateway.session_driver import is_driver_transport

            job_id = delegated.group(1)
            try:
                if str(uuid.UUID(job_id)) != job_id:
                    raise ValueError
            except ValueError:
                raise UnsupportedPolicy("selection_invalid") from None
            claim = _active_claim.get()
            if not is_driver_transport(transport) or claim is None or claim[0] != job_id:
                raise UnsupportedPolicy("transport_not_allowed")
            body = {
                "sessionKey": session_id,
                "cwd": cwd,
                "launchKind": "delegated",
                "acceptVersions": [2],
                "jobId": job_id,
                "leaseToken": claim[1],
            }
        else:
            raise UnsupportedPolicy("selection_invalid")

        try:
            response = self._client.call("projection.issue", body=body)
        except BridgeError as exc:
            raise _unsupported(exc) from exc
        snapshot = response.get("snapshot")
        owner_id = response.get("ownerId")
        reference = response.get("projectionId")
        if not isinstance(snapshot, dict) or not isinstance(owner_id, str) or not owner_id or not isinstance(reference, str) or not reference:
            raise UnsupportedPolicy("provider_failed")
        return snapshot, owner_id

    def restore(self, reference: str, *, lineage_root: str, profile_id: str) -> tuple[dict, str]:
        if profile_id != "default":
            raise UnsupportedPolicy("profile_unsupported")
        try:
            response = self._client.call(
                "projection.check",
                path_params={"projectionId": reference},
                body={"sessionKey": lineage_root, "includeSnapshot": True},
            )
        except BridgeError as exc:
            raise _unsupported(exc) from exc
        snapshot = response.get("snapshot")
        owner_id = response.get("ownerId")
        if not isinstance(snapshot, dict) or not isinstance(owner_id, str) or not owner_id:
            raise UnsupportedPolicy("binding_mismatch")
        return snapshot, owner_id

    def check(self, reference: str, *, lineage_root: str, profile_id: str) -> None:
        if profile_id != "default":
            raise UnsupportedPolicy("profile_unsupported")
        try:
            response = self._client.call(
                "projection.check",
                path_params={"projectionId": reference},
                body={"sessionKey": lineage_root, "includeSnapshot": False},
            )
        except BridgeError as exc:
            raise _unsupported(exc) from exc
        if response.get("ok") is not True:
            raise UnsupportedPolicy("provider_failed")


def register_shared_agent_provider() -> None:
    global _provider_dispose
    with _registration_lock:
        if _provider_dispose is None:
            _provider_dispose = register_session_policy_provider(RhythmSessionPolicyProvider())


def _reset_provider_for_tests() -> None:
    global _provider_dispose
    with _registration_lock:
        if _provider_dispose is not None:
            _provider_dispose()
            _provider_dispose = None
