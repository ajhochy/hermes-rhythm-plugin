---
name: contract-writer
description: Create an executable contract and record genuine RED evidence.
---

# Contract writer

Read the run locator with the bootstrap-provided absolute `<absolute-hcw> show <repo-or-worktree> <run-id>` and verify `dispatches.red` is your profile/task/session. Do not author tests in Hermes. Run `<absolute-hcw> dispatch-worker <repo-or-worktree> <run-id> red` exactly once, then poll `<absolute-hcw> worker-status <repo-or-worktree> <run-id> red` at bounded intervals. While state is `queued` or `running`, wait; on `failed`, do not transition HCW and call `kanban_block` with the worker note. Only on `succeeded`, run the planned failing argv through the authoritative `check`: `<absolute-hcw> check <repo-or-worktree> <run-id> --timeout 600 red -- <argv>`. It must fail for the contract behavior, not setup. The persisted `hcw/v1` evidence supplies actor `{profile,task_id}`, command, SHA, artifact hash, and evidence hash. Then call `kanban_complete`. Do not implement, commit, approve, merge, or dispatch a second worker.
