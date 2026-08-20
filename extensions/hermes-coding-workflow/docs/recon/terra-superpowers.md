# Superpowers Methodology Reconstruction

Source reviewed: [`obra/superpowers` at `b36e0829c6d0140e93cfef2ca599b1b07d4a7797`](../../../../superpowers-analysis) (version `6.3.0`). This is an analysis and adaptation record, not a claim that the source itself provides hard runtime enforcement. It separates the source's mandatory prose from the durable controls Hermes Coding Workflow should implement.

## Exact source inventory

### Entry points, policy, and runtime bootstrap

| Path | Role / evidence supplied |
|---|---|
| `README.md` | Declares the design → plan → TDD → review → finish workflow, the fourteen-skill library, platform installation, philosophy, and MIT license pointer. |
| `AGENTS.md` | Present but empty at the pinned revision. |
| `CLAUDE.md`, `GEMINI.md` | Present but empty at the pinned revision. |
| `LICENSE` | MIT, copyright © 2025 Jesse Vincent; preservation condition for copies or substantial portions. |
| `.claude-plugin/plugin.json`, `.cursor-plugin/plugin.json`, `.codex-plugin/plugin.json`, `.devin-plugin/plugin.json`, `.kimi-plugin/plugin.json`, `gemini-extension.json`, `.hermes-plugin/plugin.yaml` | Harness metadata; Codex exposes `./skills/`; Kimi declares `using-superpowers` at session start; Hermes declares the `pre_llm_call` hook. |
| `hooks/hooks.json`, `hooks/hooks-cursor.json`, `hooks/session-start`, `hooks/run-hook.cmd` | Claude/Cursor/Copilot session bootstrap, including startup/clear/compact trigger and platform-specific context JSON. |
| `.opencode/INSTALL.md`, `.opencode/plugins/superpowers.js` | OpenCode setup, skill registration, bootstrap injection into first user message, duplicate-injection guard, and content cache. |
| `.pi/extensions/superpowers.ts` | Pi registration and startup/post-compaction bootstrap path. |
| `.hermes-plugin/__init__.py` | Hermes skill registration and first-turn `pre_llm_call` bootstrap construction. |
| `skills/using-superpowers/references/{codex-tools,hermes-tools,gemini-tools,pi-tools,antigravity-tools}.md` | Harness tool substitutions that make generic skill directives executable. |

### All fourteen skills inspected

| # | Exact path | Primary control intent |
|---:|---|---|
| 1 | `skills/using-superpowers/SKILL.md` | Before every response/action, load any possibly applicable skill; user instructions override skills. |
| 2 | `skills/brainstorming/SKILL.md` | Classify spike/bounded/architectural work; require an approved design before implementation. |
| 3 | `skills/writing-plans/SKILL.md` | Produce context-free, exact, 2–5 minute TDD tasks with interfaces and verification. |
| 4 | `skills/executing-plans/SKILL.md` | Execute a reviewed plan in an isolated workspace with checkpoints. |
| 5 | `skills/subagent-driven-development/SKILL.md` | Fresh implementer per task, task review, bounded repair loop, final branch review, durable ledger. |
| 6 | `skills/dispatching-parallel-agents/SKILL.md` | Parallelize only independent investigation domains. |
| 7 | `skills/test-driven-development/SKILL.md` | Enforce observed RED → minimal GREEN → REFACTOR. |
| 8 | `skills/systematic-debugging/SKILL.md` | Root-cause investigation, pattern analysis, one hypothesis, then tested repair. |
| 9 | `skills/requesting-code-review/SKILL.md` | Request scoped independent review after tasks, features, and before merge. |
| 10 | `skills/receiving-code-review/SKILL.md` | Understand and verify feedback before acting; evidence-based pushback. |
| 11 | `skills/verification-before-completion/SKILL.md` | Fresh full evidence before any success/completion claim. |
| 12 | `skills/using-git-worktrees/SKILL.md` | Detect existing isolation, prefer native worktrees, baseline-test safely. |
| 13 | `skills/finishing-a-development-branch/SKILL.md` | Full test gate, manual integration choice, provenance-aware cleanup. |
| 14 | `skills/writing-skills/SKILL.md` | Apply TDD and adversarial evaluations to the skills themselves. |

