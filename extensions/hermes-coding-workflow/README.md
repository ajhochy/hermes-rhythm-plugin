# Hermes Coding Workflow

A standalone Hermes plugin, profile, dashboard, and Desktop package that turns coding requests into durable, contract-driven, independently reviewed development runs.

## Intended flow

```text
request → design approval → implementation plan → acceptance contract
        → isolated worktree → RED/GREEN implementation
        → spec review → quality review → verification
        → draft PR/manual merge gate → evidence and project-state update
```

The control plane uses Hermes profiles, Kanban, worktrees, skills, hooks, and Desktop plugin APIs. OpenCode, Claude Code, Codex, and native Hermes agents remain replaceable worker backends when their tool-execution boundary satisfies the provider preflight. The authoritative product contract is `docs/ai/contracts/workflow-v2.json`; v1 is retained only as superseded history.

The methodology incorporates selected principles from Jesse Vincent's MIT-licensed `obra/superpowers`, with explicit attribution in `THIRD_PARTY_NOTICES.md` and adapted behavior tests.

## Install

Installation is explicit and local-only. It never uses the current user's home by default, contacts a network service, edits Hermes configuration files directly, or depends on a sibling worktree. The repository root is the control plane.

Create a **Hermes-tool-dispatch** source profile in the target home first, then install. Direct-tool providers such as `openai-codex`, `copilot-acp`, Claude Code ACP, and OpenCode ACP are rejected before any mutation because their file tools do not pass through Hermes `pre_tool_call` hooks.

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

## Remove

```sh
python scripts/uninstall.py --hermes-home "$HERMES_HOME"
```

Removal disables `hcw-dashboard` in base and `hcw`/`superpowers` in the source and role homes before removing only owned plugin/Desktop payloads. It preserves profiles and unrelated files, configuration, and secrets. Add `--remove-profiles` only when deliberately removing role profiles created by this installer; pre-existing profiles remain untouched.

## Public workflow CLI

Use the profile-local absolute launcher printed by the `HCW_BOOTSTRAP_V1` hook. The public lifecycle is `create-run`, `approve-design`, `approve-plan`, `check`, `commit`, `review`, `verify`, `complete`, `repair`, and `show`.

`create-run` creates the isolated worktree, locator, task graph, and authoritative `hcw/v1` run record. `verify` is the deterministic gate which activates `live`; a real acceptance command must then be recorded through `check live` before completion. `commit` records the candidate identity. Reviews carry reviewer identity, findings, and separate dispositions. A changes-requested result requires `repair`, which starts a fresh attempt. Completion is a draft-handoff/card-completion action only; merge is manual.

Direct tool/provider output is never acceptance evidence. Hermes task identity, the recorded candidate SHA, bounded hashed artifacts, and a real installed-Hermes acceptance run are the safety boundary.

## Validation and E2E

`scripts/doctor.py` validates the real Hermes scanner/registration, local `hcw --help`, role descriptions, dashboard API payload, Desktop ESM payload, pinned skill namespaces, no remote branding, and every profile-local copy.

`tests/integration/test_lifecycle_install.py` and `tests/e2e/test_disposable_repo.py` exercise the public installed launcher and real Hermes Kanban host. The E2E is mandatory acceptance: it creates a run, uses graph-issued actor/task identities, records RED/GREEN/deterministic/live checks, reviews, repair when needed, and a manual-merge handoff. No provider call, mock runner, or environment-gated substitute can satisfy that contract.

Status: complete candidate is installed through the safe `hcw-dev` source profile. Parent gates, independent review, isolated installed E2E, and an active-home tracer run all pass; the live board's nine stage tasks are all `done`. Existing direct-tool `dev` remains unchanged. See `docs/ai/project-state.md` and `docs/ai/runs/terra-final-reconcile.md`.
