# Project State — Hermes Coding Workflow

## Focus

Build the complete standalone Hermes coding workflow package, including the control plane, Superpowers-derived workflow disciplines, Hermes plugin API, Desktop run UI, installation tooling, and a real end-to-end proof.

## Repository

- Path: `/Users/ajhochhalter/.hermes/worktrees/hermes-rhythm-plugin/oauth-tier-routing/extensions/hermes-coding-workflow`
- Candidate branch: `fix/oauth-tier-routing` (manual merge gate)
- Dashboard tracker: `hermesCodingWorkflow`

## Current activity

- The predecessor OAuth-tier route remains installed in the live Hermes home. `hcw-dev`, planning, spec review, and verification use OpenAI account OAuth, but the four historical Claude-tier role profiles still route through Hermes-native `anthropic`; RED task `t_0010dc58` proved that route now fails before the first model turn with Anthropic HTTP 400. The external Claude Team CLI itself is authenticated and print-mode ready. The new external Claude CLI adapter on `fix/oauth-tier-routing` is not yet live-installed.
- The architecture pivoted: `red`, `green`, `quality-review`, and `complete` are external, Hermes-dispatched asynchronous Claude Code CLI subprocesses (`hcw dispatch-worker`/`hcw worker-status`), authenticated by Claude Team/Pro/Max account login and never an API key. Claude internal tools do not pass through Hermes hooks. Safety comes from registered-worktree confinement, authoritative stage/task/attempt/brief binding, exact variadic tool matchers, credential-minimal environments, descriptor-bound atomic artifacts, process-identity reconciliation, and controller-owned review/verification transitions.

## Safety

- Existing dirty Rhythm checkout is out of scope and must not be modified.
- No worker merges or pushes.
- No automatic default-branch merge.
- Existing `dev` remains unchanged; live enforcement is installed only in `hcw-dev` and its role profiles. OpenAI OAuth is pinned to Hermes-owned behavior by `model.openai_runtime: auto` plus `model.api_mode: codex_responses`; either Codex app-server config spelling remains rejected.

## Test status

- Control plane, native plugins, role profiles, installer, read-only API, Desktop UI, public installed lifecycle, and the async Claude Code CLI worker dispatch/runner are implemented.
- Branch gates: `220 passed` (Python) with zero skipped/xfailed/xpassed; installer integration `40 passed`; native mutation-boundary `76 passed`; Node `3/3`, production ESM build, source compilation, diff check, added-line secret scan, installed-runner importability, source/profile rollback, OpenAI runtime/API-mode allowlists, account-auth parsing, credential-minimal worker/probe environments, descriptor-bound atomic writes, registered-worktree identity, authoritative brief binding, stale-process reconciliation, authoritative worker-repository binding, worker-success transition gates, and installed external-stage E2E all pass.
- The older `live-tracer-1787210374` proof validates the pre-pivot workflow only. A fresh real Team-account asynchronous dispatch smoke is still required for this adapter; the current account-auth and print-mode readiness probes pass.

## Recent coding-agent runs

### 2026-08-21 — External-worker authority enforcement
- Immutable review of `00dc34078593f0c318737f2ae7d8da565c11d6dc` found two P1 defects before activation: external-stage transitions were instruction-gated rather than service-gated, and GREEN guidance placed `check` before the only legal `commit` window.
- The service now requires the latest exact, schema-valid, identity-bound, durable create/repair-intent-bound, design/plan/dispatch-bound, successful worker record with intact hashed stdout/stderr artifacts before RED/GREEN check, GREEN commit, quality review, or completion. Redispatch after success is idempotent.
- GREEN bootstrap and builder guidance now dispatch, poll, commit, then check. The installed lifecycle E2E exercises the complete external worker path instead of bypassing it.
- The first real RED external run reached Claude's hard 12-turn cap and the resumed run reached 30, both with zero permission denials; RED now has a 60-turn bounded budget, while model, tools, scope, and transition authority remain unchanged.
- Focused authority tests, core service suites, and the final `220 passed` aggregate gate all pass.

