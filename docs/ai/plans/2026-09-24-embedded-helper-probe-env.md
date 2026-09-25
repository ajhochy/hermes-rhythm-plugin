---
date: 2026-09-24
repo: hermes-rhythm-plugin
branch: codex/hermes-probe-env-implementation
issues: [1569]
status: verified-local
tags: [plan, hermes]
---

# Embedded resolver helper environment

The S4 owned backend spawn receives a clean host-supplied environment, but Desktop runs synchronous helpers **before** that spawn. `verifyHermesCli` in `backend-probes.ts` omits `env`, `canImportHermesCli` spreads `process.env` before its `opts.env` delta, and `backendSupportsServe` in `desktop-native-runtime.ts` explicitly spreads `process.env` into `serve --help`. Synthetic executables confirm that `OPENAI_API_KEY`, `HTTPS_PROXY`, and `NODE_PATH` reach both CLI probes and the Python import probe. The full credential values are never written by the tests; only sentinel variable names are observed.

## Acceptance boundary

For `mode: 'embedded'`, every resolver helper subprocess must receive an explicit, clean base environment supplied by the embedded host before runtime resolution. Preserve candidate **selection** and order, first-run/bootstrap decisions, the verified command/interpreter, `serve` versus legacy dashboard detection, retry/timeout behavior, platform requirements (`SystemRoot`/`WINDIR`, temp/home), and legitimate Python source/venv discovery. Derive `PYTHONPATH`, `PATH`, and UTF-8 settings against that clean base; never concatenate ambient `PYTHONPATH` or copy the current backend descriptor's `env` after it has incorporated ambient values. The same environment applies to the two attempts of a timeout retry.

Standalone Desktop keeps its existing environment semantics. Do not change `canImportHermesCli(opts.env)` from a standalone delta into a replacement without an explicit `baseEnv`/isolated-mode option. An embedded missing clean environment fails closed before invoking a helper; it must not silently fall back to `process.env`.

## Likely implementation seam

- Extend the S4 `ownedSpawn` adapter with a synchronous `probeEnv(): NodeJS.ProcessEnv` that returns a fresh clean base without a dashboard token or grants. The host derives it from its trusted `hermesHome` and controlled binary/temp directories; no renderer or raw Rhythm credential values enter it. Use this only in embedded mode.
- In `backend-probes.ts`, give `verifyHermesCli` an explicit `env` option. Give `canImportHermesCli` an explicit `baseEnv` option; merge its existing `opts.env` onto that base only for embedded calls, retaining the current ambient merge when `baseEnv` is absent. Pass the resulting exact environment to `execProbeSync` for initial and retry attempts.
- Thread the clean base through `resolveHermesBackend`, `isActiveRuntimeUsable`, `unwrapWindowsVenvHermesCommand`/`resolveVenvHermesCommand`, and `backendSupportsServe`. Rebuild source/active/Windows-venv Python paths from selected roots and site-packages against this base. Avoid using `backend.env` computed from ambient process state for embedded `serve --help`.
- On POSIX, `findSystemPython` uses PATH to choose a command; on Windows it can invoke `reg query` and `py -c`. Retain the current discovery order, but make every executed discovery helper use the same clean base. Explicit override binaries remain the selected executable. Review `HERMES_DESKTOP_PYTHON`, `HERMES_DESKTOP_HERMES`, and timeout overrides as selection knobs; do not treat their values as permission to forward arbitrary environment variables.
- First-run bootstrap passes the same host base through manifest, stage, and checkout-HEAD helpers. Direct and multi-connection Desktop update IPC plus uninstall IPC remain unregistered in embedded mode because Rhythm owns that lifecycle; packaged Windows bootstrap recovery likewise refuses the Desktop updater path instead of spawning it with ambient state.

## RED evidence and next checks

From `apps/desktop` in this isolated worktree:

```sh
env -i PATH=/Users/ajhochhalter/.local/bin:/usr/bin:/bin HOME=/private/tmp/hermes-probe-empty-home TMPDIR=/private/tmp LANG=C.UTF-8 ../../node_modules/.bin/vitest run --project electron electron/embedded-probe-env.contract.test.ts electron/embedded-native-probe-env.contract.test.ts
```

The direct probes, Windows venv shim, and real initializer/`hermes:connection` tests failed RED against the unmodified `db0cba2d3c` base. Synthetic `PYTHONPATH` and `PATH` checks remain green after repair. The timeout retry test confirms both executions receive the same clean env. The initializer test uses a synthetic shell executable only; it does not start Hermes, an API server, or a provider.

The Windows-shim/import contract uses the real import helper and asserts that the verified interpreter is retained and the descriptor derives from the clean base. The timeout-retry test gives the synthetic first attempt a 500 ms budget and confirms both executions receive the identical explicit environment. A lifecycle contract now records variable names observed by real synthetic manifest/stage and checkout-HEAD subprocesses and proves that embedded update/uninstall channels are refused before any child spawn. The original focused 12-file selection passes 101 tests with one worker; the expanded post-change selection passes 114 tests across 14 files. The desktop package's renderer, Electron, and e2e TypeScript projects also pass. Native Windows `reg.exe`/`py.exe` execution, real Python package import, and packaged/legacy runtime behavior remain unqualified.
