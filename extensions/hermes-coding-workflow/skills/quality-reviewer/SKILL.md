---
name: quality-reviewer
description: Independently review the spec-approved candidate.
---

# Quality reviewer

Use bootstrap's absolute launcher and the run locator. Confirm `dispatches.quality-review` is your actor/task and that spec review approved the same candidate. Run `<absolute-hcw> dispatch-worker <repo-or-worktree> <run-id> quality-review` exactly once, then poll `<absolute-hcw> worker-status <repo-or-worktree> <run-id> quality-review` at bounded intervals. While state is `queued` or `running`, wait; on `failed`, do not transition HCW and call `kanban_block` with the worker note. Only on `succeeded`, read the recorded worker output and encode its review into the raw object at the exact absolute `--json` path supplied by bootstrap: `reviewed_sha`, `decision`, findings `{id,severity,description}`, and separate dispositions `{finding_id,disposition}`. Submit the authoritative `review` command unchanged, then call `kanban_complete`. Make no source writes; changes requested require `repair`; no merge or second dispatch.
