# Hermes Desktop embedding contract (2026-09-19)

User correction supersedes dashboard acceptance in #1542. Implement actual apps/desktop renderer inside Rhythm Hermes tab. Preserve working Rhythm auth, engine, approval signing. No fixture substitution.

## Parallel ownership
- Native Terra: Hermes fork electron/ except preload.ts. Explicit embedded entry, shared existing native services, actual gateway backend.
- UI/build Terra: Hermes fork src/, electron/preload.ts, scripts/, package files. Embedded mode and immutable artifact builder.
- Rhythm Terra: Rhythm apps/electron/ and apps/web/. Artifact loader, view lifecycle, package integration.
- Parent: contract, documentation, review, tests, commit, installed smoke. Workers do not commit/push or launch GUI.

## Shared interface v1
Artifact root contains manifest.json, renderer/index.html (actual Desktop build), electron/embedded-host.mjs, electron/preload.cjs, native dependencies as required. Manifest: {schemaVersion:1, product:'hermes-desktop', sourceCommit:<git sha>, electronMajor:<number>, files:{renderer:'renderer/index.html',host:'electron/embedded-host.mjs',preload:'electron/preload.cjs'}, ...integrity metadata}. Builder must use fork source, not ~/.hermes install.

Host module exports async createEmbeddedHermesHost({hostWindow, webContents, assetRoot, userDataPath, hermesHome?, log?}). Called once per live WebContentsView before load. Return {dispose():Promise<void>, handleIntent(intent):Promise<{ok:boolean,reason?:string}>}. Native owns backend lifecycle and exposes normal hermesDesktop preload API; view owns load/visibility/navigation. getStatus/onStatus may be added explicitly with coordination. Document exact adaptation if necessary.

Load file URL renderer/index.html with query embedded=1. Preload exposes existing typed window.hermesDesktop with embedded host metadata. No unrestricted generic IPC bridge; guard every privileged channel against exact webContents, mainFrame, and trusted current local entry document; Rhythm host renderer and subframes rejected. Full Electron app bootstrap must not execute as a side effect. No standalone app updater/uninstall operating on Rhythm, no global single-instance or app menu takeover. Delegate host-window controls explicitly. Preserve existing standalone behavior.

Window can hide on Rhythm tab switch but must not destroy Desktop state. True disposal closes owned PTYs/backends/watchers and removes scoped handlers without killing borrowed services. No source regex tests. First implementer action: record a failing behavioral contract before implementation. Native gate is trusted sender rejection; UI gate is real app draft intent without sending; Rhythm gate is real local artifact loading and persistent view. Parent will run installed native smoke.
