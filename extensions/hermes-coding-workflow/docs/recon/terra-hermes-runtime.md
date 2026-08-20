# Hermes v0.20.0 runtime reconnaissance

Inspected source (read-only): `/Users/ajhochhalter/.hermes/hermes-agent`,
whose [`pyproject.toml`](../../../.hermes/hermes-agent/pyproject.toml) declares
`version = "0.20.0"`. This report describes the code actually present, rather
than a proposed API. Paths below are relative to that source root unless stated
otherwise.

## Executive conclusion

Hermes already supplies a durable Kanban coordination kernel, a FastAPI
dashboard extension point, an opt-in Desktop Kanban client, profile-scoped
workers, and native Git worktree materialization. The right integration shape
is **one project-scoped board per repository**, with worktree tasks and an
explicit board `default_workdir`. The dispatcher pins each child to the exact
board DB/workspace root it claimed, avoiding cross-board/profile leakage.

It does **not** supply a standalone "repo/run/worktree revision" object or
persist a task's base/head commit SHA. A native worktree starts from `HEAD` at
creation time, but a later audit cannot prove that SHA from Hermes state alone.
Any system requiring exact commit-SHA preservation must add immutable fields
(`repo_root`, `base_sha`, `head_sha`, `branch`, `worktree_path`) and capture
them before/after work, atomically with the task/run events.

## Durable Kanban model

Implementation: `hermes_cli/kanban_db.py`.

- Board selection precedence is explicit function `connect(board=...)`, then
  `HERMES_KANBAN_BOARD`, `HERMES_KANBAN_DB`, then
  `<root>/kanban/current`, then `default`. (`HERMES_KANBAN_DB` directly pins
  the DB path in `kanban_db_path()`.)
- Default board keeps compatibility paths: `<root>/kanban.db`,
  `<root>/kanban/workspaces`, `<root>/kanban/logs`, and
  `<root>/kanban/attachments`. A non-default board is isolated at
  `<root>/kanban/boards/<slug>/{kanban.db,workspaces,logs,attachments}`;
  metadata is `board.json`.
- `create_board()`, `list_boards()`, `read_board_metadata()` and
  `write_board_metadata()` carry `slug`, display metadata,
  `default_workdir`, `project_id`, `archived`, and DB path. `remove_board()`
  archives by rename to `boards/_archived/<slug>-<timestamp>` unless asked to
  delete. `default` cannot be removed.
- `VALID_STATUSES` is `triage`, `todo`, `scheduled`, `ready`, `running`,
  `blocked`, `review`, `done`, `archived`; valid workspace kinds are `scratch`,
  `worktree`, `dir`. Writes use WAL, `BEGIN IMMEDIATE`, and CAS on task status
  / claim lock (`write_txn()`, `claim_task()`): atomic only per board DB.
- Core DTOs are dataclasses `Task`, `Run`, `Comment`, `Attachment`, `Event`
  (`kanban_db.py:904`, `1093`, `1147`, `1156`, `1170`). `Task` includes ID,
  text, assignee/status/priority, timestamps, workspace kind/path, claim
  fields, tenant, `branch_name`, `project_id`, result, retry/heartbeat/run
  data, workflow/skills/model/provider/reasoning/goal/session/block metadata.
  `Run` is returned by `_run_dict()` as run ID, task, profile, state,
  timestamps, claim/PID, outcome, summary/error/metadata.
- Graph operations are `link_tasks()`, `_would_cycle()`, `unlink_tasks()`,
  `parent_ids()`, `child_ids()`, `recompute_ready()`, and
  `_parents_satisfied()`. A child goes to `todo` while any parent is not
  `done`/`archived`; it is promoted to `ready` only after dependencies settle.
- Runs/audit/logs are `task_runs`, `task_events`, `list_runs()`, `get_run()`,
  `latest_run()`, `worker_log_path()`, and `read_worker_log()`. Worker output
  appends to `<board>/logs/<task-id>.log`, with configurable rotation.

### One board per repository, project context, and workspace pinning

`hermes_cli/projects_db.py` supplies the adjacent project registry: SQLite
`projects`, `project_folders`, `project_meta`, and `discovered_repos`;
`Project`/`ProjectFolder`, `create_project()`, `add_folder()`, `set_primary()`,
`project_for_path()`, and `branch_name_for()` are the relevant symbols.
`plugins/kanban/dashboard/plugin_api.py:_resolve_project()` connects a board to
a live project. `POST /boards` stores `project_id` and uses its `primary_path`
as `default_workdir` unless an explicit valid absolute directory is supplied.