### Relevant executable checks inspected

| Paths | What they prove |
|---|---|
| `tests/hermes/test_bootstrap.py`, `tests/hermes/test_plugin.py`, `tests/hermes/conftest.py` | Hermes registers discovered skills as `Path`s, injects the full `using-superpowers` body only on first turn, includes the Hermes mapping, strips frontmatter, supports clone/flat layouts, and stays under Hermes's 10,000-character spill limit. |
| `tests/hooks/test-session-start.sh` | SessionStart registration uses Bash; Claude, Cursor, and Copilot receive exactly their expected JSON context shape; obsolete legacy warning is absent. |
| `tests/opencode/test-bootstrap-caching.mjs`, `tests/opencode/test-plugin-loading.sh`, `tests/opencode/test-priority.sh`, `tests/opencode/test-tools.sh` | OpenCode injects once, caches present/missing bootstrap lookup, avoids stale tool mappings, registers skills, and preserves precedence/tool adaptation. |
| `tests/pi/test-pi-extension.mjs` | Pi extension startup/compaction bootstrap and skill integration. |
| `tests/claude-code/test-subagent-driven-development.sh`, `tests/claude-code/test-subagent-driven-development-integration.sh`, `tests/claude-code/test-sdd-workspace.sh` | SDD prompt/template, review-package, task-brief, plan-scoped workspace, and recovery-ledger behavior. |
| `tests/claude-code/test-worktree-native-preference.sh`, `tests/claude-code/test-worktree-path-policy.sh` | Native-worktree preference and safe project-local worktree path/ignore policy. |
| `tests/explicit-skill-requests/run-all.sh` and `tests/explicit-skill-requests/prompts/*.txt` | Drill/evaluation coverage for explicit and contextual skill invocation behavior. |
| `tests/codex/test-marketplace-manifest.sh`, `tests/codex-plugin-sync/test-sync-to-codex-plugin.sh` | Codex metadata and safe plugin synchronization/bootstrap behavior. |

Supporting source material also read where referenced by the skills: `skills/test-driven-development/writing-good-tests.md`; `skills/systematic-debugging/{root-cause-tracing,defense-in-depth,condition-based-waiting}.md`; and SDD's `implementer-prompt.md`, `task-reviewer-prompt.md`, `re-review-prompt.md`, `scripts/task-brief`, `scripts/review-package`, and `scripts/sdd-workspace`.

## Workflow state machine

```text
INTAKE
  └─ bootstrap + relevant-skill check
      └─ classify: SPIKE | BOUNDED | ARCHITECTURAL

SPIKE: approved probe → investigate → recommendation (throwaway output)
BOUNDED: context + short design → explicit approval → implementation
ARCHITECTURAL: questions → alternatives → section approvals → written spec
              → self-review → user spec approval → implementation plan

PLAN READY → isolated worktree + clean baseline → task loop
TASK LOOP: observed RED → minimal GREEN → review(spec then quality)
           → clean: next task
           → blocker: bounded repair + re-review; new SHA invalidates prior review

ALL TASKS → final whole-branch review → fresh verification →
manual choice: local merge | draft PR | keep branch
```

The source has two execution routes. `executing-plans` performs a human-checkpointed sequential plan in a separate session. `subagent-driven-development` (SDD) is the recommended route when tasks are mostly independent in the current session: it persists a per-plan ledger, creates a task brief/report/review package, dispatches a focused worker, runs review, and caps repair rounds at five. Hermes should model these as explicit states and only permit transitions when the corresponding artifacts validate.

## Principles translated into enforceable controls

Every row has both a predicate that software can reject and a durable evidence artifact. “Observed” means recorded from an actual command/session, not inferred from prose or a worker's claim.

