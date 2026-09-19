"""Adversarial contracts for issue #12's three native Rhythm tools."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]


def _task(*, status="open", title="Review <untrusted> brief", notes="Private user text"):
    return {
        "id": "task-1", "title": title, "notes": notes, "status": status,
        "bucket": "today", "priority": 1, "tags": ["work"],
        "createdAt": "2026-08-21", "createdBy": "A user", "ownerId": "user-1",
        "isShared": False, "sourceType": "manual", "preferredAgent": "", "energy": "",
        "collaborators": [],
    }


@pytest.fixture
def rhythm(monkeypatch, tmp_path):
    import plugins.rhythm.tools as mod

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes" / "profiles" / "m8"))
    state = {"task": _task(), "patches": 0, "calls": []}

    class Client:
        def __init__(self, token):
            assert token == "fixture-token"

        def call(self, method, path, **kwargs):
            state["calls"].append((method, path, kwargs))
            if path == "/auth/me":
                return {"id": "user-1"}
            if path == "/workspaces/me":
                return {"id": "ws-1"}
            if path == "/dashboard/summary":
                return {"openTaskCount": 1, "threadCount": 0, "tasks": [{"id": "task-1", "title": state["task"]["title"], "notes": state["task"]["notes"], "status": "open", "bucket": "today", "dueLabel": "Today"}], "project": None, "unreadThreads": []}
            if path == "/tasks":
                return {"tasks": [state["task"] for _ in range(120)]}
            if path == "/tasks/task-1":
                return state["task"].copy()
            raise AssertionError((method, path))

        def mutate_task(self, task_id, operation, **kwargs):
            state["calls"].append(("PATCH", task_id, kwargs))
            state["patches"] += 1
            state["task"] = _task(status="done")
            return state["task"].copy()

    monkeypatch.setattr(mod.store, "connection", lambda: {
        "access_token": "fixture-token", "identity": {"id": "user-1"}, "workspace": {"id": "ws-1"},
        "generation": "connection-generation-1",
    })
    monkeypatch.setattr(mod, "RhythmClient", Client)
    monkeypatch.setattr(mod.store, "approval_scope", lambda: ("profile:m8", "connection-generation-1"))
    from gateway.session_context import set_session_vars
    session_tokens = set_session_vars(session_id="session-1")
    mod._clear_completion_receipts_for_tests()
    yield mod, state
    from gateway.session_context import clear_session_vars
    clear_session_vars(session_tokens)


def _result(raw):
    return json.loads(raw)


def test_issue_12_registers_only_the_three_native_tools_and_reads_are_bounded_untrusted(rhythm):
    mod, _ = rhythm
    assert set(mod._TOOLS) == {"rhythm_get_dashboard", "rhythm_list_tasks", "rhythm_complete_task"}

    dashboard = _result(mod.rhythm_get_dashboard({}))
    listing = _result(mod.rhythm_list_tasks({"max_results": 1000}))
    assert dashboard["untrusted_user_text"] is True
    assert dashboard["tasks"][0]["text"]["title"] == "Review <untrusted> brief"
    assert listing["untrusted_user_text"] is True
    assert len(listing["tasks"]) == 100
    assert all(entry["text"]["notes"] == "Private user text" for entry in listing["tasks"])


def test_issue_12_registers_exact_native_surface(rhythm):
    mod, _ = rhythm
    registered = []
    class Context:
        def register_tool(self, **kwargs):
            registered.append(kwargs)
    mod.register_tools(Context())
    assert {entry["name"] for entry in registered} == set(mod._TOOLS)
    assert {entry["toolset"] for entry in registered} == {"rhythm"}


def test_issue_12_native_tools_discover_through_plugin_manifest(monkeypatch, tmp_path):
    """The dashboard manifest alone must not be mistaken for native discovery."""
    from hermes_cli.plugins import PluginManager

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text("plugins:\n  enabled: [rhythm]\n", encoding="utf-8")
    manager = PluginManager()
    manifests = manager._scan_directory(REPO_ROOT / "plugins", source="bundled")
    manifest, = [entry for entry in manifests if entry.key == "rhythm"]
    manager._collect_directory_manifests = lambda: [manifest]
    manager._scan_entry_points = lambda: []
    try:
        manager.discover_and_load()
        loaded = manager._plugins["rhythm"]
        assert loaded.enabled is True
        assert set(loaded.tools_registered) == {
            "rhythm_get_dashboard", "rhythm_list_tasks", "rhythm_complete_task",
        }
    finally:
        manager.unload()


@pytest.mark.parametrize("decision", [None, False])
def test_issue_12_missing_or_denied_acp_never_patches(rhythm, monkeypatch, decision):
    mod, state = rhythm
    monkeypatch.setattr(mod, "get_edit_approval_requester", lambda: None if decision is None else (lambda _: False))
    result = _result(mod.rhythm_complete_task({"task_id": "task-1"}, task_id="attacker-controlled-task-id"))
    assert result["error"] in {"acp_approval_required", "acp_approval_denied"}
    assert state["patches"] == 0


def test_issue_12_allow_once_binds_exact_prestate_and_single_use_receipt(rhythm, monkeypatch):
    mod, state = rhythm
    proposals = []
    monkeypatch.setattr(mod, "get_edit_approval_requester", lambda: lambda proposal: proposals.append(proposal) or True)
    result = _result(mod.rhythm_complete_task({"task_id": "task-1"}, task_id="attacker-controlled-task-id"))
    assert result["status"] == "done"
    assert state["patches"] == 1
    assert proposals[0].tool_name == "rhythm_complete_task"
    assert proposals[0].arguments == {
        "task_id": "task-1", "action": "complete", "payload": {"status": "done"},
        "profile": "profile:m8", "session_id": "session-1",
        "generation": "connection-generation-1",
        "prestate_digest": next(iter(mod._completion_receipts.values())).prestate_digest,
        "remote_context_digest": next(iter(mod._completion_receipts.values())).remote_context_digest,
        "receipt_id": next(iter(mod._completion_receipts.values())).receipt_id,
        "expires_at": next(iter(mod._completion_receipts.values())).expires_at,
    }
    assert "fixture-token" not in json.dumps(proposals[0].arguments)
    assert "https://" not in json.dumps(proposals[0].arguments)
    assert len(mod._completion_receipts) == 1
    receipt = next(iter(mod._completion_receipts.values()))
    assert receipt.used is True
    assert receipt.action == "complete" and receipt.payload == {"status": "done"}
    assert receipt.profile == "profile:m8" and receipt.session_id == "session-1" and receipt.generation == "connection-generation-1"


def test_issue_12_changed_canonical_state_after_allow_once_performs_zero_patch(rhythm, monkeypatch):
    mod, state = rhythm
    def approve(_proposal):
        state["task"]["title"] = "changed concurrently"
        return True
    monkeypatch.setattr(mod, "get_edit_approval_requester", lambda: approve)
    result = _result(mod.rhythm_complete_task({"task_id": "task-1"}, task_id="attacker-controlled-task-id"))
    assert result["error"] == "stale_remote_state"
    assert state["patches"] == 0


@pytest.mark.parametrize(
    ("field", "altered"),
    [
        ("profile", "other-profile"),
        ("session_id", "other-session"),
        ("generation", "other-generation"),
        ("action", "reschedule"),
        ("payload", {"status": "open"}),
        ("prestate_digest", "altered"),
        ("remote_context_digest", "altered"),
        ("expires_at", 0),
        ("used", True),
    ],
)
def test_issue_12_altered_or_cross_scope_receipt_never_patches(rhythm, monkeypatch, field, altered):
    mod, state = rhythm
    def approve(_proposal):
        receipt = next(iter(mod._completion_receipts.values()))
        setattr(receipt, field, altered)
        return True
    monkeypatch.setattr(mod, "get_edit_approval_requester", lambda: approve)
    result = _result(mod.rhythm_complete_task({"task_id": "task-1"}, task_id="attacker-controlled-task-id"))
    assert result["error"] in {"stale_remote_state", "stale_confirmation"}
    assert state["patches"] == 0


def test_issue_12_ambiguous_transport_is_uncertain_without_retry_or_false_success(rhythm, monkeypatch):
    mod, state = rhythm
    from plugins.rhythm.backend.client import RhythmRemoteError
    monkeypatch.setattr(mod, "get_edit_approval_requester", lambda: lambda _: True)
    def ambiguous(*_args, **_kwargs):
        state["patches"] += 1
        raise RhythmRemoteError("timeout")
    monkeypatch.setattr(mod, "_mutate_complete", ambiguous)
    result = _result(mod.rhythm_complete_task({"task_id": "task-1"}, task_id="attacker-controlled-task-id"))
    assert result["error"] == "uncertain"
    assert state["patches"] == 1


def test_issue_12_missing_trusted_connection_scope_fails_closed_without_patch(rhythm, monkeypatch):
    mod, state = rhythm
    monkeypatch.setattr(mod.store, "approval_scope", lambda: None)
    monkeypatch.setattr(mod, "get_edit_approval_requester", lambda: lambda _: True)

    result = _result(mod.rhythm_complete_task({"task_id": "task-1"}, task_id="connection-generation-pretender"))

    assert result["error"] == "acp_approval_required"
    assert state["patches"] == 0
