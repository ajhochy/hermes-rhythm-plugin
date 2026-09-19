---
date: 2026-09-19
repo: hermes-rhythm-plugin
branch: codex/hermes-desktop-embedded
pr: 17
issues: [1542]
status: local-candidate
tags: [run, hermes]
---

# Actual Hermes Desktop embedded host

## Files
- Shared Desktop-native factory with a preserved standalone entrypoint.
- Scoped embedded IPC, windows, sessions, backend ownership and connection-origin lifecycle.
- Actual Desktop renderer/preload and integrity-covered pinned artifact builder.
- Embedded update controls and unsent draft intent handling.

## Checks
- Parent: `npx vitest run --project electron --exclude '**/find-in-page-native.test.mjs'`: 116 files passed, one skipped; 1511 tests passed, two skipped.
- The excluded file is an Electron app entrypoint. Parent ran its `electron/find-in-page-native-fixture` using Rhythm integration's actual Electron 40.10.2 executable: exit 0.
- Worker: desktop typecheck and lint exited 0; targeted renderer/runtime behavior regressions passed.
- Parent actual Electron startup probes caught and repaired navigation/IPC timing, uncloneable connection callbacks, absent optional plugin files and teardown ordering. Probe7 exited 0 and read actual Hermes version 0.20.5 plus six saved sessions. No message was submitted.
- Source was fast-forwarded to current fork PR head 9fa78bcba1 before this candidate commit. Existing plugin OAuth exchange fixes remain intact.

## Notes
- This local commit supplies an immutable artifact source. Signed visible Rhythm package validation follows; this checkpoint is not a complete release qualification.
- Existing compatible installed Hermes runtime is the local proof dependency. Self-contained Python distribution and exact fresh-install fork bootstrap remain separate release gates. No unpinned fallback, silent installer or installed-source mutation was added.
- Opening the tab does not change Rhythm Google login or approval identity. Unrelated local plugin build deletions in the original fork worktree were not included.

## Post-candidate review repairs
- Registry descriptors now carry the connection ID when first published. The host replaces the legacy endpoint-only record, so removing the registry route revokes its network origin. Added descriptor and observable allowlist regressions; worker Electron selection passed 1454 tests with two skips, plus typecheck and diff checks.
- Embedded artifacts retain the exact root license and staged node-pty/get-windows licenses under `licenses/`; these files are covered by the integrity manifest. Artifact tests passed 2/2. Comprehensive renderer dependency notices remain a distribution qualification item.
- Parent launched the signed Rhythm candidate with a clean PATH: real saved sessions, profile/model controls, Settings and seven installed Desktop plugins are visible. Final pinned rebuild and repeated native smoke follow these repairs.