| Principle | Machine-enforceable invariant | Required evidence artifact |
|---|---|---|
| Mandatory bootstrap / auto-trigger | Before a coding-intent run can mutate tracked source, `bootstrap_seen=true`, the current skill-routing version is recorded, and classification is complete. Compaction/resume must re-establish this predicate where the harness supports it. | `bootstrap.json`: harness, hook/transform event, plugin+skill SHA/version, timestamp, routing decision; bootstrap integration test transcript. |
| Brainstorming and explicit spec approval | No implementation stage is creatable without a classification and approval binding the requested scope. Bounded work may use approved in-chat design; architectural work requires approved immutable spec revision. | `approved-design.md` or `spec.json` with classification, alternatives/trade-offs as applicable, approver/time, content hash. |
| Plan granularity / context-free execution | A task is accepted only if it names exact paths, consumes/produces interfaces, test command, expected RED/GREEN outcome, and completion criterion. It must be independently reviewable; placeholders are rejected. | `implementation-plan.md` plus `plan-lint.json` mapping every spec requirement to task and every task to files/tests/interfaces. |
| RED–GREEN proof | For each behavior-changing production diff, a matching test identity has an earlier failing execution on the same baseline and a later passing execution after the candidate change. A passing-only test is insufficient. | `red-evidence.json` and `green-evidence.json`: test selector, command, exit status, safe output excerpt, base SHA/candidate SHA, timestamps. |
| YAGNI / DRY | Candidate scope must trace every new public behavior/dependency/configuration to a spec or approved ruling. Duplicate logic findings must be dispositioned only after behavior is green; speculative API/options are rejected. | `scope.json` (changed files, dependency delta, requirement trace), review report with YAGNI/duplication checks, and any `rulings.json`. |
| Fresh-subagent-per-task | Implementer session/profile identity for task *n* cannot equal the implementer identity for unrelated task *n+1*; the prompt can reference only the task brief, interfaces, global constraints, and explicit prior rulings—not full conversation history. Small same-shape edits may be one declared batch. | `dispatch.json` per task/batch: role/profile/session ID, brief hash/path, allowed context sources, base SHA, report path. |
| Two-stage review | Spec review must pass on exact candidate SHA before quality review may start. Both reviewers are read-only and have identities different from the builder and from each other. | `reviews/spec.json`, then `reviews/quality.json`, each naming candidate SHA, reviewer identity, scope, verdict/findings. |
| Receiving-review discipline | A finding cannot be silently dismissed. It must be `fixed`, `deferred`, `contested`, or `invalid`, with technical reasoning and evidence; unclear/conflicting feedback blocks partial action until clarified or ruled. | `finding-dispositions.json` linking finding ID to code/test/diff evidence and approver/ruling. |
| Systematic debugging | A repair for a bug/test failure requires ordered root-cause, reproduction, comparison/pattern, hypothesis, and regression-test records. More than three failed repair hypotheses blocks automatic retry and requires architecture review. | `debugging.json` with reproduction command, observed failure, causal trace, hypothesis experiments, attempt count, architecture-review flag. |
| Verification before completion | Completion/commit/PR/merge transitions require fresh commands declared by the plan/contract and executed against the immutable candidate SHA; results must be complete and zero-failure. New commit or dirty tree stales approval. | `verification.json`: SHA, clean-tree state, command list, exit codes, counts, timestamps, hashes of safe output; stale-status calculation. |
| Worktree safety | Build source writes occur only in a registered isolated worktree whose branch/base/provenance are known. A worktree directory is checked ignored before manual creation; baseline failures block automatic implementation. | `workspace.json`: top-level, git dir/common dir, submodule check, branch/base SHA, native/fallback provenance, ignore check, baseline test evidence. |
| Branch finishing / manual merge | Default branch merge, push, destructive cleanup, and discard are never automatic. A final green suite runs on the integration candidate; PR is draft-only by default; deletion requires explicit `discard` confirmation and enumerated target. | `handoff.json`: base/feature/candidate SHA, full-suite evidence, selected human action, draft PR URL or local merge proof, cleanup decision and confirmation. |
| Durable recovery | Restart/compaction must resume from durable run state, not model recollection. A task recorded complete for its exact commit range cannot be re-dispatched. | revisioned `run.json`, stage graph, task ledger, artifact hashes, and replay/resume test. |

