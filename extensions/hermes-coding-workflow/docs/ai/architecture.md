# Architecture — Hermes Coding Workflow

## Goal

Provide the complete coding workflow as a standalone Hermes extension: automatic design-first routing, approved specifications, granular implementation plans, strict TDD, isolated worktrees, fresh worker contexts, two-stage independent review, evidence-bound verification, draft-PR handoff, Desktop run visibility, and durable recovery.

## System boundary

```text
Hermes Desktop
  └─ Desktop disk plugin (ESM)
       └─ ctx.rest('/runs/...')
            └─ scoped dashboard plugin API (Python)
                 └─ workflow service
                      ├─ Hermes Kanban CLI/modules — durable cards, dependencies, runs, review
                      ├─ git/worktree adapter — exact base/candidate identity
                      ├─ repository manifests — contracts and bounded evidence
                      ├─ profile dispatcher — planner/builder/reviewer/verifier roles
                      └─ GitHub adapter — draft PR only
```

Hermes Kanban is the task-state authority. The package stores only immutable contracts, evidence manifests, review reports, and mappings to Kanban IDs.

## Installation boundary

The post-merge control plane is this repository root. Lifecycle scripts must never resolve a sibling `control-plane` worktree. Given an explicit base `HERMES_HOME` and existing `dev` source profile, installation creates the seven role homes through Hermes CLI, then stages each native payload independently into the base home and each role home:

```text
repository root
  ├─ src/hermes_coding_workflow/       Python control plane packaged into hcw/runtime/site
  ├─ plugins/hermes-coding-workflow/   source native hcw plugin
  ├─ plugins/superpowers-pinned/       source native superpowers plugin
  ├─ dashboard/                        copied exactly to hcw/dashboard
  └─ desktop/plugin.js                 copied exactly to desktop-plugins/hcw/plugin.js

HERMES_HOME
  ├─ plugins/hcw-dashboard/            read-only dashboard API (no mutation hooks)
  └─ desktop-plugins/hcw/plugin.js     Desktop disk plugin
HERMES_HOME/profiles/<safe-source> and every HERMES_HOME/profiles/dev-*/
  ├─ plugins/hcw/                      hooks, skills, dashboard API, local runtime/bin/hcw
  ├─ plugins/superpowers/              pinned skills
  └─ desktop-plugins/hcw/plugin.js     Desktop disk plugin
```

Payload replacement is transactional. Before any mutation, both the source/orchestrator profile and all existing roles must use the native safe provider `openai` with model `gpt-4o-mini`; unknown/direct-code providers fail closed. On failure, base, source, and existing role configuration bytes and enablement mutations are restored. The base never enables the `hcw` mutation hook. Enable/disable and doctor operations use the supported Hermes plugin CLI, never direct `config.yaml` edits.

## Role model

| Role | Purpose | Write authority |
|---|---|---|
| Orchestrator | Intake, graph creation, gate transitions | Workflow metadata only |
| Planner | Design interview, alternatives, approved spec and plan | Design/plan artifacts |
| Contract writer | Executable acceptance tests and RED evidence | Tests/contracts |
| Builder | Minimal implementation in isolated worktree | Assigned source/test scope |
| Spec reviewer | Compare immutable candidate to approved spec | Read-only |
| Quality reviewer | Correctness, simplicity, maintainability, security | Read-only |
| Verifier | Fresh deterministic and live behavior gates | Evidence only |
| Recorder | Draft PR, docs/ai and Dashboard projection | Metadata/docs only |

A profile/session cannot approve its own implementation.

## Run graph

```text
intake
  → brainstorming/design approval
  → plan
  → worktree + acceptance contract + observed RED
  → implementation
  → spec review
  → quality review
  → verification
  → draft PR/manual merge handoff
  → project-state and run record
```

A failed stage creates a bounded repair card linked to the failed evidence. The repair produces a new candidate SHA and invalidates all prior reviews and verification.

## Superpowers-derived principles

Adapted from `obra/superpowers` at `b36e0829c6d0140e93cfef2ca599b1b07d4a7797`:

1. **Automatic skill discipline:** coding intent routes to design before source mutation.
2. **Socratic design:** one decision at a time; alternatives and tradeoffs; explicit approval artifact.
3. **Implementation plans for a context-free worker:** exact paths, behavior, tests, commands, and completion criteria.
4. **True TDD:** each behavior records an expected failing run before a passing run.
5. **Fresh context per task:** workers receive the complete bounded task, not accumulated conversational residue.
6. **Two-stage review:** spec compliance must pass before code quality begins.
7. **Evidence before completion:** fresh command output and observable behavior bind to the exact candidate SHA.
8. **Systematic debugging:** reproduce, trace root cause, form/test one hypothesis, then repair with a regression test.
9. **Review reception:** findings are technically verified; valid blockers are fixed, invalid findings receive evidence-based disposition.
10. **Worktree and branch safety:** provenance-aware cleanup, no forced deletion, draft PR/manual merge.
11. **YAGNI/DRY:** no uncontracted features; duplication is removed only after green behavior.

The package enforces these as transition predicates, not optional prose.

## Durable artifacts

Each run lives under `.hermes/workflows/<run-id>/` in the target repository. `run.json` is the authoritative `hcw/v1` record: it contains `stage_profiles`, `stage_statuses`, `kanban_task_ids`, and one `dispatches[stage]` identity (`stage`, task ID, profile, provider, model, session ID, attempt, brief hash). The UI derives its active actor solely from that record.

```text
run.json
approved-design.json
plan.json
evidence.jsonl
reviews.json
verification.json
handoff.json
```

Evidence records contain bounded command metadata, exit status, timestamps, hashes, and safe excerpts. They exclude prompts, transcripts, secrets, and raw tool arguments.

## Transition safety

- Every transition uses expected run revision and current git SHA.
- Review/verification reports name their candidate SHA.
- New commits automatically stale prior review and verification.
- Dirty or untracked source state blocks review and completion.
- Scope checks include tracked, staged, unstaged, and untracked files.
- `verify` is the deterministic gate that activates the live stage. A real `check live` acceptance result is mandatory before `complete`.
- Default branch merge is never automated.

## Desktop surface

A native `Coding Runs` page provides:

- board/repository selector;
- run and stage status;
- dependency graph;
- assigned profile/model and attempts;
- branch and base/candidate SHAs;
- safe evidence summaries;
- review findings and dispositions;
- retry history and blockers;
- links to local artifacts and draft PR.

The UI is a read-only projection. It uses descriptor-bound, no-follow regular-file reads in the controlled workflow directory, bounds and redacts every untrusted exported string, and never returns paths, commands, transcripts, or secrets. It cannot mutate git or bypass workflow transitions.

The API payload is copied into every `hcw/dashboard` package and the Desktop ESM payload into every profile-local `desktop-plugins/hcw/plugin.js`, so dispatched workers and the base Desktop see the same installed release rather than checkout-relative files.

## Delivery

The repository ships:

- Python package and `hcw` CLI;
- native Hermes plugin lifecycle package;
- scoped dashboard API;
- bundled Desktop disk plugin;
- role and bootstrap skills;
- install/uninstall/doctor scripts;
- schema and unit/contract/security tests;
- disposable-repository end-to-end acceptance harness;
- third-party notices and methodology attribution.
