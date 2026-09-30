# Hermes Rhythm feature pack — current state

Draft PR17 on `mega/2026-09-18-rhythm-plugin-finish`; companion Rhythm PR1544. Rebuilt isolated native host now mounts Rhythm and removes route/backend registrations/stale disk inventory on Rescan without restart. Final IPC error UI correctly reports server update required before opening OAuth. Installed older Hermes remains unchanged and running.

Final scoped Rhythm tests296/296; packaging62/62; loader/Settings19/19; connection UI2/2; desktop typecheck/build pass. Earlier M10 performance failures and unrelated ownership-ledger failures remain documented; no thresholds changed. GitNexus final aggregate MEDIUM, one Contrib flow.

Hosted M3 deliberately fails closed until the login-only API is deployed. Initial legacy OAuth attempt altered Google/Gmail scope records; original grants restored and verified by parent. Hosted reads, ACP deny/allow/read-back, unsent draft and nonempty zero-write trace remain open. No marker task was mutated and no draft sent by this fork work.

Final package: `dist/rhythm-feature-pack-mega-ipc-final`, bundle SHA256 `70a0acd6707ea42e48313f25a1863b713d92e5cd222ffa5ce7845b3853d61084`. Native evidence and recovery receipts are in companion PR1544. [Run and decisions](runs/2026-09-19-hermes-mount-repair.md). Preserve four pre-existing dashboard-dist deletions.

## Recent coding-agent runs

### 2026-09-19 — desktop-embedded-native-host
- Files modified: `electron/embedded-host.ts`, scoped FS/git/terminal registrars, and native host contract tests.
- Checks run: `npm exec vitest run --project electron electron/embedded-host.test.ts` pass (106 files, 1,433 tests); full typecheck is currently blocked by concurrent `electron/desktop-native-runtime.ts:49` extraction work.
- Decisions made: isolate privileged IPC to the exact embedded main frame and document; only borrow an owner-provisioned, token-validated local runtime descriptor; stop owned children on disposal.
- Deviations from spec: full preload parity awaits the concurrent shared desktop-native-runtime extraction.
- Concerns: installed native smoke and authenticated runtime-manifest qualification remain unrun.

## Consolidation 2026-09-29

Branch `mega/2026-09-29-consolidation` (from `origin/main` b47054e036) folds every local branch, remote-tracking ref, linked-worktree WIP and external clone of this repo. Nothing was deleted by the consolidation run; a reviewed cleanup script does that later.

- PR: see PR URL line at the end of this section.
- Tracking issue: see Issue URL line at the end of this section.
- Bundles (all `git bundle verify` clean): `~/Documents/.consolidation-backups/hermes-rhythm-plugin-2026-09-29.bundle` (whole repo, `--all`, 2550 heads), `hermes-rhythm-plugin--hermes-s8-build-2026-09-29.bundle` (`/private/tmp/hermes-s8-build`), `hermes-agent--fix-kanban-recursion-guard-2026-09-29.bundle` (`~/.hermes/hermes-agent` branch + autostash).
- Cleanup script (NOT executed; user reviews and runs): `~/Documents/.consolidation-backups/cleanup/hermes-rhythm-plugin-2026-09-29-cleanup.sh`; manifest `hermes-rhythm-plugin-2026-09-29-manifest.json` beside it.
- In-flight worktrees: none (no live process has its cwd in any of the 64 linked worktrees).
- Dashboard dist: the four dirty `plugins/{hermes-achievements,kanban}/dashboard/dist/{index.js,style.css}` deletions (see "Preserve four pre-existing dashboard-dist deletions" above) were WIP-snapshotted and are preserved as deletions on this branch. Restore with `git checkout origin/main -- plugins/hermes-achievements/dashboard/dist plugins/kanban/dashboard/dist` if they were not intended.

