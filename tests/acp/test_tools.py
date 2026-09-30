"""Tests for acp_adapter.tools — tool kind mapping and ACP content building."""

import json

from acp_adapter.edit_approval import EditProposal
from acp_adapter.tools import (
    TOOL_KIND_MAP,
    build_tool_complete,
    build_tool_start,
    build_tool_title,
    extract_locations,
    get_tool_kind,
    make_tool_call_id,
)
from acp.schema import (
    FileEditToolCallContent,
    ContentToolCallContent,
    ToolCallLocation,
    ToolCallStart,
    ToolCallProgress,
)


# ---------------------------------------------------------------------------
# TOOL_KIND_MAP coverage
# ---------------------------------------------------------------------------


COMMON_HERMES_TOOLS = ["read_file", "search_files", "terminal", "patch", "write_file", "process"]


class TestToolKindMap:
    def test_all_hermes_tools_have_kind(self):
        """Every common hermes tool should appear in TOOL_KIND_MAP."""
        for tool in COMMON_HERMES_TOOLS:
            assert tool in TOOL_KIND_MAP, f"{tool} missing from TOOL_KIND_MAP"

    def test_tool_kind_read_file(self):
        assert get_tool_kind("read_file") == "read"

    def test_tool_kind_terminal(self):
        assert get_tool_kind("terminal") == "execute"








    def test_unknown_tool_returns_other_kind(self):
        assert get_tool_kind("nonexistent_tool_xyz") == "other"


# ---------------------------------------------------------------------------
# make_tool_call_id
# ---------------------------------------------------------------------------


class TestMakeToolCallId:
    def test_returns_string(self):
        tc_id = make_tool_call_id()
        assert isinstance(tc_id, str)

    def test_starts_with_tc_prefix(self):
        tc_id = make_tool_call_id()
        assert tc_id.startswith("tc-")

    def test_ids_are_unique(self):
        ids = {make_tool_call_id() for _ in range(100)}
        assert len(ids) == 100


# ---------------------------------------------------------------------------
# build_tool_title
# ---------------------------------------------------------------------------


class TestBuildToolTitle:
    def test_terminal_title_includes_command(self):
        title = build_tool_title("terminal", {"command": "ls -la /tmp"})
        assert "ls -la /tmp" in title

    def test_terminal_title_truncates_long_command(self):
        long_cmd = "x" * 200
        title = build_tool_title("terminal", {"command": long_cmd})
        assert len(title) < 120
        assert "..." in title

    def test_read_file_title(self):
        title = build_tool_title("read_file", {"path": "/etc/hosts"})
        assert "/etc/hosts" in title


    def test_search_title(self):
        title = build_tool_title("search_files", {"pattern": "TODO"})
        assert "TODO" in title




    def test_skill_view_title_includes_skill_name(self):
        title = build_tool_title("skill_view", {"name": "github-pitfalls"})
        assert title == "skill view (github-pitfalls)"


    def test_execute_code_title_includes_first_code_line(self):
        title = build_tool_title("execute_code", {"code": "\nfrom hermes_tools import terminal\nprint('done')"})
        assert title == "python: from hermes_tools import terminal"


    def test_unknown_tool_uses_name(self):
        title = build_tool_title("some_new_tool", {"foo": "bar"})
        assert title == "some_new_tool"

    def test_titles_are_force_redacted_and_hard_bounded_for_every_argument_shape(self):
        """Titles are ACP wire data too, including every formatter-specific arg."""
        secret = "sk-abcdefghijklmnopqrstuvwx1234567890"
        cases = [
            ("terminal", {"command": f"echo {secret}"}),
            ("read_file", {"path": f"/tmp/{secret}"}),
            ("write_file", {"path": f"/tmp/{secret}"}),
            ("patch", {"mode": secret, "path": f"/tmp/{secret}"}),
            ("search_files", {"pattern": secret}),
            ("web_search", {"query": secret}),
            ("web_extract", {"urls": [{"url": f"https://x/{secret}"}]}),
            ("process", {"action": secret, "session_id": secret}),
            ("delegate_task", {"goal": secret}),
            ("session_search", {"query": secret}),
            ("memory", {"action": secret, "target": secret}),
            ("execute_code", {"code": f"print('{secret}')"}),
            ("skill_view", {"name": secret, "file_path": secret}),
            ("skill_manage", {"action": secret, "name": secret, "file_path": secret}),
            ("browser_navigate", {"url": f"https://x/{secret}"}),
            ("browser_vision", {"question": secret}),
            ("vision_analyze", {"question": secret}),
            ("image_generate", {"prompt": secret}),
            ("cronjob", {"action": secret, "job_id": secret}),
        ]
        for tool_name, args in cases:
            title = build_tool_start("tc-title", tool_name, args).title
            assert secret not in title
            assert len(title) <= 200

    def test_title_cap_applies_after_every_formatter(self):
        result = build_tool_start("tc-huge-title", "read_file", {"path": "x" * 10000})
        assert len(result.title) <= 200


