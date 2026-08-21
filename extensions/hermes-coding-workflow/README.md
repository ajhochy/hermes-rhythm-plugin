# Hermes Coding Workflow

A standalone Hermes plugin, profile, dashboard, and Desktop package that turns coding requests into durable, contract-driven, independently reviewed development runs.

## Intended flow

```text
request → design approval → implementation plan → acceptance contract
        → isolated worktree → RED/GREEN implementation
        → spec review → quality review → verification
        → draft PR/manual merge gate → evidence and project-state update
```

The control plane uses Hermes profiles, Kanban, worktrees, skills, hooks, and Desktop plugin APIs. Hermes itself — the orchestrator and every one of its profiles — stays on GPT-5.6-Sol through OpenAI account OAuth; there is no Hermes-native Anthropic routing. The `red`, `green`, `quality-review`, and `complete` stages are instead dispatched to an external, asynchronous Claude Code CLI subprocess authenticated by its own Claude Team/account login, never an API key. The authoritative product contract is `docs/ai/contracts/workflow-v2.json`; v1 is retained only as superseded history.

The methodology incorporates selected principles from Jesse Vincent's MIT-licensed `obra/superpowers`, with explicit attribution in `THIRD_PARTY_NOTICES.md` and adapted behavior tests.

## Install

Installation is explicit and local-only. It never uses the current user's home by default, contacts a network service, edits Hermes configuration files directly, or depends on a sibling worktree. The repository root is the control plane.

Create a **Hermes-tool-dispatch** source profile in the target home first, then install. Its name must be distinct from all managed workflow role names; installer and doctor reject a collision before mutation or scanning. Direct-tool providers such as `copilot-acp`, Claude Code ACP, and OpenCode ACP are rejected before any mutation because their file tools do not pass through Hermes `pre_tool_call` hooks. Both `openai` and `openai-codex` are runtime-checked before the native-provider allowlist; `codex_app_server` under either supported config spelling and unknown runtime values remain fail-closed.

```sh
export HERMES_HOME=/path/to/isolated-hermes-home
hermes profile create dev --no-alias
# Configure dev with a supported native provider/model before install.
python scripts/install.py --hermes-home "$HERMES_HOME" --source-profile dev
python scripts/doctor.py --hermes-home "$HERMES_HOME" --source-profile dev
```

The installer preflights Hermes, the source/orchestrator provider, native plugin manifests, the root Python control plane, dashboard API, Desktop ESM file, role skills, and pinned Superpowers skills. The unsafe/default base receives only the read-only dashboard package and Desktop asset. The source/orchestrator and every workflow role receive the enforcement/runtime packages:

```text
$HERMES_HOME/plugins/hcw-dashboard/               read-only dashboard API; no mutation hook
$HERMES_HOME/desktop-plugins/hcw/plugin.js        Desktop ESM disk plugin
$HERMES_HOME/profiles/dev/plugins/hcw/            source/orchestrator hook, skills, runtime
$HERMES_HOME/profiles/dev/plugins/superpowers/    pinned Superpowers skills
$HERMES_HOME/profiles/dev-*/plugins/{hcw,superpowers}/
```

The local command is always the installed launcher:

```sh
$HERMES_HOME/profiles/dev/plugins/hcw/runtime/bin/hcw --help
```

Role profiles are created with Hermes's supported `profile create --clone-from dev --no-alias` flow and precise routing descriptions: `dev-planner`, `dev-contract`, `dev-builder`, `dev-spec-reviewer`, `dev-quality-reviewer`, `dev-verifier`, and `dev-recorder`. The source and all roles must retain supported Hermes-tool-dispatch providers. Plugin enablement and scanner validation use supported Hermes CLI commands; no `config.yaml` is edited directly.

For account-subscription routing with no API keys, authenticate `hermes auth add openai-codex`, then add `--account-oauth-tiers` to the install command. Every installed Hermes profile — orchestrator, planner, spec reviewer, contract writer, builder, quality reviewer, verifier, and recorder — routes to OpenAI OAuth with `gpt-5.6-sol` (verification instead uses `gpt-5.6-terra`). No installed profile is ever configured with provider `anthropic`, and no Hermes-side Anthropic credential is required. Every profile explicitly sets `model.openai_runtime: auto`, pins its native Hermes API mode (`codex_responses`), and clears inherited fallback providers, so no API-key or direct-tool route is attempted. OpenAI OAuth is accepted only through Hermes's `codex_responses` loop; either config spelling for `codex_app_server`, plus unknown runtime values, remains fail-closed because app-server owns its tools outside Hermes hooks. Verify exact routes, empty fallback chains, and active OAuth credential metadata with:

```sh
python scripts/doctor.py --hermes-home "$HERMES_HOME" --source-profile hcw-dev --account-oauth-tiers --verify-account-oauth --verify-claude-cli
```

`--verify-claude-cli` additionally confirms the external `claude` executable has an active Claude Team/Pro/Max account-subscription login and is print-mode ready; API-key/Console auth and unknown auth states fail closed. It never depends on a Hermes profile or API key. Tests and isolated validation inject a disposable fake executable through `HCW_CLAUDE_CLI` rather than touching a live account.

### Claude Code CLI worker stages

The `red`, `green`, `quality-review`, and `complete` stages of every run are executed by the Claude Code CLI, dispatched and supervised by Hermes rather than run inside it:

- `hcw dispatch-worker <repo> <run-id> <stage>` reserves a durable `worker-<run>-<stage>-<attempt>-<n>` record (see the run's `workers/` directory, e.g. `.hermes/workflows/<run-id>/workers/<stage>-<attempt>-<n>.json`), then spawns a fully detached `python -m hermes_coding_workflow.worker_runner` process and returns immediately — the CLI invocation never blocks on Claude. That detached runner is the process that actually invokes `claude -p --output-format json --model <tier-model> --max-turns <n> --allowedTools <least-privilege set> --safe-mode --no-session-persistence` with its stdin set to a context-free brief built solely from the run's durable `plan.json`/`approved-design.json` artifacts, and atomically records the terminal `succeeded`/`failed` state, exit code, and hashed stdout/stderr artifact paths when the subprocess exits.
- `hcw worker-status <repo> <run-id> <stage>` reads back the latest worker record (`queued`, `running`, `succeeded`, or `failed`) without blocking, so the orchestrator can poll a long-running Claude subprocess instead of holding it synchronously.
- The backend/model map is fixed and durable (`hermes_coding_workflow.contracts.CLAUDE_TIER_MODELS`): `red` and `green` run on `claude-sonnet-4-6`, `quality-review` on `claude-opus-4-6`, and `complete` on `claude-haiku-4-5`. All four are tagged `backend: "claude-code-cli"` in their worker record, never a Hermes provider name.
- The worker receives a credential-minimal operational allowlist (`HOME`/keychain context, `PATH`, locale/temp/certificate paths), not the parent control-plane environment. API-key/token/password/cloud-backend variables are absent, Claude tool subprocesses receive an explicit credential scrub list, and Hermes actor identity (`HERMES_PROFILE`, `HERMES_KANBAN_TASK`, `HERMES_SESSION_ID`, `HERMES_MODEL`, `HERMES_PROVIDER`) is injected. `claude` authenticates through its own Team/Pro/Max account login, never a Hermes-held credential.
- Claude's own internal tool calls (file edits, `git`, test commands) never pass through Hermes `pre_tool_call` hooks — that hook boundary only wraps Hermes's own agent loop, not an external CLI's subprocess tree. Safety instead comes from: confinement to the run's controlled, non-symlinked `.worktrees/` worktree (`safety.validate_controlled_worktree`); exact stage/task/brief identity checked before dispatch so a worker can only ever act on the one durable task it was issued; least-privilege `--allowedTools` per stage (e.g. quality review gets `Read,Grep,Glob` only, never write access); redacted, hashed process artifacts (stdout/stderr) recorded for every run; and the durable independent spec/quality review and verification gates the orchestrator still enforces on the candidate after any worker exits.

## Remove

```sh
python scripts/uninstall.py --hermes-home "$HERMES_HOME"
```

Removal disables `hcw-dashboard` in base and `hcw`/`superpowers` in the source and role homes before removing only owned plugin/Desktop payloads. It preserves profiles and unrelated files, configuration, and secrets. Add `--remove-profiles` only when deliberately removing role profiles created by this installer; pre-existing profiles remain untouched.

## Public workflow CLI

Use the profile-local absolute launcher printed by the `HCW_BOOTSTRAP_V1` hook. The public lifecycle is `create-run`, `approve-design`, `approve-plan`, `check`, `commit`, `review`, `verify`, `complete`, `repair`, `show`, `dispatch-worker`, and `worker-status`. `dispatch-worker`/`worker-status` launch and poll the external Claude Code CLI subprocess for the current `red`/`green`/`quality-review`/`complete` stage; see "Claude Code CLI worker stages" above.

`create-run` creates the isolated worktree, locator, task graph, and authoritative `hcw/v1` run record. `verify` is the deterministic gate which activates `live`; a real acceptance command must then be recorded through `check live` before completion. `commit` records the candidate identity. Reviews carry reviewer identity, findings, and separate dispositions. A changes-requested result requires `repair`, which starts a fresh attempt. Completion is a draft-handoff/card-completion action only; merge is manual.

Direct tool/provider output is never acceptance evidence. Hermes task identity, the recorded candidate SHA, bounded hashed artifacts, and a real installed-Hermes acceptance run are the safety boundary.

## Validation and E2E

`scripts/doctor.py` validates the real Hermes scanner/registration, local `hcw --help`, role descriptions, dashboard API payload, Desktop ESM payload, pinned skill namespaces, no remote branding, and every profile-local copy.

`tests/integration/test_lifecycle_install.py` and `tests/e2e/test_disposable_repo.py` exercise the public installed launcher and real Hermes Kanban host. The E2E is mandatory acceptance: it creates a run, uses graph-issued actor/task identities, records RED/GREEN/deterministic/live checks, reviews, repair when needed, and a manual-merge handoff. No provider call, mock runner, or environment-gated substitute can satisfy that contract.

Status: the predecessor OpenAI OAuth route is installed through `hcw-dev`, and every Hermes profile routes through OpenAI account OAuth with no `anthropic` provider or fallback. The external asynchronous Claude CLI adapter for `red`/`green`/`quality-review`/`complete` is a verified branch candidate, not yet live-installed: 126 Python tests, 3 Node/Desktop tests and the production build pass, with zero skipped/xfail markers. Independent rereview and a real post-reset Team-account dispatch smoke remain required before installation or publication. Existing `dev` remains unchanged. See `docs/ai/project-state.md`.