### Folded (merged, or ancestor of this branch)
Merged with `--no-ff`: `origin/mega/2026-09-18-rhythm-plugin-finish` @ 31b8917a6d (PR #17 head), `codex/hermes-theme` @ d747cbd9e8 (also `origin/codex/hermes-theme`), local `mega/2026-09-18-rhythm-plugin-finish` @ 30b1bb892b (WIP snapshot of the 29 dirty files), `fix/oauth-tier-routing` @ 5eca430a4b (PR #16 head b19bcff5b4 plus WIP snapshot of 7 files), `fix/hcw-no-nested-bootstrap` @ 3eabafbbcf (WIP snapshot), `refs/clone/hermes-agent/fix/kanban-recursion-guard` @ 3bb8be6642 (from `~/.hermes/hermes-agent`, WIP snapshot; conflicts resolved: union in `agent/copilot_acp_client.py` and `hermes_cli/config_defaults.py`, mega side for `runtime-loader{,.test}.ts`), `refs/clone/hermes-agent/stash-backup/0-2026-09-29` @ ceae6a88e8 (discord app-command sync fix carried in its own commit; recorded with `-s ours`).
Cherry-picked: `agent-stack/rhythm-feature-pack-m10-terra` (= `-m10-terra-repair`) tip 8c5a5e1027 as 6838c255e3 (the only commit of that lineage not on mega); `agent-stack/rhythm-feature-pack-sonnet` @ 93d833b107 has an identical tree. Both recorded with `-s ours`.
Recorded with `-s ours` (superseded, kept reachable): `codex/sa-s4` @ 183fcebded, `codex/sa-s5` @ 98cd74f4c3, `codex/sa-stage` @ da63f9b490, `codex/hermes-probe-env-implementation` @ 9a7ad76a70, `agent-stack/rhythm-feature-pack-m6-terra` @ eb98888b7b.
Ancestors of mega (no merge needed): `codex/hermes-s7`, `codex/hermes-shared-integration`, `refs/clone/hermes-s8-build/codex/hermes-s7` @ 31b8917a6d; `codex/sa-s0` @ e3b38d624f; `codex/sa-s5b` @ c71453de63; `codex/sa-stage2` @ aa2ceb4c83; `codex/1540-p1-routes` @ feef2e7bd7; `codex/hermes-credential-spawn-receipts`, `codex/hermes-probe-env-contract` @ d14e280dbf; `codex/1569-s3-backend-env`, `codex/hermes-desktop-embedded`, `codex/native-hermes-session-policy` @ 8ea642dbb6; `wt/t_*` (10), `hcw/t_20553fcd/attempt-1`, `hcw/t_971f390b/attempt-1`, `origin/wt/t_c118913c` @ d1eaf21d8a; `plan/rhythm-feature-pack` @ ad7a14a539 (already in `origin/main`).

### Preserved as patches (`consolidation/unmerged/`)
Nine `hcw/t_*/attempt-1` WIP snapshot commits (abandoned Hermes Coding Workflow attempts: Rhythm page/connection tests and `plugins/github-intake` tests) conflict with each other, so each is one `git apply`-able patch: `hcw-t_c118913c` 837575b5b9, `hcw-t_c118913c_v2` 773503dabf, `hcw-t_e3646d73` e81fb67969, `hcw-t_5a65dde9` 687b7b1f7a, `hcw-t_075b9043` a8de29bdea, `hcw-t_2f151463` 85297c2d3a, `hcw-t_dbfb6851` 5c56440c85, `hcw-t_84d809af` 5b6788e588, `hcw-t_e7ca3114` 352f54b734 (all `-attempt-1.patch`).

### Dropped (content is on mega or main; bundle `hermes-rhythm-plugin-2026-09-29.bundle` holds every tip)
- `agent-stack/rhythm-feature-pack-m0-sonnet` e54a58b67e, `-m2-terra` cc3fdaa5c2, `-m3-terra` 082748ce5b, `-m4a-terra` 745ed228b4, `-m4b-terra` 70d8037caf, `-m5-terra` 839604a3b0, `-m7-terra` ab920ec0e9, `-m8-terra` 534d76471b, `-m9-terra` 37cabf08fa, `-m9-final-terra` 1b04e6c4a3: every commit is patch-identical (`git range-diff` "=") to a commit already on mega.
- `codex/sa-s3` 42dceebab4: tree identical to mega commit cd345ca2cd.
- `feat/hermes-coding-workflow` 975e0759fe (local and origin): empty diff against `origin/main`, whose b47054e036 is the squashed #1.
- Not candidates: `upstream/*` (1576+ mirrored NousResearch refs; the cleanup script narrows the fetch refspec to `upstream/main`), tags.
