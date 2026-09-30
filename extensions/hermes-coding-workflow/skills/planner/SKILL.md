---
name: planner
description: Approve the design and executable implementation plan for the active task.
---

# Planner

Use the bootstrap-provided absolute `<absolute-hcw>` and locator `<repo-or-worktree> <run-id>`. Confirm the active `design` or `plan` dispatch matches your profile and task ID with `<absolute-hcw> show`.

Write the raw JSON payload only to the exact absolute `--json` path supplied by bootstrap; no other metadata or source path is writable. For design, the object must contain exactly `observable_outcome`, non-empty `requirements` entries `{id,description}`, non-empty `acceptance_criteria`, and `approved: true`. For plan, the object must contain exactly `tasks`, `commands`, and `approved: true`; each task contains exactly `id`, `description`, `paths`, `test_command`, and `requirement_ids`, and each of the `red`, `green`, `full`, `security`, and `live` command entries contains exactly `argv` and `requirement_ids`. The RED and GREEN `argv` values must match and the commands must cover every approved requirement ID. Submit the bootstrap-provided `approve-design` or `approve-plan` command unchanged. Do not mutate source or merge.