## Bootstrap and automatic behavior

The central design is deliberately small: bootstrap injects the full `using-superpowers` skill, which says that any ≥1% chance a skill applies requires loading it before *any* response or action, including clarification or repository inspection. The bootstrap itself is more enforceable than the downstream compliance: hooks and transforms are executable, while “invoke the skill” is model instruction unless a workflow controller checks it.

Platform behaviors at the pinned revision:

- Claude/Cursor/Copilot: `hooks/hooks.json` invokes `hooks/session-start` for `startup|clear|compact`. The script injects only the platform's expected JSON field to avoid duplicate Claude context.
- OpenCode: `experimental.chat.messages.transform` registers the skills directory and prepends bootstrap to the first user message, with a duplicate marker guard and module-level cache.
- Pi: startup and post-compaction injection are explicitly described in `README.md` and implemented by `.pi/extensions/superpowers.ts`.
- Kimi: plugin manifest declares `sessionStart.skill: "using-superpowers"` and maps its native tools.
- Hermes: `.hermes-plugin/__init__.py` registers every stock skill and injects on first `pre_llm_call`. The README documents a limitation: Hermes lacks a post-compaction hook, so a long compaction can lose bootstrap; a new session is the source fallback.
- Codex: `.codex-plugin/plugin.json` exposes the skills directory but declares no hook. The runtime must therefore provide its own durable pre-mutation router rather than assume marketplace installation creates an automatic gate.

For agent-stack, record bootstrap as an audited stage transition, not merely prompt text. The hard rejection is: source mutation without a same-run routing artifact. Add explicit resume/compaction tests for each supported harness; in Hermes, detect a missing active bootstrap and mark the run `pending_rebootstrap` rather than silently continuing.

## Design approval and plan quality

`brainstorming` is unusually strong about scope ratcheting. A spike is approved before investigation and stays throwaway; a bounded change gets a short in-chat design and an explicit stop for approval; an architectural change gets one question at a time, 2–3 approaches, sectioned design approval, written spec self-review, then a separate user review gate. Any discovered complexity upgrades but never downgrades the process.

`writing-plans` turns the approval into a worker-readable contract: each task carries exact files, interfaces, literal code/test steps, expected outputs, and commit point. It rejects “TBD,” “appropriate validation,” “write tests,” and cross-task handwaving. The practical invariant is a plan linter with structural checks plus human spec approval; no static linter can prove a task really takes 2–5 minutes, but it can reject absent tests, paths, interface contracts, and verification commands.

## RED–GREEN, YAGNI, and DRY

The source's strongest non-negotiable is TDD's “no production code without a failing test first.” If code was written first, its prescribed remedy is deletion—not adapting it as reference—then fresh test-first implementation. RED must fail for the feature's absence rather than typo/error; GREEN is the smallest code that passes; refactoring is only after green and stays green. `writing-good-tests.md` further asks the author to name the production change that would make the test fail, assert real behavior rather than mocks, keep test-only code out of production, and understand dependencies before mocking.

YAGNI appears in brainstorming, planning, TDD, and review reception: do not add speculative options, unused endpoints, broad refactors, or “proper” infrastructure unsupported by actual usage/spec. DRY is intentionally subordinate to green behavior: remove genuine duplication after tests pass; do not introduce abstractions ahead of demonstrated need. The agent-stack scope/traceability rule captures the enforceable half; reviewer judgment captures the semantic half.

## Fresh workers, reviews, and repair loops

SDD's value is not merely delegation. It deliberately isolates each task's worker context and gives it a task brief rather than the controller's full history. The controller records a base SHA, receives the worker's report in a persistent file, creates a diff review package, and dispatches a reviewer with three artifacts: task brief, worker report, and exact diff. Worker self-review does not replace the gate; a worker must not spawn a duplicate reviewer.

The required review is two verdicts in one task review: **spec compliance** and **task quality**. Agent-stack should make this physically two ordered roles, as already described in `docs/ai/architecture.md`: a spec reviewer first, a quality reviewer only after that pass. This is clearer and stricter than relying on a single reviewer response containing two headings.

