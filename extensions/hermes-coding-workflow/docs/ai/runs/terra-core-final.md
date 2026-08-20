# Terra core final integration receipt

- Scope: `src/hermes_coding_workflow`, v1 schemas, native HCW plugin, and core tests only.
- Contract: `create-run` creates the contained worktree and locator, then the Hermes v0.20 graph with exact `dev-*` profiles. Later authority is the persisted stage task/profile mapping.
- Evidence: `hcw check` executes argv in the registered worktree and persists bounded, redacted, chained artifacts; callers do not submit exit codes or artifacts.
- Safety: no Hermes installation, network access, live Hermes execution, commit, or push was performed.
- Validation: `PYTHONPATH=src pytest -q tests/core` passed (5 tests); `python -m compileall -q src plugins/hermes-coding-workflow` passed; `git diff --check` passed; `python -m pip wheel . --no-build-isolation --no-deps --wheel-dir /private/tmp/hcw-wheel-check` produced `hermes_coding_workflow-0.1.0-py3-none-any.whl`.
- Plugin-suite note: `PYTHONPATH=src pytest -q tests/core tests/plugin` was attempted. Core passed; four legacy plugin tests failed because their fixtures assert the superseded v0 record shape (and one environment lacks `hermes_cli`). No non-owned plugin tests were changed.
# Superseded by [terra-final-reconcile.md](terra-final-reconcile.md).
