# Terra final reconcile — 2026-08-19

Supersedes the earlier integrated lifecycle assertions for the repaired public contract.

- Lifecycle plan shape is exactly `{tasks,commands,approved}`. E2E declares RED/GREEN/FULL `python -m unittest discover -s tests`, security `python -m compileall -q app.py`, and live `python -c "import app; assert app.value()==2"`, all mapped to `R1`.
- The installed proof uses a safe native `openai` / `gpt-4o-mini` base and source profile before installation, role-local launchers, a profile-local `hcw commit`, real Hermes task IDs, real Kanban comments, and ends at `completed`.
- Dispatch records have strict `stage, task_id, profile, provider, model, session_id, attempt, brief_hash` keys; `internal.json` holds the non-exported Kanban home only.
- Base installation is dashboard-only (`hcw-dashboard` plus Desktop); source and role profiles receive `hcw` and `superpowers` enforcement packages. Unsafe source preflight makes no mutation.
- Focused validation run during reconciliation: `python -m py_compile src/hermes_coding_workflow/*.py scripts/*.py dashboard/plugin_api.py plugins/hermes-coding-workflow/__init__.py` and `PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 pytest -q tests/core -p no:cacheprovider` (11 passed). Installed lifecycle and lifecycle-install runs were re-executed after the repair.

## Parent acceptance

- `PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 pytest -ra -p no:cacheprovider` — **31 passed in 144.05s**, zero skips/xfails.
- `npm test` — **3 passed**; `npm run build` — passed.
- Offline wheel build and Python compilation — passed.
- `git diff --check` — passed.
- Mandatory installed lifecycle used real Hermes board/task IDs and native plugin doctors and ended with run status `completed`.

## Final-review repair

- `workflow-v1.json` is explicitly superseded by authoritative `workflow-v2.json`, which names the shipped CLI and safe-provider topology.
- Builder order is `hcw commit` then planned GREEN check.
- Repair now reuses the original run's Kanban home, creates attempt-bound cards, and reattaches hashed approved-plan command comments; a focused repair regression passes.
- Completion rereads and verifies the evidence hash chain and every artifact digest; post-live tampering is rejected by a focused full-lifecycle regression.
- Parent rerun: `33 passed in 183.00s`, zero skips/xfails; Node `3/3`, ESM build, wheel, and diff gates passed.
- Bounded security re-review required exact ordered verification evidence IDs. Completion now compares the recorded sequence exactly and rejects duplicates; focused regression passed, followed by `33 passed in 217.98s` with zero skips/xfails.
