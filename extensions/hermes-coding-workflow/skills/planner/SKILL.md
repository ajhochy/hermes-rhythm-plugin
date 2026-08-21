---
name: planner
description: Approve the design and executable implementation plan for the active task.
---

# Planner

Use the bootstrap-provided absolute `<absolute-hcw>` and locator `<repo-or-worktree> <run-id>`. Confirm the active `design` or `plan` dispatch matches your profile and task ID with `<absolute-hcw> show`.

Write the raw JSON payload only to the exact absolute `--json` path supplied by bootstrap; no other metadata or source path is writable. For design, the object must contain exactly `observable_outcome`, non-empty `requirements` entries `{id,description}`, non-empty `acceptance_criteria`, and `approved: true`. For plan, the object must contain exactly `tasks`, `commands`, and `approved: true`; each task names paths, behavior, test argv, and requirement IDs, and `commands` covers `red`, `green`, `full`, `security`, and `live`. Submit the bootstrap-provided `approve-design` or `approve-plan` command unchanged. Do not mutate source or merge.
