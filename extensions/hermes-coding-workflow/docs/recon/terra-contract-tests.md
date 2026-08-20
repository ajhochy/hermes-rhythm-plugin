# Terra contract-test design

## Purpose

This report defines a test-first contract for Terra: an accepted campaign is split into independently owned vertical packages, each package runs in an isolated worktree, and a run completes only when current, attributable evidence proves live requested behavior. It is a design artifact only; it specifies no production implementation.

The model follows the agent-stack chain: plan -> issue -> acceptance contract -> build -> verification -> state update -> postmortem. Its central invariant is: **evidence before assertions; stale evidence is not evidence**. Hermes Kanban's lifecycle, worktree, review, dispatch-lock, redaction, and plugin-ownership test surface is the behavioral precedent. Superpowers supplies the test discipline: name the break, use independent literal expectations, and exercise real boundaries rather than grepping source.

## Package tree

    packages/
      terra-contracts/              # versioned schemas and validators only
        src/schema/{campaign,run,stage,review,evidence}.schema.json
        src/validate.ts
        test/schema-contract.test.ts
      terra-policy/                 # pure transitions, rejection, SHA and scope rules
        src/{transitions,rejections,scope,sha}.ts
        test/{transitions,rejections,scope}.test.ts
      terra-evidence/               # append-only, content-addressed evidence
        src/{store,hash,attestation}.ts
        test/{integrity,red-green,attestation}.test.ts
      terra-workspace/              # disposable Git/worktree containment
        src/{git,worktree,dirty-tree}.ts
        test/{worktree-isolation,scope,dirty-tree}.test.ts
      terra-runner/                 # claim, retry, stage scheduling; never review
        src/{campaign-runner,stage-runner}.ts
        test/{run-lifecycle,collision}.test.ts
      terra-review/                 # independent review and invalidation
        src/{review-gate,invalidate}.ts
        test/{review,post-review-change}.test.ts
      terra-live/                   # live behavior probes and execution security
        src/{probe,redaction}.ts
        test/{probe,security}.test.ts
      terra-cli/                    # thin public adapter, no duplicated policy
        src/commands/{accept,run,review,complete}.ts
        test/cli-contract.test.ts
      terra-e2e/                    # public, disposable-repository test
        test/disposable-repo.e2e.test.ts

Dependencies are directed downward. Contracts has no dependencies; policy, evidence,
and workspace depend only on contracts; runner/review/live compose lower packages;
CLI composes them; E2E invokes only the public CLI. The builder cannot write a
review and the reviewer cannot write the builder worktree.

## Versioned schemas

Every persisted object has schema_version "terra/v1", kind, opaque UUID id,
RFC-3339 UTC created_at, and strict validation. Unknown major versions, unknown
required protocol fields, and abbreviated Git SHAs are rejected. Full object hashes
are required; branch names are never evidence identities.

### Campaign (terra/v1/campaign)

    {
      "schema_version": "terra/v1", "kind": "campaign", "id": "uuid",
      "created_at": "2026-08-19T00:00:00Z",
      "request": "observable user outcome",
      "acceptance_prompt": "immutable structured prompt/answer",
      "base_ref": "refs/heads/main", "base_sha": "full object hash",
      "packages": [{"id":"P-1","title":"...","path_scope":["src/x/**"],"depends_on":[]}],
      "required_checks": ["unit","integration","live"],
      "status": "draft|accepted|running|blocked|completed|cancelled"
    }

base_sha is resolved once at acceptance. A package scope is nonempty, normalized,
repository-relative, and disjoint from all other package scopes after expansion.

### Run (terra/v1/run)

    {
      "schema_version":"terra/v1", "kind":"run", "id":"uuid",
      "campaign_id":"uuid", "package_id":"P-1", "attempt":1,
      "actor":{"role":"builder","id":"worker-a"},
      "worktree":{"path":"approved temporary absolute path","base_sha":"...","head_sha":"..."},
      "status":"queued|claimed|building|ready_for_review|rejected|repairing|verified|completed|cancelled",
      "created_at":"...", "updated_at":"..."
    }

One run owns exactly one package, one builder principal, one temporary worktree, and
one immutable base SHA. A retry creates a new attempt; it never erases rejection
history.

### Stage (terra/v1/stage)

    {
      "schema_version":"terra/v1", "kind":"stage", "id":"uuid", "run_id":"uuid",
      "name":"design|red|build|review|verify|live|complete",
      "status":"pending|active|passed|failed|blocked|skipped",
      "input_sha":"...", "output_sha":"...", "started_at":"...", "finished_at":"...",
      "evidence_ids":["EV-..."]
    }

A passed stage has evidence and a full output SHA. input_sha is the commit inspected
at that time, never inferred after the fact.

### Review (terra/v1/review)

    {
      "schema_version":"terra/v1", "kind":"review", "id":"uuid", "run_id":"uuid",
      "reviewer":{"role":"reviewer","id":"worker-b"}, "reviewed_sha":"...",
      "decision":"approved|changes_requested|rejected",
      "findings":[{"severity":"blocker|major|minor","text":"..."}],
      "evidence_ids":["EV-..."], "created_at":"...",
      "invalidated_at":null, "invalidation_reason":null
    }

