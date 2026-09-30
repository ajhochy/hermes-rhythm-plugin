# Open Design integration — paused handoff

**Status:** PAUSED by user request
**Paused at:** 2026-08-20 17:02:06 PDT (-0700)
**Primary branch:** `agent-stack/opendesign-webview`
**Primary worktree:** `/Users/ajhochhalter/.hermes/worktrees/hermes-agent/opendesign-webview`
**Primary HEAD:** `f107c3e08f10695621af76548bcc93ee8b9e2805`
**Dev Dashboard tracker:** `hermesOpenDesignWebview` — overall 55%, paused (`pending`)

## Pause receipt

- No Open Design background process was active when paused.
- Removed one-shot cron job `Resume Open Design S1 after Claude reset` (`0fe0b95df0c4`).
- Do not restart S1, S2, or S3 workers until the user explicitly resumes this project.
- No Open Design PR has been opened.
- S1, S2, and S3 are **not integrated** into the primary branch.

## Product goal

Ship a production Open Design 0.20.0 workspace at Hermes Desktop `/design` using the real Open Design app in a sandboxed Electron guest. Hermes owns runtime supervision, exact loopback authority, profile-scoped persistent storage, theme synchronization, and credential-free ACP model reuse. Do not merge Open Design source into Hermes or copy Hermes provider credentials into Open Design configuration.

## What is integrated

The primary branch contains the frozen contract and accepted S4 defaults/privacy work:

- `31d23b551` — freeze Open Design integration contract
- `558e9c801` — amend packaging boundary
- `0713df75f` — seed Hermes Open Design defaults
- `4fb6b5116` — align config seeding
- `f107c3e08` — bound config reads

Official Open Design 0.20.0 artifact hashes previously verified:

- macOS arm64 DMG: `85d30826ba46729f45bf059c76e710e760e2b6bfc2c57218e311027cbb0cbcd5`
- Windows x64 NSIS: `9788a6a7a3ff1c6e31b41756fb1ecd631b54307acfed5937bfe5b1bd0000d9b8`

## S1 — runtime staging and supervision

**Worktree:** `/Users/ajhochhalter/.hermes/worktrees/hermes-agent/opendesign-runtime-s1`
**Branch:** `agent-stack/opendesign-runtime-s1`
**Base/rejected candidate:** `066db25324a03cac53115d97f6e7eaf9285656e8`
**State:** dirty additive repair worktree; preserve it exactly

Local evidence:

- 345/345 Open Design tests pass.
- Typecheck passes.
- `git diff --check` passes.
- Focused Windows guardian/supervisor factory tests and guardian race probes pass locally.
- Win32 supervisor construction now fails closed unless owned-runtime dependencies are wired.

Why S1 is not accepted:

- Candidate `066db253…` immutable review rejected it: 0 P0, 7 P1, 4 P2, 3 P3.
- Local macOS TypeScript tests cannot replace required real Windows evidence.
- Required external gates remain:
  - real MSVC guardian build;
  - Windows Job Object lifecycle and crash behavior;
  - Authenticode/trust-chain validation;
  - durable ownership, ACL, reparse-point, and anti-TOCTOU proof;
  - installed NSIS/MSI smoke;
  - exact Node 22 workflow alignment (`.nvmrc` was observed as `26`).

Primary repair packet:

`/Users/ajhochhalter/.hermes/agent-prompts/hermes-opendesign-runtime-s1-post-066db-repair.md`

Original immutable review:

`/Users/ajhochhalter/.hermes/cache/delegation/subagent-summary-0-20260820_135939_712343.txt`

Useful checkpoints:

- `/tmp/hermes-s1-current-tested-checkpoint.patch`
- `/tmp/hermes-s1-current-tested-untracked.tar.gz`
- `/tmp/hermes-s1-current-after-parent-repairs.log`

## S2 — secure Electron guest and IPC bridge

**Worktree:** `/Users/ajhochhalter/.hermes/worktrees/hermes-agent/opendesign-secure-s2`
**Branch:** `agent-stack/opendesign-secure-s2`
**Latest rejected candidate:** `33715e15fc8531ab809d423adbc4495ba649b3d2`
**State:** clean at the rejected candidate

Latest candidate gate evidence:

- 289 focused Open Design tests pass.
- 1,738 Electron/platform tests pass; 2 skipped.
- 5,171 UI tests pass.
- Typecheck, lint, build, postbuild, and diff-check pass.
- Real Electron security harness passes every scenario, verifies cleanup, and exits 0.

Why S2 is not accepted:

Fresh dual immutable review rejected `33715e15…`. Valid deduplicated repair set:

- **P1:** process-global binding lets trusted Hermes windows overwrite each other's profile authority.
- **P1:** status events lack owner + generation identity, so stale A1 events survive A→B→A2.
- **P2:** malformed status can revoke a healthy origin.
- **P2:** production ignores the guest-policy disposer.
- **P2:** undifferentiated subframe loading can hide a healthy guest indefinitely.
- **P2:** any Enter key grants an overly broad external-open token.
- **P2:** late retry completion/rejection can overwrite a newer profile.

