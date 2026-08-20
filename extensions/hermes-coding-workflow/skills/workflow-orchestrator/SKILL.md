---
name: workflow-orchestrator
description: Create and route one Hermes Coding Workflow run.
---

# Workflow orchestrator

Source mutation is blocked until `create-run`, approved design and plan, and a recorded RED check exist. Use the profile-local absolute launcher printed by `HCW_BOOTSTRAP_V1`; never substitute a checkout-relative or PATH launcher.

1. Identify the repository, board, package, scope, and run ID. Run `<absolute-hcw> create-run <repo> --run-id <id> --package <package> --scope <path> --board <board>`.
2. Read `<absolute-hcw> show <repo-or-worktree> <id>` and dispatch only the active stage's authoritative `kanban_task_ids`, `stage_profiles`, and `dispatches[stage]` identity (`stage`, `task_id`, `profile`, `provider`, `model`, `session_id`, `attempt`, `brief_hash`).
3. Pass workers only the run locator and bounded approved artifacts. Advance only with `approve-design`, `approve-plan`, `check`, `commit`, `review`, `verify`, `complete`, or `repair`.
4. `verify` is the deterministic gate that activates `live`; run `check live -- <argv>` before `complete`. A repair after changes requested uses `repair`, creates a new attempt, and stales prior review/verification.
5. Completion creates a draft handoff only. A human performs the merge.