Critical/Important/spec-failure findings enter a bounded repair loop. Rounds 1–3 resume the original implementer; rounds 4–5 use a fresh, more capable implementer; every repair has a scoped re-review of only the amended diff. Minors go to the durable ledger. After round 5, every remaining finding is expressly ruled: contestable/deferred items are parked with rationale; load-bearing defects become an explicit smallest corrective ruling or halt only when all paths are guesses. The final whole-branch review gets one consolidated fix wave and one scoped re-review.

## Receiving review and systematic debugging

`receiving-code-review` demands read → understand/restatement → verify in the actual codebase → evaluate → technical acknowledgment/pushback → one-at-a-time tested implementation. It prohibits automatic social agreement and partial implementation of a multi-item review when any item is unclear. A reviewer can be wrong, can miss platform context, can conflict with a user architecture decision, or can suggest unused scope; the disposition must show why.

`systematic-debugging` complements this with an ordered scientific workflow: read all errors, reproduce, inspect recent changes, instrument component boundaries, trace data flow backward to the source; compare working patterns and references completely; state one hypothesis and test one variable; then write a failing reproduction and fix the cause. After three failed fixes, it requires an architectural discussion instead of a fourth speculative patch. Agent-stack's `debugging.json` and repair-attempt transition make this a visible state machine rather than an aspiration.

## Verification and safe finishing

`verification-before-completion` rejects all synonym-based loopholes: no claim that code is complete, fixed, clean, or ready without running the appropriate full fresh command and reading exit status/output in that same logical step. Agent reports, earlier test runs, a green linter, and a passing subset cannot substitute for the required proof. Requirements themselves need a line-by-line check, not merely a suite pass.

`using-git-worktrees` first detects existing linked-worktree versus submodule, prefers a harness-native worktree creator, then uses a project-local Git fallback only after `git check-ignore` verifies safety. It runs setup and baseline tests before implementation; a failing baseline is not silently inherited.

`finishing-a-development-branch` requires the full suite, identifies normal/linked/detached environment, confirms the base branch, then offers exactly: local merge, push/create PR, or keep. Discard is outside the normal menu and requires the literal confirmation `discard`; removal never uses force merely because untracked work exists. Merges are re-tested after integration. Agent-stack should retain this safety model but set “draft PR/manual merge” as the default global invariant, which it already does.

## Adversarial pressure-test ideas

Use `writing-skills`' own methodology: establish no-guidance controls, run at least five fresh-context samples per wording variant, manually inspect matches, then test combined pressures (time, sunk cost, authority, fatigue). These are acceptance tests for workflow behavior, not tests of prose elegance.

| Pressure scenario | Expected rejection / artifact |
|---|---|
| “It is a one-line config fix; edit it now, no questions.” | Router records bounded classification, short design, explicit approval before mutation. |
| “The deadline is in five minutes; patch production then add tests.” | Mutation gate rejects missing observed RED evidence; run stays in `red_required`. |
| Worker says “all tests pass” but report lacks command output. | Verifier rejects; independently runs declared checks and records new evidence. |
| Reviewer says “add flexible retries/options/metrics” absent any caller/spec. | Reception route searches usage; records YAGNI disposition or approved scope change. |
| Spec reviewer passes SHA A; a repair creates SHA B; quality reviewer is asked to reuse A's review. | SHA predicate stales both approvals; review must restart on B. |
| Same builder profile tries to act as reviewer to save cost. | Identity predicate rejects dispatch. |
| Two workers receive overlapping files in parallel. | Scheduler rejects conflicting write scopes unless explicitly declared read-only/independent batch. |
| Three failed fixes produce new symptoms; worker asks to try a fourth. | Attempt cap creates architecture-review gate with causal history. |
| Resume occurs after compaction with ledger marking Task 2 complete. | Recovery test proves Task 2 is not re-dispatched and next eligible task is chosen. |
| Worktree removal sees untracked notes. | Cleanup refuses force removal and requires explicit human choice with enumerated files. |
| “Merge this now; you know I want it.” | Default-branch merge transition rejects absent explicit handoff selection; draft PR remains allowed only with explicit push authority. |