Recommended invariant:

1. Create/register one Hermes project for each repository; set its primary
   checkout to the repository root.
2. Create exactly one Kanban board per repository, give it that `project_id`,
   and let the primary path become `default_workdir`.
3. Create coding tasks with `workspace_kind: "worktree"`; set a deterministic
   `branch_name` before dispatch. Do not use server-global "current board" as
   a desktop selection mechanism—every Desktop request passes `?board=<slug>`.

`resolve_workspace()` and `_resolve_worktree_workspace()` enforce the binding.
Without `workspace_path`, a worktree task requires the board's absolute,
Git-backed `default_workdir` and materializes
`<repo>/.worktrees/<task-id>`. With a path, it must be absolute; existing
linked worktrees are checked for the expected branch. `_ensure_git_worktree()`
runs either:

```sh
git -C <repo> worktree add <target> <branch>
git -C <repo> worktree add -b <branch> <target> HEAD
```

This is native Git worktree behavior, not a Hermes copy. It uses whatever
`HEAD` resolves to at invocation; neither `Task`, `Run`, schema, REST DTO, nor
event payload stores a Git SHA. Preserve exact SHAs by externally recording
`git -C <repo> rev-parse HEAD` before dispatch and `git -C <worktree> rev-parse
HEAD` at review/completion, or add the aforementioned fields/transition guard.

## Dispatcher, profiles, review, and failures

`dispatch_once()` / `_dispatch_once_locked()` claim ready tasks; review work is
considered only when `review_dispatch_enabled()` is true. `run_daemon()` ticks
continuously, while gateway dispatch is normally controlled by
`kanban.dispatch_in_gateway` (the standalone daemon is marked deprecated in
`hermes_cli/kanban.py`). `_default_spawn()` launches:

```sh
hermes -p <assignee> --cli --accept-hooks [--skills <name> ...] \
  [-m <model> --provider <provider>] [--reasoning <level>] \
  [--toolsets <effective-profile-tools>] chat -q 'work kanban task <id>' [-Q]
```

The child gets profile `HERMES_HOME`, `HERMES_PROFILE`, tenant, task/run/claim
metadata, `HERMES_KANBAN_DB`, `HERMES_KANBAN_WORKSPACES_ROOT`,
`HERMES_KANBAN_BOARD`, and the resolved workspace in `HERMES_KANBAN_WORKSPACE`
and `TERMINAL_CWD`. It removes inherited gateway routing context and
`HERMES_TUI`, starts a new session, and tags `HERMES_SESSION_SOURCE=kanban`.
That is the concrete profile spawning and workspace isolation contract.

`hermes_cli/profiles.py` says each profile is an independent `HERMES_HOME`.
CLI entries include `hermes profile create <name> [--clone|--clone-all]
[--no-skills] [--description]`, `list`, `use`, `describe`, `show`, `delete`,
and `rename`; profile descriptions drive Kanban routing. Profile directories
live under `<Hermes root>/profiles/<name>` and `resolve_profile_env()` is the
spawn-time resolver.

Review transition contract:

```text
ready/running --request_review()--> review
review --claim_review_task()--> running (reviewer run)
running reviewer --request_changes()--> ready|todo (restores implementing assignee)
review --reopen_review_task()--> ready|todo (restores implementer)
running/ready --complete_task()--> done
```

`request_review()` ends the implementation run as `review_requested`, emits a
`review_requested` event with implementer/reviewer provenance, and refuses to
clear a live claim unless the worker presents `expected_run_id` or the operator
uses `force=True`. `request_changes()` requires an active run claimed from
`review`, durable handoff provenance, and emits `changes_requested`.
`reopen_review_task()` re-gates parent dependencies and preserves failure
counter; completion is the success path that resets it. Review content goes
through `redact_review_value()` before storage.

Failure/recovery primitives: `heartbeat_claim()`, `release_stale_claims()`,
`enforce_max_runtime()`, `detect_stale_running()`,
`reconcile_orphaned_running()`, `detect_crashed_workers()`, `reclaim_task()`,
`check_respawn_guard()`, and `block_task()`. Typed block kinds are
`dependency`, `needs_input`, `capability`, `transient`; repeated true blocks
escalate to `triage` after `BLOCK_RECURRENCE_LIMIT=2`. The dispatcher bounds
spawn/crash/timeout retries using `consecutive_failures`. Operationally, a
missing `hermes` executable, invalid/missing profile, non-Git/default workdir,
branch collision, a dead/permission-denied PID, SQLite/file I/O, remote
unmounted attachments, or an absent dispatcher all leave diagnosable state
rather than silently succeeding.

