# Project State — Hermes Coding Workflow

## Focus

Build the complete standalone Hermes coding workflow package, including the control plane, Superpowers-derived workflow disciplines, Hermes plugin API, Desktop run UI, installation tooling, and a real end-to-end proof.

## Repository

- Path: `/Users/ajhochhalter/Documents/hermes-coding-workflow`
- Candidate branch: `integration/complete-workflow` (manual merge gate; `main` remains foundation-only)
- Dashboard tracker: `hermesCodingWorkflow`

## Current activity

- Complete candidate `b436a6e` is installed in the live Hermes home through safe native-provider source profile `hcw-dev` and seven Gemini-backed role profiles. A real installed tracer run completed on board `hcw-live-tracer-1787210374`; all nine exact task IDs are `done`, RED failed as required, GREEN/live passed, the candidate SHA was preserved, and the disposable repository's `main` remained unchanged.

## Safety

- Existing dirty Rhythm checkout is out of scope and must not be modified.
- No worker merges or pushes.
- No automatic default-branch merge.
- Existing direct-tool `dev` remains unchanged; live enforcement is installed only in `hcw-dev` and its role profiles.

## Test status

- Control plane, native plugins, role profiles, installer, read-only API, Desktop UI, and public installed lifecycle are implemented.
- Final fork-worktree gates: `44 passed in 245.65s` with zero skips/xfails; Node `3/3`, production ESM build, Python compilation, wheel build, diff check, native plugin doctors, isolated installed lifecycle, crash-consistency failure injection, and live active-home lifecycle all passed.
- Live proof: run `live-tracer-1787210374`, board `hcw-live-tracer-1787210374`, nine tasks all `done`, base `4e269dee0ded1b4c4080f02f9fdc3be536979323`, candidate `0123bcdac2e9b3faaca17b58af8d72e37afb5b93`, and default branch unchanged.

## Recent coding-agent runs

### 2026-08-20 — live installation and Kanban reconciliation
- Installed dashboard-only payload in the base Hermes home and enforcement/runtime payloads in `hcw-dev` plus seven safe native-provider role profiles; existing `dev` remained unchanged.
- First external install attempt proved transactional rollback under an unsupported Apple Python 3.9 environment. Replayed with Homebrew Python 3.11; installation and doctor passed.
- First live tracer exposed that internal stage completion did not close Kanban tasks. Added exact fail-closed `kanban complete` synchronization with RED-first behavioral coverage, reran all gates, reinstalled, and replayed on a fresh per-repo board.
- Final live board contains exactly nine tasks and all are `done`; the earlier failed-test board was archived recoverably.

### 2026-08-19 — native workflow plugin repair
- Files modified: native plugin packages, lifecycle scripts, isolated-host tests, pinned brainstorming server, and Terra run evidence.
- Checks run: focused plugin/skill pytest passed (7); Python compile, Node syntax validation, and diff check passed.
- Decisions made: plugin namespaces use Hermes v0.20's actual namespace source (manifest `name`: `hcw`/`superpowers`), while directory IDs remain the requested native package names.
- Deviations from spec: no live profile installation, push, merge, or network activity.
- Concerns: the control-plane source is installed from the sibling control-plane worktree into the isolated plugin runtime.

### 2026-08-19 — integrated final repair
- Files modified: authoritative run DTO/service, native hcw guard, Hermes adapter, installer doctor, lifecycle/plugin/E2E tests, and integrated run record.
- Checks run: Python regression and installed disposable-repository lifecycle; Node test/build; offline wheel build; Hermes doctors; diff and scoped secret scan.
- Decisions made: the run record is the single source for stage status; matching malformed workflow identity fails closed while no workflow identity fails open.
- Deviations from spec: none; no live Hermes home, network, push, or merge was used.
- Concerns: none known after final gates.

### 2026-08-19 — product contract/API/UI rejected-review repair
- Files modified: role skills, README/architecture, descriptor-safe dashboard projection, Desktop renderer, and owned API/Desktop tests.
- Checks run: `PYTHONPATH=. pytest -q -ra tests/api` (9 passed); `python -m py_compile dashboard/plugin_api.py`; `npm test` (3 passed); `npm run build` (ESM parse plus 3 passed); `git diff --check` (passed).
- Decisions made: API DTOs derive current actor from `run.dispatches` and preserve service-shaped reviews/dispositions; untrusted text is redacted and bounded at every response field; artifacts are opened relative to a controlled directory descriptor with no-follow + `fstat` validation.
- Deviations from spec: no installed-Hermes/packaged Desktop smoke, install, live run, network activity, or commit was performed at the user's direction.
- Concerns: the current core record at this rejected base does not yet emit the requested `dispatches` map or public `commit` command; the product layer rejects missing dispatches and documents the target contract, but core implementation is outside this owner's scope.
