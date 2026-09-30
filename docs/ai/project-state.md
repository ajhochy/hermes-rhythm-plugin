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