### 2026-08-21 — External stage controller contract repair
- Files modified: the native bootstrap now emits `dispatch-worker`, `worker-status`, and the later authoritative lifecycle command in order for red, green, quality-review, and complete; the four corresponding role skills require one dispatch, bounded polling to `succeeded`/`failed`, fail-closed Kanban blocking on worker failure, and controller-only HCW transition after success. `tests/plugin/test_native_plugins.py` covers all four bootstrap and skill contracts.
- Checks run: test RED reproduced eight failures: four stale skills and four bootstrap command omissions. GREEN: focused contract matrix 13 passed; native plugin suite 75 passed; serialized isolated-home full Python suite 211 passed with one dependency deprecation warning; Node tests/build 3 passed each; Python compilation, diff check, and added-line secret scan passed.
- Decisions made: external Claude workers never receive an HCW launcher and never transition state. The Hermes profile is explicitly responsible for one dispatch, durable status polling, deterministic RED/GREEN checks or review/complete encoding, and final Kanban terminal reporting. A failed external worker cannot advance HCW.
- Live control note: the installed runtime is confirmed pre-adapter (`dispatch-worker`/`worker-status` absent and runtime modules differ or are missing). No live profile or Kanban mutation occurred while this repair was developed.

### 2026-08-21 — Exact legacy route migration repair
- Files modified: `scripts/install.py` recognizes only the four exact historical managed Anthropic routes as eligible inputs to an explicit `--account-oauth-tiers` migration, after the managed profile description has matched; `tests/integration/test_lifecycle_install.py` proves the exact legacy set can reach transactional conversion while ordinary preflight and an altered Anthropic model remain rejected.
- Checks run: live RED runs 21–24 all exited before their first model turn with the same Anthropic extra-usage HTTP 400 and no Kanban terminal call. Test RED: both migration regressions failed because preflight had no migration-aware boundary. GREEN: migration regressions 2 passed; installer integration 40 passed; serialized isolated-home full Python suite 207 passed with one dependency deprecation warning; Node tests/build 3 passed each; Python compilation, diff check, and added-line secret scan passed. A first full-suite invocation inherited a stale terminal-only delegated-child marker and correctly failed eight Kanban fixtures plus the E2E; the Desktop serve process did not contain the marker, and the exact rerun with only that stale snapshot value removed passed.
- Decisions made: no general Anthropic exception exists. Migration requires the explicit flag, exact managed role description, exact provider/model/runtime/API-mode tuple, and an empty fallback chain. The transaction still snapshots all existing configs before route conversion and rolls back on failure.
- Live control note: Claude Team account auth and print-mode readiness pass independently. Live profile deployment and recovery remain blocked until immutable review accepts this exact candidate.

### 2026-08-21 — Stage payload write boundary repair
- Files modified: `plugins/hermes-coding-workflow/__init__.py` emits and authorizes one exact absolute `.hermes/hcw-inputs/<stage>.input.json` path for each JSON-consuming stage, binds `--json` to that same path, rejects symlinked payload components, and fail-closes `execute_code`; `tests/plugin/test_native_plugins.py` covers all four stages plus wrong paths, source writes, code execution, and symlink inverses; planner/spec/quality role skills now describe the raw validated payload schemas and exact bootstrap path.
- Checks run: live RED run 17 proved valid design identity could not create the required input file. GREEN: focused mutation matrix 15 passed; native plugin suite 71 passed; serialized isolated-home full Python suite 205 passed with one dependency deprecation warning; Node tests/build 3 passed each; Python compilation, diff check, and added-line secret scan passed. Immutable review found one P2: the planner skill did not name the exact raw plan task/command keys. A RED documentation-contract test reproduced it, the skill now names every required key and RED/GREEN coverage rule, and both native/full suites passed afterward.
- Decisions made: design, plan, spec-review, and quality-review may write only their exact stage-specific metadata input; source remains immutable. Lifecycle JSON commands reject alternate files, relative paths, `/dev/stdin`, duplicate/extra arguments, and symlinked payload authority. General `execute_code` is blocked because it has no explicit auditable target.
- Live control note: design run 18 completed through the old hook by supplying the raw validated payload over `/dev/stdin`; authoritative state advanced to `awaiting_plan`. That workaround demonstrates why the terminal argument must be exact rather than generally readable.
- Concerns: bounded immutable rereview of the additive P2 correction, targeted hook/role-skill redeployment, and a fresh-process installed probe remain required before this repair is accepted.

