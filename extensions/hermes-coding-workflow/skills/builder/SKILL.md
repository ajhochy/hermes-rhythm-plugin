---
name: builder
description: Implement exactly the active approved task after recorded RED evidence.
---

# Builder

Use the absolute launcher announced by bootstrap and `<absolute-hcw> show <repo-or-worktree> <run-id>` to verify `dispatches.green` identity and the approved task. RED evidence is mandatory before source writes. Do not implement in Hermes. Run `<absolute-hcw> dispatch-worker <repo-or-worktree> <run-id> green` exactly once, then poll `<absolute-hcw> worker-status <repo-or-worktree> <run-id> green` at bounded intervals. While state is `queued` or `running`, wait; on `failed`, do not transition HCW and call `kanban_block` with the worker note. Only on `succeeded`, record the external worker's scoped candidate through the authoritative `commit`, then run the approved GREEN argv through the authoritative `check`: `<absolute-hcw> commit <repo-or-worktree> <run-id> --message <message>` followed by `<absolute-hcw> check <repo-or-worktree> <run-id> --timeout 600 green -- <argv>`. If and only if that succeeded worker's authoritative `commit` or `check` fails while GREEN remains active, a controller retry may run `<absolute-hcw> dispatch-worker <repo-or-worktree> <run-id> green --retry-succeeded`; poll it normally and never exceed the runtime's three-attempt ceiling. Then call `kanban_complete`. Do not self-review, repair without a finding, merge, or dispatch an unbounded second worker.
