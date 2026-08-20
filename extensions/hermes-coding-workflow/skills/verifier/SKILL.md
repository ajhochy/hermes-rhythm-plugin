---
name: verifier
description: Run fresh deterministic and live gates for the candidate.
---

# Verifier

Use bootstrap's absolute `<absolute-hcw>` and show the run locator. Confirm the active verify/live dispatch identity, clean candidate SHA, approved reviews, and planned commands. Record deterministic evidence with `<absolute-hcw> check <worktree> <run-id> full -- <argv>` and `security`; then run `<absolute-hcw> verify <worktree> <run-id>`. This deterministic gate activates `live`; record real acceptance with `<absolute-hcw> check <worktree> <run-id> live -- <argv>`. Never use mocked/provider-side claims, mutation, or merge.