One additional claimed P1—guest-local failure surviving a same-origin profile switch—is contradicted by the exact passing regression already in `src/app/open-design/index.test.tsx`. Retain and strengthen that test; ask the next reviewer to reproduce a valid ordering before changing behavior.

Architecture selected for the next repair:

- S1 provides one process-wide runtime supervisor, so S2 must enforce one process-wide owning trusted Hermes window.
- Owner identity is main-issued from trusted sender WebContents/window identity.
- Every runtime operation/event carries owner + monotonic generation + profile.
- Non-owner windows receive a stable sanitized non-ready status and cannot mutate, receive owner broadcasts, or attach an authorized guest.
- Owner close must dispose policy and release ownership so another window can acquire.

Repair packet:

`/Users/ajhochhalter/.hermes/agent-prompts/hermes-opendesign-secure-s2-post-33715-repair.md`

Immutable reviews:

- `/Users/ajhochhalter/.hermes/cache/delegation/subagent-summary-0-20260820_165439_701244.txt`
- `/Users/ajhochhalter/.hermes/cache/delegation/subagent-summary-1-20260820_165439_701577.txt`

## S3 — live Hermes theme synchronization

**Worktree:** `/Users/ajhochhalter/.hermes/worktrees/hermes-agent/opendesign-theme-s3-final`
**Branch:** `agent-stack/opendesign-theme-s3-final`
**Latest rejected candidate:** `4ca699984ea50dd124f7c825ceeb7975e126b220`
**State:** clean at the rejected candidate

Latest candidate gate evidence:

- 341/341 focused theme tests pass.
- 5,473/5,473 UI tests pass.
- Typecheck, lint, build, postbuild, and diff-check pass.
- Existing and added Electron/browser probes passed before immutable review.

Why S3 is not accepted:

Immutable review rejected `4ca699…`: 2 P1, 4 P2, 1 P3.

- **P1:** a genuine decoy MutationObserver can falsely certify legacy owner retirement.
- **P1:** connected owners hidden in shadow roots/other documents survive light-tree scans.
- **P2:** trailing CSS comments bypass direct-color range preflight.
- **P2:** guest-overridden DOM methods can forge postcondition verification.
- **P2:** object result validation cannot prove pre-transport descriptors across Chromium structured clone.
- **P2:** radius values have no textual resource bound.
- **P3:** valid `oklch()` and `display-p3` computed shadows are discarded.

Repair packet:

`/Users/ajhochhalter/.hermes/agent-prompts/hermes-opendesign-theme-s3-post-4ca699-repair.md`

Immutable review:

`/Users/ajhochhalter/.hermes/cache/delegation/subagent-summary-0-20260820_155703_433275.txt`

## S4 — Hermes ACP model reuse

**State:** defaults/privacy commits are integrated in the primary branch.

Still required after S1/S2/S3 acceptance:

- wire the accepted runtime/secure guest/theme slices into production composition;
- prove live ACP model catalog and real generation through Open Design without copying credentials;
- verify profile changes and owned-runtime lifecycle;
- preserve telemetry-off and analytics blocking behavior.

## Remaining campaign work

Resume in this order:

1. **S1:** finish additive repairs and obtain real Windows trust/ownership/installed-lifecycle evidence.
2. **S2:** implement single-owner-window authority, owner+generation event identity, and the five valid P2 repairs; run a real two-window/iframe Electron harness; commit one additive repair; obtain fresh dual immutable review.
3. **S3:** repair all seven review findings with real Chromium/Electron regressions; commit one additive repair; obtain fresh immutable review.
4. Integrate only clean accepted S1/S2/S3 commits into `agent-stack/opendesign-webview`.
5. **S5:** run production-composition verification: unit/integration, live app, real ACP generation, packaging, security, visual regression, and real Windows lifecycle/trust gates.
6. Run final independent adversarial review on a detached clean head and reconcile every concrete finding.
7. Update Dev Dashboard and Obsidian project record after gates.
8. Push to `ajhochy` and open a PR only after honest final verification. No PR currently exists.

## Non-negotiable constraints when resuming

- Do not reset, clean, delete, or discard any S1/S2/S3 worktree or checkpoint.
- One writer per worktree; concurrent agents never share a worktree.
- Node 22 is authoritative: `/opt/homebrew/opt/node@22/bin`.
- Run desktop scripts from `apps/desktop`.
- TDD is mandatory; immutable review uses exact committed heads and fresh detached worktrees.
- Do not integrate a slice until its exact commit is locally verified and independently accepted.
- Never copy Hermes provider credentials into Open Design configuration; keep all secrets redacted.
- Preserve `/design` as chrome-free/full-bleed, sandboxed, context-isolated, no Node integration, exact validated loopback authority, denied unauthorized navigation/popups/downloads/permissions, and fail-closed behavior.
- Windows guardian acceptance requires real Windows evidence; macOS simulations are insufficient.
