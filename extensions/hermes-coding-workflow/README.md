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

Create a **Hermes-tool-dispatch** source profile in the target home first, then install. Direct-tool providers such as `copilot-acp`, Claude Code ACP, and OpenCode ACP are rejected before any mutation because their file tools do not pass through Hermes `pre_tool_call` hooks. Both `openai` and `openai-codex` are runtime-checked before the native-provider allowlist; `codex_app_server` under either supported config spelling and unknown runtime values remain fail-closed.

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

For account-subscription routing with no API keys, first authenticate both pools with `hermes auth add openai-codex` and `hermes auth add anthropic --type oauth`, then add `--account-oauth-tiers` to the install command. The source orchestrator, planner, and spec reviewer use OpenAI OAuth with `gpt-5.6-sol`; contract and builder use Claude Sonnet 4.6; quality review uses Claude Opus 4.6; verification uses `gpt-5.6-terra`; recording uses Claude Haiku 4.5. Every profile explicitly sets `model.openai_runtime: auto`, pins its native Hermes API mode (`codex_responses` for OpenAI or `anthropic_messages` for Anthropic), and clears inherited fallback providers, so no API-key or direct-tool route is attempted. OpenAI OAuth is accepted only through Hermes's `codex_responses` loop; either config spelling for `codex_app_server`, plus unknown runtime values, remains fail-closed because app-server owns its tools outside Hermes hooks. Verify exact routes, empty fallback chains, and active OAuth credential metadata with:

```sh
python scripts/doctor.py --hermes-home "$HERMES_HOME" --source-profile hcw-dev --account-oauth-tiers --verify-account-oauth
```

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

Status: the OAuth-tier candidate is installed through `hcw-dev`; OpenAI Sol live inference and all structural gates pass. Anthropic OAuth is authenticated but live Anthropic inference remains pending account extra-usage entitlement. Existing `dev` remains unchanged. See `docs/ai/project-state.md`.