# ---------------------------------------------------------------------------
# build_tool_start
# ---------------------------------------------------------------------------


class TestBuildToolStart:
    def test_build_tool_start_for_patch(self):
        """patch start should not duplicate the edit-approval diff."""
        args = {
            "path": "src/main.py",
            "old_string": "print('hello')",
            "new_string": "print('world')",
        }
        result = build_tool_start("tc-1", "patch", args)
        assert isinstance(result, ToolCallStart)
        assert result.kind == "edit"
        assert len(result.content) >= 1
        item = result.content[0]
        assert isinstance(item, ContentToolCallContent)
        assert "Approval prompt shows the diff" in item.content.text
        assert "src/main.py" in item.content.text


    def test_auto_approved_edit_start_shows_diff_content(self):
        """Auto-approved edit starts need the diff because no approval card exists."""
        args = {"path": "/tmp/acp.txt", "old_string": "old", "new_string": "new"}
        result = build_tool_start(
            "tc-auto-edit",
            "patch",
            args,
            edit_diff=EditProposal("patch", "/tmp/acp.txt", "old\n", "new\n", args),
        )

        assert isinstance(result, ToolCallStart)
        assert result.kind == "edit"
        assert len(result.content) == 1
        item = result.content[0]
        assert isinstance(item, FileEditToolCallContent)
        assert item.path == "/tmp/acp.txt"
        assert item.old_text == "old\n"
        assert item.new_text == "new\n"







    def test_terminal_command_secret_is_redacted(self):
        """The raw command line is echoed verbatim as start content today;
        an inline secret (e.g. ``export TOKEN=... && curl ...``) must be
        redacted before it reaches the ACP wire, not just the result."""
        secret = "sk-abcdefghijklmnopqrstuvwx1234567890"
        args = {"command": f"curl -H 'Authorization: Bearer {secret}' https://x"}
        result = build_tool_start("tc-term", "terminal", args)

        text = result.content[0].content.text
        assert secret not in text
        assert "curl" in text  # safe display preserved

    def test_execute_code_source_secret_is_redacted(self):
        secret = "sk-abcdefghijklmnopqrstuvwx1234567890"
        args = {"code": f"import requests\nrequests.get('https://x', headers={{'Authorization': '{secret}'}})"}
        result = build_tool_start("tc-exec", "execute_code", args)

        text = result.content[0].content.text
        assert secret not in text
        assert "requests.get" in text

    def test_write_file_diff_secret_is_redacted(self):
        secret = "sk-abcdefghijklmnopqrstuvwx1234567890"
        args = {"path": "/tmp/x.env", "content": f"API_KEY={secret}"}
        result = build_tool_start(
            "tc-write",
            "write_file",
            args,
            edit_diff=EditProposal("write_file", "/tmp/x.env", None, f"API_KEY={secret}", args),
        )

        item = result.content[0]
        assert secret not in (item.new_text or "")

    def test_generic_tool_raw_input_secret_is_redacted_and_bounded(self):
        """A generic/MCP tool (not in the polished list) sends the full
        arguments dict as ``raw_input`` with no bound today — any secret
        value in the arguments leaks verbatim, and there is no size cap."""
        secret = "sk-abcdefghijklmnopqrstuvwx1234567890"
        args = {"token": secret, "note": "x" * 10000}
        result = build_tool_start("tc-mcp", "mcp_some_server_do_thing", args)

        raw = result.raw_input
        assert raw is not None
        serialized = json.dumps(raw, default=str)
        assert secret not in serialized
        assert len(serialized) < 6000

    def test_generic_tool_raw_output_secret_is_redacted_and_bounded(self):
        secret = "sk-abcdefghijklmnopqrstuvwx1234567890"
        result = build_tool_complete(
            "tc-mcp-out", "mcp_some_server_do_thing", f"token is {secret} " + ("y" * 10000)
        )

        assert result.raw_output is not None
        assert secret not in result.raw_output
        assert len(result.raw_output) < 6000

    def test_build_tool_start_for_browser_navigate(self):
        """browser_navigate should emit a polished start event."""
        args = {"url": "https://x.com"}
        result = build_tool_start("tc-browser-start", "browser_navigate", args)
        assert isinstance(result, ToolCallStart)
        assert result.title == "navigate: https://x.com"
        assert result.kind == "fetch"
        assert result.content[0].content.text == '{\n  "url": "https://x.com"\n}'
        assert result.raw_input is None








# ---------------------------------------------------------------------------
# build_tool_complete
# ---------------------------------------------------------------------------


