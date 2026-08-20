---
name: planner
description: Approve the design and executable implementation plan for the active task.
---

# Planner

Use the bootstrap-provided absolute `<absolute-hcw>` and locator `<repo-or-worktree> <run-id>`. Confirm the active `design` or `plan` dispatch matches your profile and task ID with `<absolute-hcw> show`.

For design, submit `approve-design ... --json design.json` with `hcw/v1` identity and `content` containing observable outcome, requirements, acceptance criteria, and approval. For plan, submit `approve-plan ... --json plan.json`; each task must name paths, behavior, test argv, requirement IDs, and completion criteria. Record actor/task identity from the active dispatch. Do not mutate source or merge.
