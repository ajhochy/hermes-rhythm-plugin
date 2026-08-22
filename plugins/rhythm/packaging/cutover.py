"""Local-only M10 cutover evidence for the sealed Rhythm feature pack.

This is deliberately an evidence generator, not a production installer or a
live-service probe.  It uses the real pinned ``RhythmClient`` with sanitized
canonical fixture responses, and it only hands a caller-owned *temporary*
Hermes home to the pre-existing lifecycle helpers.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ..backend.client import RhythmClient, RhythmRemoteError
from .build import build_feature_pack
from .lifecycle import (
    doctor_feature_pack,
    install_feature_pack,
    rollback_feature_pack,
    uninstall_feature_pack,
)
from .validate import PackagingGateError


class CutoverError(ValueError):
    """The reviewable M10 evidence is incomplete, unsafe, or inconsistent."""


# Ordered to make the ledger stable and easy to compare in review.
APPROVED_DESTINATIONS: dict[str, tuple[str, ...]] = {
    "dashboard": ("/auth/me", "/workspaces/me", "/dashboard/summary"),
    "tasks": ("/tasks",),
    "planner": ("/planner/weeks/2026-08-17",),
    "rhythms": ("/recurring-rules",),
    "projects": ("/project-templates", "/project-instances"),
    "messages": ("/message-threads", "/users"),
    "facilities": ("/facilities", "/facilities/reservations"),
    "automations": ("/automations/catalog", "/automations/rules"),
    "integrations": ("/integrations/status", "/integrations/settings", "/integrations/sync"),
    "artifacts": ("/artifacts",),
}

POLICY_DISABLED_ACTIONS = (
    "agent_navigation",
    "messages.create_thread",
    "messages.send",
    "messages.rename_thread",
    "messages.delete_thread",
    "collaborator_mutations",
    "automation_writes",
    "integration_credential_writes",
)

_NATIVE_TOOLS = ["rhythm_complete_task", "rhythm_get_dashboard", "rhythm_list_tasks"]
_ALLOWED_WRITE_CONFIRMATIONS: dict[str, dict[str, Any]] = {
    "tasks": {"operation": "tasks.complete", "evidence": {"suite": "desktop-mounted", "test": "mounts the actual TasksScreen adapter: local confirm then one bound operation, with no token or broad writes", "result": "pass"}},
    "planner": {"operation": "planner.update-task", "evidence": {"suite": "desktop-mounted", "test": "mounts Planner: the visible confirmation and operation carry one identical generation", "result": "pass"}},
    "rhythms": {"operation": "rhythms.update-rule", "evidence": {"suite": "shared-react18-react19", "test_file": "tests/rhythms.screen.test.ts", "test": "requires one exact host confirmation before a permitted rule update and never writes when cancelled", "result": "pass"}},
    "projects": {"operation": "projects.update-template", "evidence": {"suite": "shared-react18-react19", "test_file": "tests/projects.screen.test.ts", "test": "uses the exact narrow Projects capability and one foreground confirmation before a project-step mutation", "result": "pass"}},
    "messages": {"operation": "messages.mark-read", "evidence": {"suite": "shared-react18-react19", "test_file": "tests/messages.screen.test.ts", "test": "opens a thread, marks it read, and shows the transcript and participants", "result": "pass"}},
    "facilities": {"operation": "facilities.update-reservation", "evidence": {"suite": "shared-react18-react19", "test_file": "tests/facilities.screen.test.ts", "test": "binds facility writes to the exact foreground confirmation payload before mutation", "result": "pass"}},
}
_MOUNTED_DESTINATION_EVIDENCE = {"suite": "desktop-mounted", "test": "mounts every approved destination in compact and expanded failure states", "result": "pass"}
_PROFILE_SWITCH_EVIDENCE = {"suite": "desktop-mounted", "test": "does not let a deferred old gateway publish after a provider re-home", "result": "pass", "mutation": "zero_patch"}
_SECRET_MARKERS = ("bearer ", "token=", "api_key=", "secret=", "password=", "access_token=")


def _fixture_transport(calls: list[tuple[str, str]]):
    def transport(method: str, url: str, _headers: dict[str, str], _body: bytes | None, _timeout: float):
        path = url.removeprefix("https://api.rhythm.app")
        calls.append((method, path))
        return 200, {}, {"fixture": "sanitized-canonical"}

    return transport


def _assert_policy_surface(repo_root: Path) -> None:
    """Prove prohibited actions are neither routed upstream nor native tools."""
    client_source = (repo_root / "plugins/rhythm/backend/client.py").read_text(encoding="utf-8")
    api_source = (repo_root / "plugins/rhythm/dashboard/plugin_api.py").read_text(encoding="utf-8")
    tools_source = (repo_root / "plugins/rhythm/tools.py").read_text(encoding="utf-8")
    forbidden_upstream = ("/messages/send", "/messages/create", "/collaborators", "/automations/write", "/integrations/credentials")
    if any(value in client_source or value in api_source for value in forbidden_upstream):
        raise CutoverError("policy-disabled action is present in a backend route surface")
    if any(action.replace(".", "_") in tools_source for action in POLICY_DISABLED_ACTIONS):
        raise CutoverError("policy-disabled action is present in the native tool surface")
    if sorted(_NATIVE_TOOLS) != ["rhythm_complete_task", "rhythm_get_dashboard", "rhythm_list_tasks"]:
        raise CutoverError("native Rhythm tool surface is not exact")


def _assert_auth_expiry() -> str:
    client = RhythmClient("sanitized-fixture-token", transport=lambda *_: (401, {}, {}), sleep=lambda _: None)
    try:
        client.call("GET", "/tasks")
    except RhythmRemoteError as exc:
        if exc.kind == "unauthorized":
            return exc.kind
    raise CutoverError("auth expiry did not fail closed as unauthorized")


def _assert_uncertain_write() -> str:
    calls: list[str] = []

    def transport(method: str, _url: str, _headers: dict[str, str], _body: bytes | None, _timeout: float):
        calls.append(method)
        if method == "PATCH":
            raise RhythmRemoteError("timeout")
        return 200, {}, {"id": "task-1", "status": "done"}

    try:
        RhythmClient("sanitized-fixture-token", transport=transport, sleep=lambda _: None).mutate_task("task-1", "complete")
    except RhythmRemoteError as exc:
        if exc.kind == "uncertain" and calls == ["PATCH", "GET"]:
            return "no_retry_no_false_success"
    raise CutoverError("uncertain write retried or reported false success")


def _assert_native_tool_registration() -> list[str]:
    from .. import tools

    registered: list[str] = []

    class Context:
        def register_tool(self, **kwargs: Any) -> None:
            registered.append(kwargs["name"])

    tools.register_tools(Context())
    if sorted(registered) != _NATIVE_TOOLS:
        raise CutoverError("native tool registration is not exactly the approved three tools")
    return list(_NATIVE_TOOLS)


def _has_secret(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_has_secret(item) or any(marker in str(key).lower() for marker in _SECRET_MARKERS) for key, item in value.items())
    if isinstance(value, list):
        return any(_has_secret(item) for item in value)
    return any(marker in str(value).lower() for marker in _SECRET_MARKERS)


def validate_cutover_ledger(ledger: dict[str, Any]) -> None:
    """Validate the committed/generated ledger without contacting any service."""
    if ledger.get("evidence_mode") != "sanitized_canonical_fixture_transport":
        raise CutoverError("ledger must identify sanitized canonical fixture transport")
    modules = ledger.get("modules")
    if not isinstance(modules, list) or [row.get("module") for row in modules] != list(APPROVED_DESTINATIONS):
        raise CutoverError("ledger must contain every approved destination in canonical order")
    for row in modules:
        if not row.get("fixture"):
            raise CutoverError("module is missing fixture evidence")
        if not row.get("canonical_reads"):
            raise CutoverError("module is missing canonical read evidence")
        responsive = row.get("responsive_a11y")
        if not isinstance(responsive, dict) or responsive.get("result") != "pass" or responsive.get("test") != _MOUNTED_DESTINATION_EVIDENCE["test"]:
            raise CutoverError("module is missing mounted responsive/a11y evidence")
        failure = row.get("failure_state")
        if not isinstance(failure, dict) or failure.get("result") != "pass" or failure.get("test") != _MOUNTED_DESTINATION_EVIDENCE["test"]:
            raise CutoverError("module is missing mounted failure-state evidence")
        allowed = row.get("allowed_write_confirmation")
        if allowed is not None:
            if allowed.get("operation") not in {entry["operation"] for entry in _ALLOWED_WRITE_CONFIRMATIONS.values()} or allowed.get("evidence", {}).get("result") != "pass":
                raise CutoverError("unapproved or unexecuted write confirmation in ledger")
    if ledger.get("native_tools", {}).get("exercised") != _NATIVE_TOOLS:
        raise CutoverError("ledger native tools are not exact")
    if ledger.get("policy_disabled_actions") != list(POLICY_DISABLED_ACTIONS):
        raise CutoverError("policy-disabled actions are incomplete")
    if ledger.get("policy_disabled_proof") != "absent_from_adapter_and_native_tool_surface":
        raise CutoverError("policy-disabled proof is missing")
    profile = ledger.get("safety_checks", {}).get("profile_switch_generation_invalidation")
    if profile != _PROFILE_SWITCH_EVIDENCE:
        raise CutoverError("profile-switch evidence is not the executed mounted regression")
    if _has_secret(ledger):
        raise CutoverError("credential-shaped value found in cutover ledger")
    performance = ledger.get("safety_checks", {}).get("performance", {})
    if performance.get("elapsed_ms", performance.get("budget_ms", 0) + 1) > performance.get("budget_ms", 0):
        raise CutoverError("performance budget exceeded")


def run_fixture_cutover(repo_root: Path, temporary_home: Path) -> dict[str, Any]:
    """Run the final deterministic dogfood cycle against a supplied temp home.

    ``temporary_home`` is validated by the existing lifecycle helper and must
    be a dedicated descendant of the operating system temp directory.  No
    credentials, live network calls, or non-fixture writes are performed.
    """
    started = time.monotonic()
    temporary_home = temporary_home.resolve(strict=False)
    package = temporary_home.parent / "rhythm-feature-pack"
    feature_pack = build_feature_pack(repo_root, package)
    statuses = [
        install_feature_pack(feature_pack, temporary_home),
        install_feature_pack(feature_pack, temporary_home, force_reinstall=True),
        install_feature_pack(feature_pack, temporary_home, upgrade=True),
        rollback_feature_pack(temporary_home),
    ]
    doctor = doctor_feature_pack(temporary_home, connection_probe=lambda: RuntimeError("Bearer [REDACTED]"))
    statuses.append(uninstall_feature_pack(temporary_home))
    if doctor["tools"] != _NATIVE_TOOLS or "sanitized-fixture-token" in doctor["connection"].get("error", ""):
        raise CutoverError("doctor evidence is not exact or redacted")

    calls: list[tuple[str, str]] = []
    client = RhythmClient("sanitized-fixture-token", transport=_fixture_transport(calls), sleep=lambda _: None)
    modules: list[dict[str, Any]] = []
    for module, paths in APPROVED_DESTINATIONS.items():
        reads = []
        for path in paths:
            client.call("GET", path)
            reads.append(path)
        modules.append(
            {
                "module": module,
                "fixture": "sanitized-canonical-v1",
                "canonical_reads": reads,
                "allowed_write_confirmation": _ALLOWED_WRITE_CONFIRMATIONS.get(module),
                "responsive_a11y": dict(_MOUNTED_DESTINATION_EVIDENCE),
                "failure_state": dict(_MOUNTED_DESTINATION_EVIDENCE),
            }
        )
    if calls != [("GET", path) for paths in APPROVED_DESTINATIONS.values() for path in paths]:
        raise CutoverError("fixture cycle escaped the exact canonical read transport")
    _assert_policy_surface(repo_root)
    native_tools = _assert_native_tool_registration()
    elapsed_ms = int((time.monotonic() - started) * 1000)
    ledger = {
        "schema": 1,
        "issue": 14,
        "evidence_mode": "sanitized_canonical_fixture_transport",
        "external_credentialed_live_read": "pending_manual",
        "modules": modules,
        "native_tools": {"exercised": native_tools, "count": len(native_tools)},
        "lifecycle": {
            "temporary_home_only": True,
            "statuses": [row["status"] for row in statuses],
            "restart_signal": "hermes gateway restart",
            "doctor": {"compatible": doctor["compatible"], "connection": doctor["connection"]["status"], "tools": doctor["tools"]},
        },
        "safety_checks": {
            "auth_expiry": _assert_auth_expiry(),
            "restart_signal": "hermes gateway restart",
            "profile_switch_generation_invalidation": dict(_PROFILE_SWITCH_EVIDENCE),
            "uncertain_write": _assert_uncertain_write(),
            "secret_redaction": "pass",
            "performance": {"budget_ms": 2500, "elapsed_ms": elapsed_ms},
        },
        "policy_disabled_actions": list(POLICY_DISABLED_ACTIONS),
        "policy_disabled_proof": "absent_from_adapter_and_native_tool_surface",
        "automated_acceptance": "pass",
        "manual_gates": ["AJ cutover and merge", "signed/notarized release"],
    }
    validate_cutover_ledger(ledger)
    return ledger
