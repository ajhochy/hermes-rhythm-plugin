---
date: 2026-09-24
repo: hermes-rhythm-plugin
branch: codex/hermes-credential-spawn-receipts
pr: 17
issues: [1569]
status: partial
tags: [run, hermes]
---

# Owned-child credential application receipts

## Files

- `apps/desktop/electron/embedded-host.ts` emits frozen main-only, per-attempt starting/accepted/retired observations for owned default-profile starts. Its existing fallback spawner retains the S3 clean environment; the production host supplies the same clean base and filtered grant to the extracted native runtime through an embedded-only `ownedSpawn` adapter. Borrowed and nondefault starts emit no default receipt and receive no default grant. Host disposal awaits in-flight starts and propagates failed stops.
- `apps/desktop/electron/desktop-native-runtime.ts` keeps the native resolver, first-run choice, exact command and arguments, profile selection, ready-file/HTTP/WS readiness, web assets, parent watchdog, child claim, process ownership, and shutdown. Both primary and pool owned spawns replace inherited environment with the host's clean base; Python launch variables are rebuilt against that base instead of copying `backend.env` with ambient PATH/PYTHONPATH.
- `apps/desktop/electron/embedded-host-spawn-receipts.test.ts` exercises fallback host lifecycle with a disposable shell child. `embedded-shared-runtime.test.ts` drives the real initializer and `hermes:connection` IPC through a disposable Node loopback child, including broker, no-broker hostile ambient sentinel, and nondefault pool launch. The child reports only synthetic credential classification and required variable names. The native IPC cases also prove pending-broker disposal, accepted-observer refusal and exact child stop, split-chunk secret redaction, and a bounded, surfaced failed stop. A second RED-to-green native regression proves failed adoption cleanup remains sticky across retries and disposal, while repeated disposal retains the original failure.
- `docs/ai/contracts/issue-1569-s4-spawn-receipts.json` keeps broad W5–W7 acceptance pending until main broker/adapter and packaged smoke evidence are complete.

## Checks

- Before product edits: seven expected RED, two controls passing (`/private/tmp/hermes-spawn-receipts-red2.log`). The real initializer IPC test exposed a bypass at native owned spawn (`/private/tmp/hermes-real-ipc-red.log`); the no-broker sentinel exposed the same inherited-environment risk outside a broker context.
- The initial prepared-host routing was abandoned before integration because it dropped native lifecycle/readiness behavior. Final command from `apps/desktop`: `env -i PATH=/Users/ajhochhalter/.local/bin:/usr/bin:/bin HOME=/private/tmp/hermes-ipc-empty-home TMPDIR=/private/tmp LANG=C.UTF-8 ../../node_modules/.bin/vitest run --project electron electron/embedded-shared-runtime.test.ts electron/embedded-host-spawn-receipts.test.ts electron/embedded-host.test.ts electron/embedded-host-initialization.test.ts electron/primary-backend-startup.test.ts`: **38 passed across five files** before the sticky-cleanup change; the two changed real IPC failed-stop cases then passed in a narrow selection (other native IPC cases were not repeated). Electron `tsc -p tsconfig.electron.json --noEmit --pretty false`: exit 0.

## Notes

- No real Hermes executable, installed account store, provider, or non-fixture endpoint was accessed. Embedded resolver helper probes still run before the clean long-lived spawn adapter and can inherit ambient environment; helper-process sanitation and packaged/legacy runtime proof remain open. No commit or push. The callback does not carry credential values, hashes, paths, token, or renderer data.
- Main S4 must bind each opaque attempt to host/identity, reject stale or duplicate records, retain saved consent separately from application, and keep sharing unavailable on disposal failure. The fork suite does not prove those main/UI outcomes or packaged execution.
- GitNexus impact was attempted before product edits against a sibling index ten commits stale. New host symbols were unmapped (risk unknown); a same-named `stopChild` matched an unrelated test. No low-risk conclusion is claimed.

## Parent integration receipt

Parent reviewed both product diffs, including strict failed-adoption cleanup and memoized host disposal. Copied only the eight owned slice files onto native-policy integration2291990e54. The same five-file command above now passes **39/39** after the final repair; Electron typecheck passes. Durable logs: `/Users/ajhochhalter/Documents/rhythm-orchestration-evidence/2026-09-24-repair4/hermes-s4-parent.log` and `hermes-s4-parent-types.log`. Actual native initializer/IPC is driven against disposable children; Electron/WS boundaries remain fixtures. Helper subprocess sanitation and final packaged/native smoke remain open.
