# PAUSED: HCW Bootstrap Guard Handoff

**Paused by user:** 2026-08-20, after the second full verification gate. Do not resume automatically.

## Repository state

- Worktree: `/Users/ajhochhalter/.hermes/worktrees/hermes-rhythm-plugin/oauth-tier-routing`
- Branch: `fix/oauth-tier-routing`
- HCW extension: `extensions/hermes-coding-workflow/`
- Bootstrap source files changed:
  - `extensions/hermes-coding-workflow/plugins/hermes-coding-workflow/__init__.py`
  - `extensions/hermes-coding-workflow/tests/plugin/test_native_plugins.py`
- Changes remain uncommitted and unpushed.
- The broader branch also contains the pending Claude CLI adapter. Do **not** run the full installer merely to deploy this guard; that would install unrelated, not-yet-released adapter changes.

## Confirmed original defect

With `HERMES_KANBAN_TASK=t_81f59d6c` and missing `HCW_RUN_ID`/`HERMES_PROFILE`, the installed hook rejected the required initial terminal call as `incomplete workflow identity` before `hcw create-run` could create lifecycle state.

The source now has a narrow bootstrap predicate. It permits only when all of these hold:

- terminal command uses this plugin's installed runtime launcher;
- subcommand is `create-run`;
- `--run-id` occurs exactly once and equals `HERMES_KANBAN_TASK`;
- an inherited `HCW_RUN_ID`, if present, also equals the task ID;
- run ID syntax is valid;
- the target repo is the current assigned worktree;
- neither the lifecycle locator nor target run manifest exists;
- no shell chaining/redirection tokens are present.

Normal post-bootstrap lifecycle, registered-worktree, task/profile/stage, and mutation restrictions remain unchanged.

## Regression coverage

The requested cases are implemented and pass:

1. Dispatcher-style partial identity permits a valid matching `create-run`.
2. Full identity without a locator permits the same bootstrap.
3. Mismatched `--run-id` is blocked.
4. Non-HCW terminal mutation remains blocked.
5. Post-bootstrap source mutation still requires full registered lifecycle state.

Additional live-derived regression:

6. First-turn bootstrap context must include the actual cwd, Kanban task ID, board, package, and complete required `create-run` shape, and must tell the worker not to omit arguments or prefix environment assignments.

The existing lifecycle guard contract also remains green. Latest full Python suite passed, Node/Desktop tests passed 3/3, production build passed, Python compilation passed, and `git diff --check` passed.

## Live installation state

A first targeted hook revision was installed transactionally across these managed profiles:

- `hcw-dev`
- `dev-planner`
- `dev-contract`
- `dev-builder`
- `dev-spec-reviewer`
- `dev-quality-reviewer`
- `dev-verifier`
- `dev-recorder`

All eight installed copies currently have:

```text
sha256 b323ed364fcb28a713e61d0bbab44cae85b3f53bb8e97fcca614bce24f13988b
```

Fresh-process probes against that installed revision proved matching partial/full bootstrap calls are allowed and mismatched/non-HCW calls are blocked.

The current source has a later revision with complete first-turn command guidance:

```text
sha256 67a43d89f7ac9d987769eb68e5289fe1762a99ae755e1154c912bf2d72359437
```

**That later source revision is tested but is not installed.**

## Kanban retry state

Card:

```text
t_81f59d6c — Build GitHub issue → Kanban intake and HCW routing automation
```

After installing the first guard revision, run 2 spawned in `hcw-dev`. The guard repair itself loaded, but the worker invoked:

```text
.../runtime/bin/hcw create-run
```

with no required arguments, then tried the same bare command with inline environment assignments. Both calls correctly remained blocked. The run entered the block-loop limit and the card moved to `triage` after two blocked attempts. No HCW locator or run manifest was created and the card worker modified no repository files.

Run-2 transcript:

```text
@session:hcw-dev/20260820_165700_38afa4
```

## Independent review received after pause

`deleg_2a527a41` reviewed the pre-bootstrap dirty candidate at HEAD `e08c44073daba3aeb81ea68092e4eaab2cb491c7` and returned **FAIL**. Its reviewed fingerprint was:

```text
8544cb7512d67bb958e4929fdbcc0ea781fc2e534173d9b93c8fcd7b43cd156e
```

The reviewer made no repository changes, the before/after fingerprints matched, 88 focused tests passed, and `git diff --check` passed. The verdict is stale for approval because bootstrap source/tests changed while the review was running, but its findings concern other files untouched by the bootstrap work and therefore require direct reproduction after resume:

1. **P1 — Claude doctor auth classification remains substring-based.** `scripts/doctor.py` parses the explicit `Login method:` line, but accepts any value containing an allowed substring. Examples such as `Unknown Team account` or generic `Claude.ai account` may pass. Reproduce and change this to a closed set of documented explicit Team/Pro/Max login-method values; test Pro, Max, Console, Unknown Team account, Claude.ai account, and organization-only labels.
2. **P1 — detached runner does not revalidate authoritative identity immediately before Claude launch.** After `dispatch_worker` queues and releases the run lock, lifecycle state may change before `worker_runner.main` acquires it. The runner currently validates its worker record and artifact hashes, but must also revalidate active stage, attempt, task, profile, dispatch mapping, and the applicable `internal.json` create/repair intent. Add a queue-then-mutate regression and fail the worker terminally without invoking Claude on mismatch.
3. **P2 documentation — worker history location.** README says history resides in `run.json`; actual worker records are under the run's `workers/` directory. Correct the operational documentation.

Full review artifact:

```text
/Users/ajhochhalter/.hermes/cache/delegation/subagent-summary-0-20260820_164209_496160.txt
```

Do not treat this review as approval. Reproduce the two P1 findings, repair them with RED→GREEN tests if they still hold, rerun all gates, freeze the final candidate, and request a new immutable review.

## Remaining work

1. Review the current two-file bootstrap diff without changing it.
2. Recalculate/confirm source and installed hashes.
3. Atomically deploy **only** `plugins/hermes-coding-workflow/__init__.py` to the eight managed profiles, requiring the current installed hash above before replacement and rolling back all copies on any mismatch/failure.
4. Verify in a fresh imported process that `_build_bootstrap()` contains the real worker cwd, `t_81f59d6c`, current board, and the complete required command shape.
5. Recover `t_81f59d6c` from `triage`/block-loop state using the supported Kanban recovery path, then dispatch exactly one fresh attempt.
6. Inspect the new worker transcript. It must call the installed launcher with repo, matching `--run-id`, package, one or more scopes, board, and goal. Do not weaken the hook to permit a bare command or inline env-prefix workaround.
7. Verify actual bootstrap success by observing the new run manifest/locator and progress beyond initial orchestration—not merely process spawn.
8. Rerun complete Python, Node/Desktop/build, compilation, and diff gates after any change.
9. The pre-bootstrap independent review `deleg_2a527a41` is stale for these later hook/test changes; obtain a fresh immutable review before commit/push/publication.
10. Update the Dev Dashboard and Obsidian only after the user resumes work and the live retry is verified.

## Safety notes

- Do not broadly allow terminal commands before lifecycle identity exists.
- Do not permit bare `hcw create-run`.
- Do not accept mismatched or duplicate `--run-id` arguments.
- Do not install the broader dirty branch as a shortcut.
- Do not retry the Kanban card again until the later guidance revision is installed and freshly verified.