class TestPolishedContentRedaction:
    """A polished ``content`` block (read_file, process, search_files, ...)
    is built from formatted tool-result text, not the raw ``result`` string
    that ``raw_output`` bounds/redacts. Every one of these formatters must
    force-redact and bound its own output — a secret embedded in a file
    read, a process log, a search match, or a generic JSON field must never
    reach the ACP wire verbatim, and no formatted block may be unbounded."""

    AWS_SECRET = "AKIAIOSFODNN7EXAMPLE"
    GITHUB_SECRET = "ghp_1234567890abcdefghijklmnopqrstuvwx"
    BEARER_SECRET = "sk-abcdefghijklmnopqrstuvwx1234567890"

    def test_read_file_content_redacts_secret(self):
        result = json.dumps({"content": f"line1\nAWS_KEY={self.AWS_SECRET}\nline3", "total_lines": 3})
        r = build_tool_complete("tc-read-secret", "read_file", result, function_args={"path": "/tmp/x.env"})
        text = r.content[0].content.text
        assert self.AWS_SECRET not in text
        assert "/tmp/x.env" in text  # non-secret metadata preserved

    def test_read_file_error_message_redacts_secret(self):
        """formatter error/message path: a read failure surfaces the
        upstream error text verbatim today, which can itself carry a
        credential (e.g. an auth failure echoing the token it rejected)."""
        result = json.dumps({"error": f"permission denied for token {self.GITHUB_SECRET}"})
        r = build_tool_complete("tc-read-err", "read_file", result, function_args={"path": "/tmp/x"})
        text = r.content[0].content.text
        assert self.GITHUB_SECRET not in text
        assert "Read failed" in text

    def test_process_output_redacts_secret(self):
        result = json.dumps({"status": "completed", "output": f"token: {self.GITHUB_SECRET}"})
        r = build_tool_complete(
            "tc-process-secret", "process", result, function_args={"action": "status", "session_id": "s1"}
        )
        text = r.content[0].content.text
        assert self.GITHUB_SECRET not in text
        assert "s1" in text  # non-secret metadata preserved

    def test_search_files_match_content_redacts_secret(self):
        result = json.dumps(
            {"total_count": 1, "matches": [{"path": "a.py", "line": 1, "content": f"KEY={self.AWS_SECRET}"}]}
        )
        r = build_tool_complete("tc-search-secret", "search_files", result)
        text = r.content[0].content.text
        assert self.AWS_SECRET not in text
        assert "a.py:1" in text  # non-secret metadata preserved

    def test_browser_navigate_result_redacts_secret(self):
        """browser/media formatted result path."""
        result = json.dumps(
            {"title": "Login", "url": "https://x.com", "text": f"session token {self.BEARER_SECRET} set"}
        )
        r = build_tool_complete("tc-browser-secret", "browser_navigate", result)
        text = r.content[0].content.text
        assert self.BEARER_SECRET not in text
        assert "Login" in text  # non-secret metadata preserved

    def test_generic_structured_dict_result_redacts_secret(self):
        """structured JSON path for a tool with no dedicated formatter."""
        result = json.dumps({"success": True, "message": f"issued key {self.AWS_SECRET}", "id": "x1"})
        r = build_tool_complete("tc-generic-secret", "some_plugin_tool", result)
        text = r.content[0].content.text
        assert self.AWS_SECRET not in text
        assert "x1" in text  # non-secret metadata preserved

    def test_generic_top_level_list_result_redacts_secret(self):
        """non-string content: a top-level JSON list (not a dict, not a
        plain string) routed through the generic structured formatter."""
        result = json.dumps([{"note": f"leaked {self.AWS_SECRET}"}])
        r = build_tool_complete("tc-list-secret", "some_other_tool", result)
        text = r.content[0].content.text
        assert self.AWS_SECRET not in text

    def test_todo_start_preview_redacts_secret_in_item_content(self):
        """tool-start args: a todo item's own content can carry a secret
        a user pasted (e.g. 'rotate this key: ...')."""
        args = {"todos": [{"status": "pending", "content": f"rotate {self.AWS_SECRET}"}]}
        result = build_tool_start("tc-todo-secret", "todo", args)
        text = result.content[0].content.text
        assert self.AWS_SECRET not in text

    def test_todo_start_preview_is_bounded(self):
        """A single oversized todo item content must not ship unbounded —
        there is no per-item or total-length cap on this preview today."""
        huge = "z" * 50000
        args = {"todos": [{"status": "pending", "content": huge}]}
        result = build_tool_start("tc-todo-huge", "todo", args)
        text = result.content[0].content.text
        assert len(text) < 20000

    def test_terminal_start_command_is_bounded(self):
        huge_cmd = "echo " + "a" * 50000
        result = build_tool_start("tc-term-huge", "terminal", {"command": huge_cmd})
        text = result.content[0].content.text
        assert len(text) < 20000

    def test_skill_manage_diff_content_redacts_secret(self):
        """Diff content built from a parsed unified diff (e.g. skill_manage
        completion) bypasses the text-content formatters entirely and must
        get the same redaction/bound guarantee."""
        from acp_adapter.tools import _parse_unified_diff_content

        diff_text = (
            "--- a/skill.md\n"
            "+++ b/skill.md\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            f"+API_KEY={self.AWS_SECRET}\n"
        )
        blocks = _parse_unified_diff_content(diff_text)
        assert blocks, "expected at least one diff content block"
        assert self.AWS_SECRET not in (blocks[0].new_text or "")

    def test_start_diffs_are_redacted_and_bounded_for_patch_write_and_skills(self):
        secret = "sk-abcdefghijklmnopqrstuvwx1234567890"
        huge = "z" * 50000
        cases = [
            ("patch", {"path": "/tmp/x", "old_string": f"OLD={secret}{huge}", "new_string": f"NEW={secret}{huge}"}, EditProposal("patch", "/tmp/x", f"OLD={secret}{huge}", f"NEW={secret}{huge}", {})),
            ("write_file", {"path": "/tmp/x", "content": f"NEW={secret}{huge}"}, EditProposal("write_file", "/tmp/x", f"OLD={secret}{huge}", f"NEW={secret}{huge}", {})),
            ("skill_manage", {"action": "patch", "name": "x", "file_path": "SKILL.md", "old_string": f"OLD={secret}{huge}", "new_string": f"NEW={secret}{huge}"}, None),
            ("skill_manage", {"action": "write_file", "name": "x", "file_path": "extra.md", "file_content": f"NEW={secret}{huge}"}, None),
        ]
        for tool_name, args, edit_diff in cases:
            result = build_tool_start("tc-diff", tool_name, args, edit_diff=edit_diff)
            item = result.content[0]
            assert secret not in (item.old_text or "")
            assert secret not in (item.new_text or "")
            assert len(item.path) <= 200
            assert len(item.old_text or "") <= 20000
            assert len(item.new_text or "") <= 20000