### 2026-08-21 — Linked-controller bootstrap authorization repair
- Files modified: `plugins/hermes-coding-workflow/__init__.py` uses one exact registered Kanban linked-root predicate for both missing-locator guidance and `create-run` authorization; `tests/plugin/test_native_plugins.py` proves that the exact command emitted for a valid linked controller is accepted.
- Checks run: immutable review RED reproduced a valid `.worktrees/<task>` controller receiving `create-run` guidance while the guard rejected the same command. GREEN: reviewer-focused 25 passed; serialized isolated-home full Python suite 198 passed with one dependency deprecation warning; Node tests/build 3 passed each; Python compilation, diff check, and added-line secret scan passed.
- Decisions made: a linked root is authorized only when its canonical basename equals `HERMES_KANBAN_TASK`, its branch is exactly `wt/<task>`, it is registered under trusted Git authority, and its command repository exactly matches the canonical current directory; generic linked worktrees remain rejected.
- Live control note: the old installed hook caused repeated automatic design-stage promotions while this repair was being verified. The design card was left intact in `triage` and temporarily unassigned to stop dispatch churn; no root retry was initiated.
- Concerns: fresh immutable rereview, targeted hook redeployment, and one stage-only live recovery remain required.

### 2026-08-21 — Nested linked-worktree topology repair
- Files modified: `plugins/hermes-coding-workflow/__init__.py` validates a linked Kanban task worktree and its nested HCW worktree through shared trusted Git authority plus exact worktree-list membership; missing-locator root bootstrap is limited to registered `wt/<task>` workspaces whose basename equals `HERMES_KANBAN_TASK`. `tests/plugin/test_native_plugins.py` models the real nested topology and covers root bootstrap, active stage derivation, missing nested locator, and unrelated linked-worktree rejection.
- Checks run: RED: linked root bootstrap was rejected and nested HCW stage registration returned false. GREEN: security/live-topology-focused 45 passed; serialized isolated-home full Python suite 198 passed with one dependency deprecation warning; Node tests/build 3 passed each; 36-file source compilation, diff check, and added-line secret scan passed.
- Decisions made: controller and stage may both be linked worktrees when they share the same fully validated common Git directory and both exact paths appear in Git's worktree list; root create-run remains narrower than generic linked-worktree membership.
- Deviations from spec: no push, merge, live-profile mutation, or additional Kanban retry.
- Concerns: fresh immutable rereview, targeted hook redeployment, and stage-only live recovery remain required.

### 2026-08-21 — Canonical locator/manifest identity repair
- Files modified: `plugins/hermes-coding-workflow/__init__.py` requires repository and worktree identity fields to be exact canonical absolute existing non-symlink directory spellings before comparison; `tests/plugin/test_native_plugins.py` replays symlink aliases in both locator and authoritative manifest identity fields.
- Checks run: RED: both aliased `repo_root` and `worktree_path` cases emitted active red-stage guidance and authorized the exact lifecycle command. GREEN: security-focused 42 passed; serialized isolated-home full Python suite 195 passed with one dependency deprecation warning; Node tests/build 3 passed each; 36-file source compilation, diff check, and added-line secret scan passed.
- Decisions made: parse locator and manifest repository/worktree identity through one exact canonical directory helper before any authorization or missing-locator matching.
- Deviations from spec: no push, merge, live-profile mutation, or Kanban mutation.
- Concerns: fresh immutable rereview, targeted hook redeployment, and stage-only live recovery remain required.

