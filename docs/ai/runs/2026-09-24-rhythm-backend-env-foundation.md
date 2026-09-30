---
date: 2026-09-24
repo: hermes-rhythm-plugin
branch: codex/hermes-shared-integration
pr: 17
issues: []
status: partial
tags: [run, hermes]
---

# Rhythm #1569 S3 backend environment foundation

## Files

Embedded host accepts an optional main-owned backendEnv callback and identity context. Only owned default-profile spawns invoke it. Child environment is constructed from controlled location/locale/runtime values and the four approved static API-key names; ambient secrets and loader variables are excluded. Callback failure or a two-second deadline starts without grants. Borrowed runtimes are preserved.

## Checks

Base `8ea642dbb6a8b8d65868c3e7a468c471914f037b` plus this slice.

- Independent candidate host tests initially 19/19 and desktop typecheck exit 0.
- Parent and independent review reproduced UTF-8 split and overlapping-secret partial log disclosure. Streaming StringDecoder and longest-first full-value redaction address them. Parent additionally reproduced a token-shaped substring preventing whole-grant removal; complete values are now removed before URL token masking.
- Final integrated `npx vitest run --project electron electron/embedded-host.test.ts electron/embedded-host-initialization.test.ts electron/embedded-host-backend-env.test.ts`: 3 files, 22/22, exit 0.
- Final integrated `npm run typecheck`: exit 0; `git diff --check`: exit 0.
- Earlier repair ran the broader Electron suite: 1462 passed, 2 skipped, before the final token-order fix. This is recorded separately from the final 22-test replay.
- New captureChildOutput is not present in stale GitNexus index; upstream impact UNKNOWN. Its direct use is limited to owned child stdout/stderr capture.

External evidence: `/Users/ajhochhalter/Documents/rhythm-orchestration-evidence/2026-09-24-repair4/s3-*` and `/private/tmp/rhythm-repair4/s3-*`.

## Notes

Tests inject synthetic child streams and callback keys. No actual account/home credential source was read or modified. A real owned Hermes process, consumer-side grant lifecycle, Accounts UI, local memory capability and packaged-runtime tests remain pending. No native payload or Rhythm source pin is updated by this commit. The later rebuilt artifact must include reviewed native shared-agent changes and feed mega Rhythm PR #1544; no independent release.