Reviewer identity must differ from builder identity. Approval containing a blocker is
invalid. Any head change after reviewed_sha invalidates approval.

### Evidence (terra/v1/evidence)

    {
      "schema_version":"terra/v1", "kind":"evidence", "id":"EV-uuid",
      "run_id":"uuid", "stage_id":"uuid",
      "type":"design|red|test|review|live|git|security", "captured_at":"...",
      "actor":{"role":"builder|reviewer|gate","id":"..."}, "commit_sha":"...",
      "command":["executable","argument"], "exit_code":0,
      "summary":"bounded redacted result", "artifact_sha256":"64 lowercase hex",
      "previous_evidence_hash":"sha256 or null"
    }

The ledger is append-only and hash chained. Commands use argument vectors. Redaction
occurs before persistence. Failed evidence counts as RED only when it predates the
change it describes; it cannot satisfy GREEN or completion.

## State transitions

| From | Event and preconditions | To | Required evidence |
|---|---|---|---|
| draft | acceptance prompt concrete; scopes valid; base SHA resolved | accepted | design |
| accepted | clean isolated worktree and atomic claim | queued/claimed | Git/worktree |
| claimed | builder starts | building | stage start |
| building | contract test fails at pre-change SHA | building | RED |
| building | scoped change passes checks at head | ready_for_review | GREEN, scope, clean tree |
| ready_for_review | distinct reviewer approves exact head | verified | review |
| verified | full, security, live gates pass at same head | completed | full, security, live |
| any nonterminal | policy/check failure | rejected/repairing/blocked | rejection |
| rejected or repairing | new isolated retry | claimed | new run record |

Completed is terminal. A campaign completes only when every package completed in
dependency order; evidence from package A cannot discharge package B.

## Rejection rules

| Code | Reject condition | Required response |
|---|---|---|
| stale_sha | stage, review, or evidence SHA differs from current run head/input | invalidate downstream stages and rerun at current head |
| missing_red_evidence | no failing contract test recorded at pre-change SHA | reject attempt; new RED-first attempt |
| post_review_change | HEAD differs from reviewed_sha after approval, including amend/rebase/generated edit | invalidate approval and independently review again |
| missing_live_behavior | no required probe, failed/different-SHA probe, or only source inspection | reject completion and run declared probe |
| reviewer_builder_collision | actor identity, authenticated principal, credential, or worktree overlaps | reject review and assign an independent reviewer |
| path_scope_violation | a changed path lies outside allowed globs or package scopes overlap | reject before review; split/correct scope |
| dirty_worktree | staged, unstaged, or untracked file at claim/review/complete (other than explicitly excluded evidence) | block; clean or create fresh worktree |
| premature_completion | completion claim lacks same-head full/review/security/live evidence | record W5 and do not set completed |

Also reject malformed schema, non-fast-forward base substitution, incomplete package
dependency, duplicate active claim, evidence-chain mismatch, reviewer write attempt,
shell-string command, unredacted secret, or any probe outside a disposable fixture.

## Explicit contract tests

| Test file | Behavior proved |
|---|---|
| terra-contracts/test/schema-contract.test.ts | accepts valid v1 fixtures; rejects version, kind, identity, time, SHA, enum, and protocol-field violations |
| terra-policy/test/transitions.test.ts | permits only listed transitions; passed stages require evidence; terminal states cannot regress; dependencies cannot be bypassed |
| terra-policy/test/rejections.test.ts | each rejection row returns its machine code and leaves no completed run |
| terra-policy/test/scope.test.ts | rejects absolute paths, traversal, symlink escape, overlap, and changed files outside scope |
| terra-evidence/test/integrity.test.ts | verifies append-only hash chain; detects content/order/timestamp tampering; failed evidence cannot be GREEN |
| terra-evidence/test/red-green.test.ts | requires pre-change RED and later-head GREEN; rejects pass-only and RED-after-change runs |
| terra-workspace/test/worktree-isolation.test.ts | worktree starts from resolved SHA, never caller checkout; reviewer/builder worktrees differ; cleanup is fixture-root only |
| terra-workspace/test/dirty-tree.test.ts | catches staged, unstaged, untracked, ignored-policy, submodule, and generated-file cases |
| terra-runner/test/run-lifecycle.test.ts | claim is atomic; retry preserves history; a run cannot own two packages |
| terra-runner/test/collision.test.ts | builder cannot create review; reviewer cannot use builder worktree/credentials |
| terra-review/test/review.test.ts | approval requires distinct reviewer, current SHA, no blocker, review evidence, and read-only review |
| terra-review/test/post-review-change.test.ts | a one-byte/amended commit invalidates approval; old review cannot satisfy gates |
| terra-live/test/probe.test.ts | declared probe runs against actual artifact and captures observable output; text/source scan fails |
| terra-live/test/security.test.ts | rejects injection; redacts secrets; bounds output; restricts paths/network; records security failure |
| terra-cli/test/cli-contract.test.ts | public commands emit versioned records/nonzero structured errors and cannot supply status/SHA to bypass policy |
| terra-e2e/test/disposable-repo.e2e.test.ts | black-box campaign proves accepted -> RED -> GREEN -> independent review -> full/live -> complete and every rejection |

