# Terra lifecycle final integration

Date: 2026-08-19

## Scope

- Replaced lifecycle scripts with a root-owned, explicit-`HERMES_HOME` installation model.
- Installed native `hcw` and `superpowers` payloads, root dashboard API, root Desktop ESM, root Python control-plane runtime, and local `hcw` launcher in the base home plus all seven role homes.
- Added isolated-Hermes-home lifecycle integration coverage and replaced the in-process disposable workflow E2E with a public installed-launcher contract.

## Evidence

- An isolated temporary `HERMES_HOME` with source `dev` profile installed both plugins into the base home and `dev-planner`, `dev-contract`, `dev-builder`, `dev-spec-reviewer`, `dev-quality-reviewer`, `dev-verifier`, and `dev-recorder`.
- Hermes `plugins doctor --ci` registered `hcw` with two hooks and `superpowers` with no hooks in every installed home.
- `scripts/doctor.py --hermes-home <isolated-home>` completed after validating scanner registration, launcher, role descriptions, dashboard/Desktop payloads, namespaces, branding, and profile copies.

## Expected integration failure

`tests/e2e/test_disposable_repo.py` is strict-xfail when enabled with `HCW_POST_MERGE_E2E=1`. The installed `hcw start` command calls `ActorContext.from_env()`, which requires `HERMES_KANBAN_TASK`, and then creates the real Kanban graph before rejecting the caller unless that already-supplied task equals the newly created RED task. A public worker therefore cannot obtain the actual RED ID from the manifest before satisfying `start`. This is a control-plane integration defect outside this worker's owned paths. The E2E retains the real CLI/real Kanban boundary and does not add a fake runner or service call to hide it.

## Safety

- No live user home was installed into or modified.
- No network, push, merge, or commit was performed.
- The disposable E2E initializes its own repository and asserts that `main` remains untouched and the candidate branch is not merged.
# Superseded by [terra-final-reconcile.md](terra-final-reconcile.md).