### 2026-08-21 — Linked-worktree Git marker authority repair
- Files modified: `plugins/hermes-coding-workflow/__init__.py` lstat-validates primary `.git` directories, linked-worktree `.git` regular files, raw `gitdir` targets, and `commondir` metadata before canonicalization; `tests/plugin/test_native_plugins.py` adds the immutable-review symlink replay plus malformed, nonregular, relative-metadata, and symlinked-component coverage.
- Checks run: RED: immutable review reproduced active guidance and exact `hcw check` authorization after replacing a linked worktree's `.git` file with a symlink to valid metadata. GREEN: security-focused 38 passed; serialized isolated-home full Python suite 193 passed with one dependency deprecation warning; Node tests/build 3 passed each; 36-file source compilation, diff check, and added-line secret scan passed.
- Decisions made: trust Git repository authority only after raw marker and metadata provenance passes lstat-based regular-file/directory and no-symlink validation; compare canonical paths only after raw validation.
- Deviations from spec: no push, merge, live-profile mutation, or Kanban mutation.
- Concerns: fresh immutable rereview, targeted hook redeployment, and stage-only live recovery remain required.

### 2026-08-21 — Git common-directory authority repair
- Files modified: `plugins/hermes-coding-workflow/__init__.py` centrally validates raw Git worktree/common-directory authority paths before canonicalization; `tests/plugin/test_native_plugins.py` adds the redirected `.git` symlink regression and ordinary primary/linked-worktree coverage.
- Checks run: RED: the redirected common-directory test failed by emitting active red-stage guidance. GREEN: complete native-plugin contract suite passed.
- Decisions made: relative Git common-directory output is anchored at Git's queried worktree before checking every authority component for symlinks and directory shape; canonicalization occurs only afterward.
- Deviations from spec: none.
- Concerns: none.

### 2026-08-21 — Locator authority repair
- Files modified: `plugins/hermes-coding-workflow/__init__.py` recognizes a linked worktree controlled by exactly one canonical, non-symlinked authoritative run even when its local locator is missing, without deriving stage authority; it rejects symlinked locator and manifest components and limits create-run bootstrap to a canonical repository root. `tests/plugin/test_native_plugins.py` adds immutable-review regressions and inverse coverage for missing locators, ambiguous/malformed state, unregistered worktrees, and locator/manifest parent and leaf symlinks.
- Checks run: RED: both immutable-review regressions failed (missing locator emitted root `create-run` guidance; symlinked `.hermes` emitted active red-stage guidance). GREEN: focused plugin suite passed; isolated temporary-`HERMES_HOME` full Python suite exited 0 (existing FastAPI/TestClient deprecation warning only); Node tests/build passed 3/3; Python compilation, `git diff --check`, and strict added-line credential scan passed.
- Decisions made: derive missing-locator control context only from the current exact Git worktree's canonical parent repository and exactly one safe authoritative match; that recognition produces only invalid-identity guidance and never stage authorization. Root bootstrap remains available only at the canonical repository root.
- Deviations from spec: no push, merge, live-profile mutation, or Kanban mutation.
- Concerns: the extension-local `.venv` lacks `pygments`, and Homebrew pytest runs lifecycle subprocesses without wheel build support; the documented shared Hermes venv was used for the full isolated suite.

