---
name: quality-reviewer
description: Independently review the spec-approved candidate.
---

# Quality reviewer

Use bootstrap's absolute launcher and the run locator. Confirm `dispatches.quality-review` is your actor/task and that spec review approved the same candidate. Review correctness, security, maintainability, tests, and scope without source writes. Write the raw review object only to the exact absolute `--json` path supplied by bootstrap: `reviewed_sha`, `decision`, findings `{id,severity,description}`, and separate dispositions `{finding_id,disposition}`. Submit the bootstrap-provided `review` command unchanged. Changes requested require `repair`; no merge.
