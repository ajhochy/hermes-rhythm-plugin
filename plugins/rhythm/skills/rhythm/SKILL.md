---
name: rhythm
description: Use the bounded Rhythm native tools after the user opts in and connects a Rhythm account.
---

# Rhythm

Use `rhythm_get_dashboard` and `rhythm_list_tasks` for read-only context.
`rhythm_complete_task` is a scoped, approval-bound mutation: state the task
and ask for confirmation before invoking it. Never request or expose access
tokens; connection setup remains in the Dashboard plugin flow.