class TestBuildToolComplete:
    def test_build_tool_complete_for_terminal(self):
        """Completed terminal call should include output text."""
        result = build_tool_complete("tc-2", "terminal", "total 42\ndrwxr-xr-x 2 root root 4096 ...")
        assert isinstance(result, ToolCallProgress)
        assert result.status == "completed"
        assert len(result.content) >= 1
        content_item = result.content[0]
        assert isinstance(content_item, ContentToolCallContent)
        assert "total 42" in content_item.content.text
        assert result.raw_output is None








    def test_build_tool_complete_marks_returncode_nonzero_as_failed(self):
        result = build_tool_complete("tc-fail", "execute_code", '{"output": "bad", "returncode": 2}')
        assert result.status == "failed"








    def test_build_tool_complete_for_search_files_formats_matches(self):
        result = build_tool_complete(
            "tc-search",
            "search_files",
            '{"total_count":2,"matches":[{"path":"README.md","line":3,"content":"TODO: fix this"},{"path":"src/app.py","line":9,"content":"needle"}],"truncated":true}\n\n[Hint: Results truncated. Use offset=12 to see more.]',
        )
        text = result.content[0].content.text
        assert "Search results" in text
        assert "Found 2 matches" in text
        assert "README.md:3" in text
        assert "TODO: fix this" in text
        assert "Results truncated" in text
        assert result.raw_output is None







    def test_build_tool_complete_generically_formats_unknown_json_dict_without_raw_output(self):
        result = build_tool_complete(
            "tc-recall-search",
            "memory_archive_search",
            '{"results":[{"id":"obs-1","status":"active","content":"Recall should render as a readable summary."}],"trust":"lower-trust archive evidence"}',
        )
        text = result.content[0].content.text
        assert "memory_archive_search result" in text
        assert "lower-trust archive evidence" in text
        assert "Recall should render as a readable summary" in text
        assert "{\"results\"" not in text
        assert result.raw_output is None









# ---------------------------------------------------------------------------
# extract_locations
# ---------------------------------------------------------------------------


class TestExtractLocations:
    def test_extract_locations_with_path(self):
        args = {"path": "src/app.py", "offset": 42}
        locs = extract_locations(args)
        assert len(locs) == 1
        assert isinstance(locs[0], ToolCallLocation)
        assert locs[0].path == "src/app.py"
        assert locs[0].line == 42

    def test_extract_locations_without_path(self):
        args = {"command": "echo hi"}
        locs = extract_locations(args)
        assert locs == []
