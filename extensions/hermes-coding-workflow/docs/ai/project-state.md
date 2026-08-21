# Project State — Hermes Coding Workflow

## Focus

Build the complete standalone Hermes coding workflow package, including the control plane, Superpowers-derived workflow disciplines, Hermes plugin API, Desktop run UI, installation tooling, and a real end-to-end proof.

## Repository

- Path: `/Users/ajhochhalter/.hermes/worktrees/hermes-rhythm-plugin/oauth-tier-routing/extensions/hermes-coding-workflow`
- Candidate branch: `fix/oauth-tier-routing` (manual merge gate)
- Dashboard tracker: `hermesCodingWorkflow`

## Current activity

- The predecessor OAuth-tier route is installed in the live Hermes home. `hcw-dev` is the GPT-5.6-Sol orchestrator through OpenAI account OAuth, and every Hermes profile stays on OpenAI OAuth with no API-key fallback chain or provider `anthropic`. Exact-route doctor, OpenAI Sol smoke, and the Hermes hook probe pass. The new external Claude CLI adapter on `fix/oauth-tier-routing` is not yet live-installed.
- The architecture pivoted: `red`, `green`, `quality-review`, and `complete` are external, Hermes-dispatched asynchronous Claude Code CLI subprocesses (`hcw dispatch-worker`/`hcw worker-status`), authenticated by Claude Team/Pro/Max account login and never an API key. Claude internal tools do not pass through Hermes hooks. Safety comes from registered-worktree confinement, authoritative stage/task/attempt/brief binding, exact variadic tool matchers, credential-minimal environments, descriptor-bound atomic artifacts, process-identity reconciliation, and controller-owned review/verification transitions.

## Safety

- Existing dirty Rhythm checkout is out of scope and must not be modified.
- No worker merges or pushes.
- No automatic default-branch merge.
- Existing `dev` remains unchanged; live enforcement is installed only in `hcw-dev` and its role profiles. OpenAI OAuth is pinned to Hermes-owned behavior by `model.openai_runtime: auto` plus `model.api_mode: codex_responses`; either Codex app-server config spelling remains rejected.

## Test status

- Control plane, native plugins, role profiles, installer, read-only API, Desktop UI, public installed lifecycle, and the async Claude Code CLI worker dispatch/runner are implemented.
- Branch gates: `159 passed` (Python) with zero skipped/xfailed/xpassed; Node `3/3`, production ESM build, Python compilation, diff check, installed-runner importability, source/profile rollback, OpenAI runtime/API-mode allowlists, account-auth parsing, credential-minimal worker/probe environments, descriptor-bound atomic writes, registered-worktree identity, authoritative brief binding, stale-process reconciliation, and authoritative worker-repository binding all pass.
- The older `live-tracer-1787210374` proof validates the pre-pivot workflow only. A fresh real Team-account asynchronous dispatch smoke is still required for this adapter; the first matcher probe reached the account's normal session cap and reported a 17:30 PDT reset.

## Recent coding-agent runs

### 2026-08-21 — OAuth tier-routing authoritative worker repository binding
- Files modified: `plugins/hermes-coding-workflow/__init__.py` binds `dispatch-worker` and `worker-status` to the canonical authoritative `run.repo_root`; `tests/plugin/test_native_plugins.py` covers canonical, alias, and rejected worker-command paths.
- Checks run: focused RED: 14 selected tests, 4 expected failures proving both commands allowed different/nonexistent repositories; focused GREEN: 14 passed. Parent full Python suite: 159 passed with one dependency deprecation warning. Node/Desktop: 3 passed; production build: 3 passed. Python compilation, diff check, and added-line secret scan passed.
- Decisions made: follow the CLI/run established `Path.resolve()` policy, accepting canonical-equivalent symlink aliases but requiring the resolved command repository equal the run's controlling `repo_root`; do not bind it to the isolated implementation worktree.
- Deviations from spec: no push, deployment, profile mutation, or Kanban retry before a fresh immutable rereview.
- Concerns: fresh immutable rereview remains required; real installed-profile worker dispatch remains pending.

### 2026-08-20 — Claude Code CLI async worker dispatch and Anthropic-routing removal
- Files modified: `scripts/{install,doctor}.py`, `src/hermes_coding_workflow/{cli,contracts,safety,service,store}.py`, `tests/integration/test_lifecycle_install.py`, `README.md`, `docs/ai/architecture.md`, `docs/ai/project-state.md`.
- Files added: `src/hermes_coding_workflow/{claude_worker,process,worker_runner}.py`, `tests/core/test_{atomic_writes,claude_worker,dispatch_worker,dispatch_cli,worktree_identity}.py`, and `tests/integration/test_installed_runner_importability.py`.
- Decisions made: Hermes stays entirely OpenAI account-OAuth (GPT-5.6-Sol); four bounded stages run as detached Claude CLI account-subscription workers. Workers receive only operational/account context plus actor identity, never the parent control-plane environment. The Hermes controller alone performs workflow transitions.
- Checks run: full Python suite (126 passed, zero skip/xfail markers); Node/Desktop (3 passed) and production build; Python compilation; `git diff --check`; focused direct parent-swap, symlink, process-identity, worktree, installed-layout, auth-method, and brief-forgery reproductions.
- Deviations from spec: no commit, push, or live adapter install yet; manual merge gate remains.
- Concerns: independent rereview and fresh real Team-account dispatch smoke remain open gates.

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
