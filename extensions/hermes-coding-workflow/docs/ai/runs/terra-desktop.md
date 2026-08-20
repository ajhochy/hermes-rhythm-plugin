# Terra Desktop P3/P4 — RED → GREEN evidence

Base: `2cc3c7bb07fa43c51734bc3443490663e0dca314` on `terra/desktop`.

## RED

`PYTHONDONTWRITEBYTECODE=1 pytest -q -s -p no:cacheprovider tests/api`:
`4 failed` before the repair. The failing assertions demonstrated that the
old adapter listed board directories rather than real `kanban_db` metadata,
did not resolve `project_id`, accepted a metadata traversal path, and did not
report a changing durable snapshot as `409`.

`node --test tests/desktop/plugin.test.mjs`: `3 failed` before the repair.
The ESM loader could not import the old contribution in the deterministic
runtime shim, and the expected exported detail renderer/keyed polling model
did not exist. These were executable runtime/renderer failures, not source
regex checks.

## GREEN

`PYTHONDONTWRITEBYTECODE=1 pytest -q -s -p no:cacheprovider tests/api`
passed: `4 passed` (real installed Hermes metadata projection for default and
named boards; project/root validation; traversal/symlink rejection;
bounded/redacted DTOs; GET-only 404/409/422 behavior).

`npm test` passed: `4` Desktop tests register the exact contributions through
an executable ESM loader, render complete blocked/stale detail data and page
states, prove GET-only REST use, and install into an isolated Hermes home with
both actual plugin doors plus the enabled allow-list. `npm run build` repeats
the production ESM parse/load smoke with only Hermes SDK/React externals.

The UI uses 5-second polling for board lists, runs, and selected detail. It
clears detail selection whenever boards change, presents native SDK controls
and explicit loading/empty/error/stale states, and contains no mutation
controls. Local artifact labels are deliberately non-actionable because the
read-only API does not expose filesystem paths; only backend-validated HTTPS
draft-PR URLs are offered to the Desktop SDK.