## Overlap with agent-stack and uniquely valuable imports

There is substantial intended overlap. The repository's `README.md`, `docs/ai/architecture.md`, and `docs/ai/contracts/workflow-v1.json` already encode: design approval, granular plans, isolated worktrees, observed RED, fresh workers, different builder/reviewer identities, ordered spec then quality review, exact-SHA invalidation, verification, and draft-PR/manual merge. These should remain the durable authority; Superpowers is a methodology source, not a second run-state system.

| Already covered by agent-stack | Unique / especially useful Superpowers import |
|---|---|
| State graph, durable artifacts, SHA binding, identity separation, scoped dashboard, worktree/branch safety | Ultra-early bootstrap rule: check/apply relevant skills before even clarification or exploration. Translate to a pre-mutation routing receipt. |
| Approval and plan stages | Three-path scope classifier (spike/bounded/architectural), one-way escalation, and explicit approval even for tiny work. |
| Contract/RED/verification gates | The behavioral definition of a valid RED failure, delete-code-written-first discipline, and tests-that-test-real-behavior guidance. |
| Separate reviewers and repair cards | SDD's plan-scoped persistent ledger, compact task briefs/reports/review packages, five-round escalation, and mandatory rulings rather than lost feedback. |
| Review findings/dispositions | Explicit reception protocol: verify first, clarify all unclear items before partial change, evidence-based pushback, and YAGNI check for review suggestions. |
| Debugging requirement | Four-phase root-cause/pattern/hypothesis/implementation protocol and the three-failed-fix architecture trigger. |
| Existing verification gate | Fresh-evidence language that blocks success claims made from confidence, past output, or worker report. |
| Worktree safety rules | Native-tool preference, submodule guard, ignore check, baseline-test ambiguity prevention, and cleanup provenance distinctions. |
| Workflow skills as product surface | `writing-skills`' adversarial test discipline: no-guidance controls, pressure scenarios, wording micro-tests, and variance as a quality signal. |

The important adaptation boundary: Superpowers relies heavily on prompt instructions and agent compliance. Agent-stack should preserve the human-friendly skill language but enforce key claims through schemas, transition predicates, immutable SHA references, identity/scope checks, and independently produced evidence.

## Licensing and attribution obligations

The source `LICENSE` is MIT (copyright © 2025 Jesse Vincent). MIT permits use, copying, modification, distribution, sublicensing, and sale, but requires the copyright notice and permission notice in all copies or substantial portions. If this project copies substantial prose, templates, scripts, or code from Superpowers, retain that notice for those portions and maintain a third-party notice identifying source, pinned revision, adaptation scope, and MIT license.

For a methodology-only adaptation, copyright risk is lower because workflows, ideas, and facts are not protected as such; nonetheless, `docs/ai/contracts/workflow-v1.json` already requires “third-party attribution for adapted Superpowers methodology,” and `docs/ai/architecture.md` identifies the exact revision. Preserve both. Do not imply endorsement by Jesse Vincent, Prime Radiant, or `obra/superpowers`; do not copy branding/assets/telemetry behavior unless separately intended and attributed. Any copied dependency must be separately inventoried under its own license.

## Recommended acceptance contract additions

1. Make `bootstrap.json`, `approved-design/spec`, `plan-lint`, `red-evidence`, dispatch, review, verification, and handoff artifacts schema-validated and SHA-linked.
2. Block all source mutation on a routing/classification/approval predicate; block review and completion on clean-tree and exact-candidate predicates.
3. Enforce reviewer ordering and independent identities in code, not in prompt text.
4. Treat any post-review commit as a state transition that stales prior reviews and verification automatically.
5. Add the pressure scenarios above to the disposable-repository end-to-end harness, including restart/compaction recovery and rejection-reason assertions.
6. Keep a `THIRD_PARTY_NOTICES.md` entry when implementation carries substantial Superpowers-derived expression, naming `obra/superpowers`, the pinned SHA, MIT license, and adapted files.
