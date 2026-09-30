from pathlib import Path
from typing import Sequence
import json
import subprocess

from hermes_coding_workflow.adapters import KanbanAdapter
from hermes_coding_workflow.contracts import PROFILES, STAGES


def test_graph_uses_plain_language_titles_and_keeps_ids_in_metadata(tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        call = tuple(argv)
        calls.append(call)
        if "create" in call and "--body" in call:
            body = json.loads(call[call.index("--body") + 1])
            return subprocess.CompletedProcess(call, 0, json.dumps({"id": f"task-{body['stage']}"}), "")
        return subprocess.CompletedProcess(call, 0, "", "")

    adapter = KanbanAdapter(tmp_path, "plain-titles", runner)
    run_id = "t_81f59d6c"
    goal = "GitHub issue intake"
    adapter.graph(run_id, "feature/plain-titles", tmp_path, PROFILES, goal=goal)

    creates = [call for call in calls if "create" in call and "--body" in call]
    assert len(creates) == len(STAGES)
    expected = {
        "design": "Design: GitHub issue intake",
        "plan": "Plan: GitHub issue intake",
        "red": "Write failing tests: GitHub issue intake",
        "green": "Implement: GitHub issue intake",
        "spec-review": "Review requirements: GitHub issue intake",
        "quality-review": "Review code quality: GitHub issue intake",
        "verify": "Verify: GitHub issue intake",
        "live": "Test live: GitHub issue intake",
        "complete": "Complete: GitHub issue intake",
    }
    for call in creates:
        title = call[call.index("create") + 1]
        body = json.loads(call[call.index("--body") + 1])
        assert title == expected[body["stage"]]
        assert run_id not in title
        assert body["run_id"] == run_id
        assert f"hcw:{run_id}:attempt-1:{body['stage']}" in call


def test_plain_language_title_is_single_line_and_bounded(tmp_path: Path) -> None:
    adapter = KanbanAdapter(tmp_path, "plain-titles", lambda argv, cwd: subprocess.CompletedProcess(argv, 0, "{}", ""))
    title = adapter._card_title("green", "  A long\n\t user-visible\x1b[2J\x00 outcome\u202e " + "x" * 200)
    assert title.startswith("Implement: A long user-visible [2J outcome ")
    assert "\n" not in title and "\t" not in title
    assert "\x1b" not in title and "\x00" not in title and "\u202e" not in title
    assert len(title) <= 111


def test_plain_language_title_handles_non_string_goal(tmp_path: Path) -> None:
    adapter = KanbanAdapter(tmp_path, "plain-titles", lambda argv, cwd: subprocess.CompletedProcess(argv, 0, "{}", ""))
    assert adapter._card_title("green", None) == "Implement: requested change"  # type: ignore[arg-type]