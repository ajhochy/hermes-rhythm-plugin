Base: `main`

Refs #3
Refs #4
Refs #5
Refs #6
Refs #7
Refs #8
Refs #9
Refs #10
Refs #11
Refs #12
Refs #13
Refs #14

## Result

The unified Rhythm feature pack includes one Desktop ESM bundle, the dashboard registration/theme seam, bounded hosted tools, packaging validation, and a reversible installer. This finish pass repairs the observed installed-host JSX incompatibility by generating elements through the host React singleton. It retains SDK state hooks; an unproven alternative was removed.

**Draft; installed/hosted cutover remains blocked.** The installed host registered `/rhythm` and loaded the exact final JSX-only package but mounted no Rhythm workspace. The visible generic composer does not prove M3, hosted reads, draft handoff, or ACP behavior. Final installed SHA matched the validated artifact; its route created a React element successfully with the final SDK hooks, but zero workspace roots appeared.

## Current evidence

- Canonical `HERMES_TEST_FILE_RETRIES=0 scripts/run_tests.sh tests/plugins/rhythm -j 4 --tb=short`: **283 passed, 0 failed**, including the unchanged M10 budget. Packaging subset: **62 passed**.
- Earlier full-run M10 timing failure followed by isolated 5/5 is retained as a flake; no threshold changed.
- Install, doctor, enable/list and process-local forced rediscovery passed; doctor found exactly 3 tools and 0 hooks. `hermes doctor` exited 0 before and after removal.
- Installed CLI has no `plugins reload` command or documented `cmd_reload` helper. Forced rediscovery is narrower evidence; native window reload was also attempted without quitting Hermes.
- Native sidebar appeared exactly once after rescans. Final-package module/route probes proved successful element creation and final SDK-hook code, but zero workspace DOM roots; hosted interaction could not begin.
- Disable/remove completed for Python and Desktop install roots; both dated backups and authentication data were preserved. Desktop toggle/destination disappeared. The running backend still displayed a cached native-tools row, so in-memory disposal remains unverified.
- Final Desktop bundle SHA-256: `f99402ca3ee33664e1582d98659420ace509d874dc47f67b6c41c0f523cfd984`.

## Milestone closure gaps

| Issue | Remaining evidence |
|---|---|
| #3 M0 | Real host reload/disposal and interactive ACP safety. |
| #4 M1 | Missing issue-to-commit/plan provenance association and shared UI compatibility closure record. |
| #5 M2 | Mounted installed page and complete duplicate/disposal behavior. |
| #6 M3 | Visible M3 flow and hosted provider/authentication registration. |
| #7 M4a | Installed Dashboard/Tasks reads, unsent draft, and nonempty zero-write hosted trace. |
| #8 M4b | Own disposable task: ACP deny, allow once, exact write and canonical read-back. |
| #9 M5 | Installed Planner/Rhythms/Projects parity. |
| #10 M6 | Installed Messages/Facilities parity. |
| #11 M7 | Installed renderer/artifact isolation. |
| #12 M8 | Real three-tool ACP client approval and hosted read-back. |
| #13 M9 | Final artifact mounted workspace, full in-memory disposal/rollback; signing is a separate release gate. |
| #14 M10 | Credentialed rendered cutover. |

No milestone is auto-closed. The mounted-route blocker must be resolved before the credentialed gates can run. No hosted rows were created and no draft was sent. Hermes Desktop remained running throughout cleanup.

Detailed commands, decisions, failures, and screenshots: [finish gate](https://github.com/ajhochy/hermes-rhythm-plugin/blob/mega/2026-09-18-rhythm-plugin-finish/docs/ai/runs/2026-09-18-rhythm-plugin-finish-gate.md). Local fixture results do not establish deployed behavior. No merge, production takeover, OpenCode retirement, or signed release is claimed.
