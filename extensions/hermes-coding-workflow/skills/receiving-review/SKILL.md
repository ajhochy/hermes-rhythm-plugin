---
name: receiving-review
description: Resolve review findings through a new repair attempt.
---

# Receiving review

Read `<absolute-hcw> show <worktree> <run-id>` and preserve each reviewer's identity, finding descriptions, and separate dispositions. Verify each changes-requested finding. If any valid change is needed, the authorized repair actor runs `<absolute-hcw> repair <repo-or-worktree> <run-id>`, then the new `dispatches` map supplies fresh task identities; repeat RED, green, commit, and reviews. Do not overwrite prior evidence or merge.