Use generated legal/illegal event paths for the state machine, generated scopes and
changed paths for containment, evidence-field mutation for hash integrity, and
concurrent claims/reviews for alias/lock safety. Every test states the concrete
wrong branch, missing side effect, or wrong argument it catches, and uses
hand-authored expected outcomes rather than production helpers.

## Non-overlapping vertical ownership

| Package | Owns | Never owns |
|---|---|---|
| contracts | schemas/parsers/compatibility fixtures | decisions, I/O, Git |
| policy | transitions, rejection, SHA/scope decisions | persistence, process execution |
| evidence | ledger, hashes, redaction | authorization decision, Git inspection |
| workspace | Git/worktrees/cleanup containment | review verdict, record semantics |
| runner | run/claim/retry/stage scheduling | review approval, probe verdict |
| review | independent review/invalidation | builder execution/worktree writes |
| live | probes/execution security | policy exceptions/completion writes |
| cli | parse/render/exit codes | duplicated business rules |
| e2e | fixtures/public black-box verification | production behavior |

## Integration order

1. Freeze v1 fixtures and validators in contracts.
2. Implement policy transitions, rejection, SHA and scope rules with property tests.
3. Add evidence integrity, redaction, and RED/GREEN contracts.
4. Add disposable Git fixture/worktree containment.
5. Compose runner claiming/retry/collision behavior.
6. Compose independent review and post-review invalidation.
7. Compose live probe/security boundary.
8. Add thin CLI and run E2E through public commands.

Each level must pass before the next is composed; no higher layer substitutes a mock
for a missing lower-level behavior.

## Gates

### Fast gate

- Format, typecheck, schemas, affected unit/property/contract tests.
- Mutation check: name the realistic wrong branch, argument, or side effect each
  test catches; delete source-text and tautological tests.
- Static secret scan and dependency/license checks.

### Full gate

- Clean isolated worktree; base/head SHA recorded.
- All unit, integration, property, and cross-package tests.
- Scope diff passes; RED at base/pre-change and GREEN at head both recorded.
- Exact-head independent review with no blockers and no actor/worktree/credential collision.
- Security suite and evidence-chain verification pass.

### Live gate

- Run the campaign-declared probe on the actual built artifact in a disposable fixture.
- Bind result, artifact hash, head SHA, fixture path, timestamp, and redacted output
  to evidence.
- Recheck status, scope diff, head SHA, and review SHA after the probe. Any change
  invalidates review and returns to repair/review.

## Security checks

- Canonicalize paths and resolve symlinks; reject traversal, absolute escape,
  untrusted nested repositories, and cleanup targets outside the temporary fixture root.
- Spawn allowlisted executables with argument vectors, minimal environment, timeout,
  resource caps, and default-deny network. Never interpolate a command shell string.
- Redact credentials/tokens/cookies/private keys/home paths and cap persisted output.
- Authenticate immutable run claims server-side; role strings supplied by clients are
  not authority.
- Hash-chain evidence and block all later gates on an integrity failure.
- Treat plugins/probes as untrusted: explicit capability allowlist, no ambient write
  access, and isolated credentials, consistent with Hermes plugin ownership controls.

## Acceptance prompt: prove design before code

The accept command persists this structured question and cannot accept a campaign
until every field is concrete:

> Before code is written, state the observable user outcome; enumerate vertical
> packages with disjoint repository-relative scopes and dependencies; name the exact
> first failing contract test and the defect it catches; give the real live command
> and disposable fixture that proves behavior (not a source grep); state the security
> boundary and an independent reviewer; confirm the resolved base SHA and isolated
> worktree. Respond ACCEPT only when complete; otherwise identify the missing decision.

Tests reject responses such as "tests will pass", "review later", "all files", a
branch name, or a source grep. The persisted acceptance record includes prompt,
answers, responder, time, and base SHA so later stages cannot silently redesign it.

## Final disposable-repository end-to-end run

The final E2E test creates a brand-new temporary Git repository containing a minimal
behaviorally testable program. It uses no developer checkout, real remote, shared
worktree, or real credentials.

1. Accept a two-package campaign with disjoint scopes, dependency A -> B, and a
   concrete live command. Verify base SHA binding.
2. Claim A in its own worktree and record a deliberately failing contract test at
   base SHA (RED).
3. Apply the smallest fixture change, commit it, record GREEN, and prove clean scope.
4. Have a different reviewer approve that exact commit; then pass full/security/live
   gates against the actual fixture artifact.
5. Complete A, repeat B only after A, then complete the campaign and verify every
   hash, SHA edge, and actor-separation rule.
6. In separate subcases submit stale evidence, missing RED, post-review change,
   missing live probe, same reviewer/builder, scope escape, dirty tree, and premature
   complete. Assert the precise rejection code and no completed run.
7. Remove only fixture-created worktrees/repository and assert the original cwd and
   repository were untouched.

This live black-box run is the final proof: it demonstrates requested behavior and
proves that no shortcut can forge completion.