## Dashboard plugin backend and exact scoped routes

Dashboard discovery/mounting is in `hermes_cli/web_server.py`:
`_discover_dashboard_plugins()`, `_safe_plugin_api_relpath()`,
`_plugin_api_runtime_gate`, and `_mount_plugin_api_routes()`. A dashboard
manifest API file must expose `router`; it mounts at `/api/plugins/<name>/`.
Bundled plugin APIs are trusted but honor explicit disable; user APIs require
`plugins.enabled` and not `plugins.disabled`; project-local plugin Python is
never auto-imported (only static UI), specifically to prevent a malicious repo
from gaining server code execution. Path containment is checked again before
`exec_module`.

Kanban router: `plugins/kanban/dashboard/plugin_api.py`, mounted at
`/api/plugins/kanban`. Its externally useful contract is:

| Method | Relative route | DTO / effect |
|---|---|---|
| GET | `/board?board=` | columns/tasks, events and board diagnostics |
| GET/POST/PATCH/DELETE | `/tasks/{id}` / `/tasks` | `CreateTaskBody`, `UpdateTaskBody`; create fields include title/body/assignee/priority/workspace/parents/project/model/reasoning/goal |
| POST/DELETE | `/links` | `LinkBody {parent_id, child_id}` / unlink query |
| POST | `/tasks/bulk` | `BulkTaskBody` |
| POST | `/tasks/{id}/comments` | `CommentBody` |
| GET/POST | `/tasks/{id}/attachments` | list or multipart file (25 MiB cap) |
| GET/DELETE | `/attachments/{attachment_id}` | download/delete; download verifies the resolved stored path stays below board attachments root |
| GET | `/runs/{id}`, `/runs/{id}/inspect`, `/tasks/{id}/log` | durable run, live psutil diagnostics, bounded log tail |
| POST | `/runs/{id}/terminate`, `/tasks/{id}/reclaim`, `/tasks/{id}/reassign` | controlled process/task recovery |
| POST | `/tasks/{id}/specify`, `/tasks/{id}/decompose`, `/tasks/{id}/estimate`, `/estimate` | triage/orchestration helpers |
| GET/PUT | `/orchestration` | `OrchestrationSettingsBody` |
| GET | `/diagnostics`, `/workers/active`, `/stats`, `/assignees`, `/model-options`, `/config` | observation/configuration |
| POST | `/dispatch` | immediate dispatcher nudge |
| GET/POST/PATCH/DELETE | `/boards`, `/boards/{slug}`, `/boards/{slug}/switch` | `CreateBoardBody`, `RenameBoardBody`; creation validates absolute existing workdir |
| GET | `/projects`, `/profiles`, `/home-channels` | roster/project/channel data |
| PATCH/POST | `/profiles/{name}`, `/profiles/{name}/describe-auto` | profile metadata |
| WS | `/events?board=` | board event stream; `_ws_upgrade_authorized()` validates upgrade auth |

All routes that take `board` call `_resolve_board()` and `_conn(board=...)`;
cross-board reads are not a normal API option. File attachment names are
sanitized/collision-resolved in `kanban_db`; streaming upload removes partial
files on cap breach.

## Desktop architecture and disk-plugin SDK

Bundled Desktop plugins are discovered via Vite glob in
`apps/desktop/src/contrib/plugins.ts`; Kanban is
`apps/desktop/src/plugins/kanban/plugin.tsx`, `id: 'kanban'`, opt-in by
default, and registers a `/kanban` route, sidebar item, status count, palette
actions and keybinding. `api.ts:bindApi()` persists UI selection in
plugin-scoped storage, opens `/events`, invalidates React Query cache from
events, and polls as the socketless fallback. It always appends the local
selected `?board=<slug>`, so viewing a repo board does not mutate global board
selection.

SDK contract (`apps/desktop/src/contrib/plugin.ts`): `HermesPlugin` is a default
export `{id,name?,description?,defaultEnabled?,register(ctx)}`. `PluginContext`
supplies namespaced `register`/`registerMany`, disposer tracking, `rest`,
`socket`, `storage`, `i18n`, and result-shaped OS facilities (notification,
open external URL, reveal path, clipboard). Contributions are automatically
named `<plugin-id>:<local-id>` and stamped `source: plugin:<id>`.

