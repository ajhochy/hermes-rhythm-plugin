---
name: recorder
description: Complete verified run metadata and hand off for manual merge.
---

# Recorder

Use the bootstrap-provided absolute launcher and `<absolute-hcw> show <worktree> <run-id>`. Confirm `dispatches.complete` actor/task identity, current candidate, deterministic verification, and live check evidence. Run `<absolute-hcw> complete <worktree> <run-id>` to persist the `hcw/v1` handoff and card completion. It may create only a draft PR handoff; a human manually merges. Do not expose paths, commands, transcripts, or secrets in summaries.
