"""Tests for ACP pre-edit approval gating."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from unittest.mock import MagicMock

from acp_adapter.edit_approval import (
    AUTO_APPROVE_ASK,
    EditProposal,
    build_acp_edit_tool_call,
    clear_edit_approval_requester,
    make_acp_edit_approval_requester,
    set_edit_approval_requester,
    should_auto_approve_edit,
)
from model_tools import handle_function_call


def teardown_function() -> None:
    clear_edit_approval_requester()


def test_acp_permission_tool_call_uses_edit_kind_and_diff_content():
    proposal = EditProposal(
        tool_name="write_file",
        path="demo.txt",
        old_text="old\n",
        new_text="new\n",
        arguments={"path": "demo.txt", "content": "new\n"},
    )

    tool_call = build_acp_edit_tool_call(proposal)

    assert tool_call.kind == "edit"
    assert tool_call.status == "pending"
    assert tool_call.rawInput == {"tool": "write_file", "arguments": proposal.arguments}
    assert len(tool_call.content) == 1
    diff = tool_call.content[0]
    assert diff.path == "demo.txt"
    assert diff.oldText == "old\n"
    assert diff.newText == "new\n"


def test_acp_permission_diff_is_redacted_and_bounded():
    secret = "sk-abcdefghijklmnopqrstuvwx1234567890"
    proposal = EditProposal(
        tool_name="patch",
        path="/tmp/x",
        old_text=f"OLD={secret}" + "x" * 50000,
        new_text=f"NEW={secret}" + "x" * 50000,
        arguments={},
    )

    tool_call = build_acp_edit_tool_call(proposal)
    diff = tool_call.content[0]

    assert secret not in (diff.oldText or "")
    assert secret not in (diff.newText or "")
    assert len(diff.oldText or "") <= 20000
    assert len(diff.newText or "") <= 20000








def test_requester_exception_denies_and_does_not_mutate(tmp_path):
    target = tmp_path / "sample.txt"
    target.write_text("before\n", encoding="utf-8")

    def boom(_proposal):
        raise RuntimeError("zed disconnected")

    set_edit_approval_requester(boom)

    result = json.loads(
        handle_function_call(
            "write_file",
            {"path": str(target), "content": "after\n"},
            task_id="acp-edit-exception",
        )
    )

    assert "error" in result
    assert "Edit approval denied" in result["error"]
    assert target.read_text(encoding="utf-8") == "before\n"


def test_patch_replace_rejection_does_not_mutate(tmp_path):
    target = tmp_path / "sample.txt"
    target.write_text("alpha\nbeta\n", encoding="utf-8")

    set_edit_approval_requester(lambda _proposal: False)

    result = json.loads(
        handle_function_call(
            "patch",
            {
                "mode": "replace",
                "path": str(target),
                "old_string": "beta\n",
                "new_string": "gamma\n",
            },
            task_id="acp-patch-reject",
        )
    )

    assert "error" in result
    assert "Edit approval denied" in result["error"]
    assert target.read_text(encoding="utf-8") == "alpha\nbeta\n"








def test_default_ask_policy_never_auto_approves_regardless_of_path(tmp_path):
    """The default/unset policy is deny-by-default: write capability is only
    ever granted by an explicit per-call decision, never silently by omission."""
    workspace_file = tmp_path / "src.py"

    assert not should_auto_approve_edit(
        EditProposal("write_file", str(workspace_file), None, "x", {}),
        AUTO_APPROVE_ASK,
        str(tmp_path),
    )
    assert not should_auto_approve_edit(
        EditProposal("write_file", str(workspace_file), None, "x", {}),
        None,
        str(tmp_path),
    )


def test_acp_edit_requester_never_offers_a_persistent_option():
    """The ACP edit-approval requester must only ever offer a single-shot
    allow or a deny — never a persistent/always-allow option. Any standing
    write capability can only come from the separate, policy-gated
    auto-approve check, not from the permission prompt itself."""
    import asyncio
    from concurrent.futures import Future
    from unittest.mock import patch

    from acp.schema import AllowedOutcome, RequestPermissionResponse

    loop = MagicMock(spec=asyncio.AbstractEventLoop)
    request_permission = MagicMock(name="request_permission")
    future = MagicMock(spec=Future)
    future.result.return_value = RequestPermissionResponse(
        outcome=AllowedOutcome(option_id="allow_once", outcome="selected"),
    )

    captured = {}

    def _schedule(coro, passed_loop):
        captured["coro"] = coro
        return future

    proposal = EditProposal(
        tool_name="write_file",
        path="demo.txt",
        old_text=None,
        new_text="new\n",
        arguments={"path": "demo.txt", "content": "new\n"},
    )

    with patch("agent.async_utils.asyncio.run_coroutine_threadsafe", side_effect=_schedule):
        requester = make_acp_edit_approval_requester(
            request_permission, loop, session_id="s1",
        )
        requester(proposal)

    captured["coro"].close()
    _, kwargs = request_permission.call_args
    option_ids = {option.option_id for option in kwargs["options"]}
    option_kinds = {option.kind for option in kwargs["options"]}
    assert option_ids == {"allow_once", "deny"}
    assert "allow_always" not in option_kinds
    assert "reject_always" not in option_kinds


def test_workspace_auto_approval_allows_workspace_and_tmp_but_not_sensitive(tmp_path):
    workspace_file = tmp_path / "src.py"
    # Use tempfile.gettempdir() so this test exercises the same code path on
    # Linux (`/tmp`), macOS (`/private/var/folders/...`) and Windows
    # (`%LOCALAPPDATA%\Temp`). Before the fix this branch only worked on Linux.
    tmp_file = Path(tempfile.gettempdir()) / "hermes-acp-auto-approve-test.txt"
    env_file = tmp_path / ".env"

    assert should_auto_approve_edit(
        EditProposal("write_file", str(workspace_file), None, "x", {}),
        "workspace_session",
        str(tmp_path),
    )
    assert should_auto_approve_edit(
        EditProposal("write_file", str(tmp_file), None, "x", {}),
        "workspace_session",
        str(tmp_path),
    )
    assert not should_auto_approve_edit(
        EditProposal("write_file", str(env_file), None, "SECRET=x", {}),
        "session",
        str(tmp_path),
    )