### 2026-08-21 — Bootstrap binding error correction
- Files modified: `plugins/hermes-coding-workflow/__init__.py` propagates an invalid active-stage binding into the existing registered-locator fail-closed bootstrap path; `tests/plugin/test_native_plugins.py` adds wrong-task, wrong-profile, inactive-stage, malformed-locator, and symlink-locator bootstrap-message coverage.
- Checks run: RED: three parametrized binding tests failed by emitting initial `create-run` guidance. GREEN: focused native-plugin suite passed; isolated temporary-`HERMES_HOME` full Python suite: 176 passed in 255.91s; Node tests/build: 3 passed each; Python compilation, diff check, and strict added-line secret scan passed. The generic root `ai-workflow checks --level issue` remains blocked because the root package has no `typecheck` script; this is present at clean head and outside this correction.
- Decisions made: reuse the existing locator-present invalid-identity response by assigning the authoritative active-stage binding error before the branch, preserving root bootstrap and stage authorization behavior.
- Deviations from spec: no push, merge, live-profile mutation, or Kanban mutation.
- Concerns: root workflow automation needs a separate configuration fix before its generic issue-level check can run.

### 2026-08-21 — Stage bootstrap locator identity repair
- Files modified: `plugins/hermes-coding-workflow/__init__.py` derives stage identity only from a non-symlinked registered locator and authoritative manifest, gates bootstrap guidance by active task/profile/stage binding, and binds lifecycle commands to the canonical repository; `tests/plugin/test_native_plugins.py` adds nine-stage bootstrap coverage and a symlink-locator rejection; `README.md` documents root versus stage bootstrap behavior.
- Checks run: RED: nine stage-worker assertions failed because bootstrap emitted `create-run`; security RED: a symlinked locator was accepted. GREEN: 10 focused assertions passed; full isolated-home Python suite: 171 passed (one existing FastAPI/TestClient deprecation warning); Node tests/build: 3 passed; Python compile, diff check, and strict added-line secret scan passed.
- Decisions made: derive a missing `HCW_RUN_ID` only after validating the current worktree's non-symlinked locator and authoritative run record; preserve the initial root `create-run` path when no locator exists.
- Deviations from spec: no push, merge, live-profile mutation, or Kanban mutation.
- Concerns: fresh immutable rereview and targeted deployment remain required.

### 2026-08-21 — Alias TOCTOU repair
- Files modified: `plugins/hermes-coding-workflow/__init__.py`, `tests/plugin/test_native_plugins.py`, `README.md`, and this state record.
- Checks run: focused RED showed six failures across both worker commands (symlink alias, deterministic alias swap before CLI resolution, and `..` spelling); focused GREEN passed. Complete Python suite: 161 passed; Node/Desktop: 3 passed; production build, Python compilation, diff check, and added-line secret scan passed.
- Decisions made: reject the authorization-critical repository argument unless it is the existing, lexically normalized, exact canonical absolute spelling stored in `run.repo_root`; no service-side inode binding was added because the existing actor-less CLI has no trusted descriptor handoff and the requested alias class is closed at the guard boundary.
- Deviations from spec: no push, deployment, profile mutation, or Kanban retry.
- Concerns: a fresh immutable rereview and a real installed-profile worker dispatch remain pending.

### 2026-08-21 — OAuth tier-routing authoritative worker repository binding
- Files modified: `plugins/hermes-coding-workflow/__init__.py` binds `dispatch-worker` and `worker-status` to the exact canonical absolute `run.repo_root` spelling; `tests/plugin/test_native_plugins.py` covers canonical and rejected alternate worker-command paths.
- Checks run: focused RED: 14 selected tests, 4 expected failures proving both commands allowed different/nonexistent repositories; focused GREEN: 14 passed. Parent full Python suite: 159 passed with one dependency deprecation warning. Node/Desktop: 3 passed; production build: 3 passed. Python compilation, diff check, and added-line secret scan passed.
- Decisions made: reject symlink aliases and every alternate/mutable path spelling before the CLI can resolve a user-controlled repository argument again; bind only the exact canonical `run.repo_root`, not the isolated implementation worktree.
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
