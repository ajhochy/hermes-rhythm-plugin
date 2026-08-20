from pathlib import Path


ROOT = Path(__file__).parents[2]
ROLES = {"workflow-orchestrator", "planner", "contract-writer", "builder", "spec-reviewer", "quality-reviewer", "verifier", "recorder", "receiving-review", "branch-finishing"}
UPSTREAM = {"using-superpowers", "brainstorming", "writing-plans", "executing-plans", "subagent-driven-development", "dispatching-parallel-agents", "test-driven-development", "systematic-debugging", "requesting-code-review", "receiving-code-review", "verification-before-completion", "using-git-worktrees", "finishing-a-development-branch", "writing-skills"}


def test_hermes_role_skill_frontmatter_and_inventory():
    found = {p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md")}
    assert ROLES <= found
    for name in ROLES:
        text = (ROOT / "skills" / name / "SKILL.md").read_text()
        assert text.startswith("---\nname:") and "description:" in text.split("---", 2)[1]


def test_complete_pinned_upstream_inventory_and_notice():
    found = {p.parent.name for p in (ROOT / "vendor" / "superpowers" / "skills").glob("*/SKILL.md")}
    assert found == UPSTREAM
    notice = (ROOT / "vendor" / "superpowers" / "NOTICE").read_text()
    assert "b36e0829c6d0140e93cfef2ca599b1b07d4a7797" in notice and "MIT" in notice