`ctx.rest` calls `pluginRest()` in `apps/desktop/src/hermes.ts`: it constructs
only `/api/plugins/<plugin-id><relative-path>`, rejects `..` before query/hash,
and applies the active profile scope. `ctx.socket` applies the same namespace,
uses token auth only where available, reconnects, and deliberately becomes a
no-op under OAuth—plugins must retain polling. This is a scoped API boundary,
not a general capability grant.

Disk contribution SDK: `apps/desktop/src/contrib/runtime-loader.ts` scans the
**local Electron** path `$HERMES_HOME/desktop-plugins/<name>/plugin.js` through
`desktopPluginsRoot()`, watches each file and directory, hot reloads, unloads
on removal, and falls back to a visible-tab five-second poll. It accepts plain
ESM only, rewrites `@hermes/plugin-sdk` and React imports to live shim blobs,
can verify `sha256-<base64>` integrity, validates a default `HermesPlugin`, and
contains render errors via contribution boundaries. It is explicitly **not a
sandbox**: disk JS runs in the renderer realm with app authority. Never treat
an integrity hash as trust, and do not reuse this loader for remote code
without iframe/worker/CSP/capability isolation.

## Hooks, installation, doctor, and hard boundaries

Kanban lifecycle hooks are best-effort post-commit observers via
`_fire_kanban_lifecycle_hook()` → `hermes_cli.lifecycle.invoke_hook`; bad hooks
cannot roll back a state transition. The worker explicitly sends
`--accept-hooks`, so its profile allowlist governs worker-side hooks. CLI hook
operations are `hermes hooks list|test|revoke|doctor` in `hermes_cli/hooks.py`.
The DB mutation guard `_assert_not_delegated_child_mutation()` rejects durable
Kanban mutations from delegated-child contexts; that is the actual guard, not
merely a UI restriction.

Agent plugin lifecycle commands are `hermes plugins install <identifier>
[--ref <40-char-commit-SHA>] [--enable|--no-enable]`, `enable`, `disable`,
`update`, `remove`, `list`, `capabilities`, and `doctor [path-or-id] [--ci]`.
`plugins_cmd.py:_install_plugin_core()` uses a temporary directory and atomic
replacement; `plugin_dev.py:doctor_plugin()` loads through the real scanner and
registration host, checks manifest v2/schema/declarations, valid hooks,
registered-vs-declared tools/hooks and callback `**kwargs` compatibility.
Dependencies are declared but Hermes deliberately never auto-installs Python
plugin dependencies. A commit pin exists for plugin installation/packs—not for
Kanban task source revisions.

## Isolated-HERMES_HOME verification runbook

These commands are live-safe only when pointed at a throwaway home and a
disposable test repository. They do not read or modify the real `~/.hermes`.

```sh
src=/Users/ajhochhalter/.hermes/hermes-agent
iso=$(mktemp -d /tmp/hermes-runtime.XXXXXX)
repo=$(mktemp -d /tmp/hermes-repo.XXXXXX)
git -C "$repo" init && git -C "$repo" config user.email test@example.invalid
git -C "$repo" config user.name test && touch "$repo"/README && git -C "$repo" add README && git -C "$repo" commit -m init
export HERMES_HOME="$iso" PYTHONPATH="$src"
python -m hermes_cli.main profile create implementer --no-alias --no-skills
python -m hermes_cli.main kanban boards create repo-a --default-workdir "$repo"
python -m hermes_cli.main kanban --board repo-a create 'verify worktree' --assignee implementer --workspace "worktree:$repo" --branch wt/verify
python -m hermes_cli.main kanban --board repo-a list
git -C "$repo" worktree list --porcelain
python -m hermes_cli.main plugins doctor "$src/plugins/kanban" --ci
```

If that build exposes a different CLI spelling, inspect `hermes kanban --help`
and use the `hermes_cli/kanban.py:build_parser` contract; the durable source
symbols above remain authoritative. For backend-only regression coverage, run:

```sh
HERMES_HOME="$iso" PYTHONPATH="$src" pytest -q \
  "$src/tests/plugins/test_kanban_dashboard_plugin.py" \
  "$src/tests/plugins/test_kanban_attachments.py" \
  "$src/tests/test_subprocess_home_isolation.py"
```

Do not run the dispatcher against a production board merely to test it: it may
spawn workers. In a production incident, use board-scoped `GET /runs/{id}` /
`/inspect`, then `POST /runs/{id}/terminate` or `/tasks/{id}/reclaim` with an
operator reason, inspect `/tasks/{id}/log`, and only then reassign/reopen.
