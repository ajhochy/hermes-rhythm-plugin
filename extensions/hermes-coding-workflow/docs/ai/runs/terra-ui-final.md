# Terra UI final integration

- Scope: `dashboard/**`, `desktop/**` (with duplicate `desktop/install.mjs` removed), package scripts, and focused API/Desktop tests only.
- Projection: reads the producer-owned `run.json`, `approved-design.json`, `plan.json`, `evidence.jsonl`, `reviews.json`, `verification.json`, `handoff.json`, and safe artifact labels. It reads the run revision before and after side artifacts, returns `409` for a changed or malformed projection, and verifies the bounded JSONL evidence hash chain.
- Safety: board metadata remains the repository authority; no paths, command output, raw arguments, or unredacted summaries are returned. Draft PR navigation permits only canonical GitHub pull-request URLs.
- Validation: `pytest -q -s -p no:cacheprovider tests/api` (6 passed); `npm test` (3 passed); `npm run build` (production ESM parse plus 3 passed); `python -m py_compile dashboard/plugin_api.py`; `git diff --check`; added-line credential scan. No packages installed, network calls, live profile actions, commits, or skipped tests.
