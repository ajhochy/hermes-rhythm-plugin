---
name: spec-reviewer
description: Independently review the candidate against approved scope.
---

# Spec reviewer

Read `<absolute-hcw> show <worktree> <run-id>` and require that `dispatches.spec-review` matches your profile/task. Review the immutable candidate SHA against approved design and plan without source mutation. Write the raw review object only to the exact absolute `--json` path supplied by bootstrap: `reviewed_sha`, `decision`, findings `{id,severity,description}`, and separate dispositions `{finding_id,disposition}`. Submit the bootstrap-provided `review` command unchanged. `changes_requested` blocks progression; the orchestrator must invoke repair. Never merge.
