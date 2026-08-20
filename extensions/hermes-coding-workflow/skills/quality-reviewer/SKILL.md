---
name: quality-reviewer
description: Independently review the spec-approved candidate.
---

# Quality reviewer

Use bootstrap's absolute launcher and the run locator. Confirm `dispatches.quality-review` is your actor/task and that spec review approved the same candidate. Review correctness, security, maintainability, tests, and scope without writes. Submit the same structured `hcw/v1` review shape through `<absolute-hcw> review <worktree> <run-id> --json review.json`; findings and dispositions remain separate. Changes requested require `repair`; no merge.
