# Terra control-plane run

## RED 1

Command: `python -m pytest tests/core/test_control_plane.py -q`

Observed failure: `/Users/ajhochhalter/.hermes/hermes-agent/venv/bin/python: No module named pytest` (exit 1).
The test specifies the strict full-SHA boundary before production code exists; pytest is declared as a development dependency but is not installed, per the no-install constraint.

## RED 2

Command: `python -m pytest tests/core/test_workflow_service.py -q`

Expected failure before the transition implementation: no service package / `pytest` unavailable locally. The behavioral test covers accepted → RED → GREEN → independent spec/quality reviews → live verification → completion and exact rejection codes.

## RED 3

Command: disposable Git lifecycle smoke via `WorkflowService`.

Observed failure: `path_scope_violation` while recording GREEN because the run's own untracked `.hermes/workflows/` evidence was incorrectly counted as source scope. The fix excludes only durable workflow metadata from source scope and dirty-tree checks.

## RED 4

Command: disposable Git lifecycle smoke via `WorkflowService` after both independent approvals.

Observed failure: `TypeError: 'RunStore' object is not subscriptable` in the verification composition path. The run record is now read explicitly before comparing its candidate SHA.

## RED 5

Command: disposable Git lifecycle smoke completion after verification.

Observed failure: the same store/record composition defect in `complete`; completion now reads the current run record before enforcing terminal gates.

## RED 6 — parent gate (observed)

Command: `PYTHONPATH=src pytest -q`

Observed failure: 2 failures — `tests/core/test_workflow_service.py::test_full_run_requires_red_reviews_and_live` and `tests/e2e/test_disposable_repo.py::test_disposable_repository_workflow` both raised `WorkflowError("dirty_worktree")` at `request_review`. Their fixture commits included `.hermes/workflows/<run>/run.json` and `evidence.jsonl`, and subsequent workflow writes modified those bookkeeping artifacts. The repair adds strict regression coverage that excludes only canonically contained repository-root `.hermes/workflows/**` paths from dirty and source-scope decisions; nested lookalikes, real source changes, and symlink escapes remain gated.

## GREEN verification

## P1-R2 repair — RED / GREEN

- Parent/reviewer RED: independent review of `bad124192e4e2ca82f4f088daaa65cf2f5d29fa4` rejected the control plane for bypassable design/plan, evidence, identity, worktree, Kanban, and locking gates; see `/tmp/hcw-control-plane-review.md`.
- Exact GREEN command: `PYTHONPATH=src pytest -q` — `14 passed` (zero skipped) after the repair contracts exercised draft → approved design → approved plan → isolated worktree RED/GREEN → spec/quality → full/security/live → verify → completion, plus rejected evidence, scope, identity, repair and revision conflict paths.

- Disposable Git workflow smoke: passed, ending in `completed` after RED, GREEN, independent spec and quality approvals, verification, and live gate.
- `PYTHONPATH=src python -m compileall -q src`: passed.
- `python -m pip wheel --no-deps --no-build-isolation --wheel-dir /private/tmp/hcw-build .`: passed; produced `hermes_coding_workflow-0.1.0-py3-none-any.whl`.
- `PYTHONPATH=src python -c 'import hermes_coding_workflow; print(hermes_coding_workflow.SCHEMA_VERSION)'`: passed (`hcw/v1`).
- `PYTHONPATH=src python -m hermes_coding_workflow.cli --help`: passed.
- `git diff --check`: passed.
- `python -m pytest -q`: blocked: the supplied interpreter has no `pytest`; dependencies were not installed by instruction.
- `PYTHONPATH=src pytest -q tests/core/test_workflow_service.py tests/e2e/test_disposable_repo.py`: passed (`17 passed, 3 skipped`).
- `PYTHONPATH=src pytest -q`: passed (`18 passed, 3 skipped`).
- `PYTHONPATH=src python -m compileall -q src`: passed.
- `PYTHONPATH=src python -c 'import hermes_coding_workflow; print(hermes_coding_workflow.SCHEMA_VERSION)'`: passed (`hcw/v1`).
- `PYTHONPATH=src python -m hermes_coding_workflow.cli --help`: passed.
- `python -m pip wheel --no-deps --no-build-isolation --wheel-dir /private/tmp/hcw-build-p1-r1 .`: passed; produced `hermes_coding_workflow-0.1.0-py3-none-any.whl`.
- `git diff --check`: passed.
- Secret scan (`rg` for common OpenAI/GitHub/AWS credentials and private keys, excluding `.git`): passed with no matches.
