# Rhythm operator live gate — 2026-09-18

Status: **partially executed; hosted M3 OAuth paused**. The separate fixed-host
candidate mounted Rhythm, but the old hosted desktop exchange changed existing
Google/Gmail integration state during a minimal-scope login. Those connections
were subsequently restored through the normal desktop consent path. The plugin
now requires a deployed login-only capability before it opens OAuth and pins
the separate login-only exchange. Do not retry **Connect Rhythm** until that
server change is deployed and verified. Socket-free pytest/build evidence is
separate from an installed Desktop, credentialed API, or approval-client result.
The only hosted Rhythm data origin is **https://api.vcrcapps.com**. There is no
configurable base URL, fallback host, redirect following, or generic proxy.

## 1. Build and inspect (CLI; no live account needed)

Run from the fork worktree. Node 22 and existing Bun are required; install no
npm/pip packages. The named `.hermes/plans/2026-08-20-hermes-rhythm-feature-pack.md`
was absent in this worktree; checked-in contracts and provenance are the basis
for these gates.

```bash
RHYTHM_PYTHON="$HOME/.hermes/hermes-agent/venv/bin/python"
node --version
bun --version
"$RHYTHM_PYTHON" -m pytest tests/plugins/rhythm -q
# Use a NEW empty path for each rebuild; the builder refuses to erase content.
"$RHYTHM_PYTHON" -m plugins.rhythm.packaging.build --output dist/rhythm-feature-pack
bash -n plugins/rhythm/packaging/install-local.sh
```

The worker already produced `dist/rhythm-feature-pack`; use that artifact or a
fresh output path instead of running the same build command over it. Exactly
one desktop ESM file (`desktop/dist/rhythm.mjs`) and one rebuilt dashboard file
(`dashboard/dist/index.js`) ship. The dashboard entry deliberately registers an
API-only hidden tab; the workspace UI belongs to Desktop. Host externals are
`@hermes/plugin-sdk`, `react`, `react-dom`, `react/jsx-runtime`,
`react-dom/client`; the final Desktop artifact imports SDK and React. The
builder maps generated JSX calls to the host React singleton because the
installed Desktop JSX-runtime shim may not expose callable `jsx`/`jsxs`.
The package excludes the vendored source maps, vendor sources, and `.env` files.
Both bundle text and the Bun dependency graph are checked; React cannot be
bundled, JSX must be production, and all other imports must be bundled.

## 2. Install → enable → reload (CLI plus Desktop)

For the installed release, finish active turns before a user-owned plugin
replacement. Do not quit or restart an existing Hermes Desktop to run this
gate. Installation replaces plugin code but does not edit config, auth, or
Desktop preferences. Use the same selected Hermes home/profile throughout.

```bash
plugins/rhythm/packaging/install-local.sh "$PWD/dist/rhythm-feature-pack"
hermes plugins doctor rhythm --ci
hermes doctor
hermes plugins enable rhythm --no-allow-tool-override
hermes plugins reload rhythm
hermes plugins list --enabled --plain
```

Backups are created once at `~/.hermes/plugins/rhythm.bak-20260918/backup.tar`
and `~/.hermes/desktop-plugins/rhythm.bak-20260918/backup.tar` when those installs
exist. Each archive contains the original `rhythm/` directory. Existing backups
are preserved. Archives are intentional: leaving a copied `plugin.yaml` or
`plugin.js` under watched roots can load an old plugin twice. Unexpected existing
backup layouts fail before replacing anything. Replacement stages both halves
and restores the previous halves on a replacement failure.

The unified Python package goes to `~/.hermes/plugins/rhythm`; its same desktop
bundle is copied to `~/.hermes/desktop-plugins/rhythm/plugin.js` for the installed
loader. No `ACTIVATION.json` is consumed by the checked-in runtime loader. Rhythm
has `defaultEnabled: false`: AJ must also enable **Settings → Plugins → Rhythm**
in Desktop. Python CLI enablement and Desktop's preference are separate gates.

`hermes plugins reload rhythm` is not available in the installed v0.20.5 CLI
(exit 2), and that release does not export `cmd_reload` from
`hermes_cli.plugins_cmd`. Record the actual command outcome. To check only
process-local rediscovery without claiming a Desktop reload, use the installed
manager's supported `force=True` path:

```bash
"$RHYTHM_PYTHON" -I - <<'PY'
from hermes_cli.plugins import get_plugin_manager
manager = get_plugin_manager()
manager.discover_and_load()
manager.discover_and_load(force=True)
manager.unload()
PY
```

For the **fixed-host candidate**, build this fork's Desktop and launch its
already-built renderer in a separate developer window with a fresh
scratch home and Electron userData. The four environment variables below are
supported by `apps/desktop/electron/main.ts`; none points to the installed
profile. The Python installer accepts an explicit `--home`, unlike the helper
shell script, which always targets `$HOME/.hermes`. Build after editing the
Rhythm renderer: the fork bundles `plugins/rhythm/desktop/src/plugin.tsx`, so
its same-id disk copy is shadowed and reinstalling that copy alone cannot
update a running bundled renderer.

```bash
RHYTHM_CANDIDATE_ROOT="$(mktemp -d /tmp/hermes-rhythm-candidate.XXXXXX)"
RHYTHM_CANDIDATE_HOME="$RHYTHM_CANDIDATE_ROOT/home"
RHYTHM_CANDIDATE_USER_DATA="$RHYTHM_CANDIDATE_ROOT/user-data"
npm run build --workspace apps/desktop
"$HOME/.hermes/hermes-agent/venv/bin/python" -m plugins.rhythm.packaging.install_local \
  --package "$PWD/dist/rhythm-feature-pack-mega-ipc-final" --home "$RHYTHM_CANDIDATE_HOME"
HERMES_HOME="$RHYTHM_CANDIDATE_HOME" hermes plugins doctor rhythm --ci
HERMES_HOME="$RHYTHM_CANDIDATE_HOME" hermes plugins enable rhythm --no-allow-tool-override
cd apps/desktop
HERMES_HOME="$RHYTHM_CANDIDATE_HOME" \
HERMES_DESKTOP_USER_DATA_DIR="$RHYTHM_CANDIDATE_USER_DATA" \
HERMES_DESKTOP_APP_NAME="Hermes Rhythm Candidate" \
HERMES_DESKTOP_HERMES_ROOT="$(cd ../.. && pwd)" npx electron .
```

These commands start a separate scratch backend/profile when the candidate is
launched; the operator owns the window and must not copy the installed home,
stored bearer, or model credentials into it. Install and enable the candidate
plugin for that scratch home before judging mount/disposal, and enable it in
Desktop Settings as well. Verify one Rhythm
sidebar entry and a mounted workspace root at `#/rhythm`, then disable/remove
the scratch plugin and use Rescan to verify route and backend-tool disposal.
This candidate check qualifies the fixed fork host, not the still-running
installed release. Do not change a long-running conversation's tool schema.
The candidate's bundled renderer wins over the scratch disk copy. The disk
package supplies the Python backend and a fallback runtime copy for releases
without the bundle; use the built-host source for renderer qualification.

## 3. Credential setup / Aug 22 connection (AJ credentials; then CLI)

M3's authenticated backend exposes `PUT /api/plugins/rhythm/connection` to accept
a token, validates it with pinned `GET /auth/me` and `GET /workspaces/me`, then
stores it through Hermes's locked auth store in `<profile HERMES_HOME>/auth.json`
(mode 0600). Only redacted identity/workspace metadata returns to the renderer.
Disconnect removes the `rhythm` record only. No token belongs in plugin files,
renderer state, screenshots, command arguments, shell history, or gate logs.

M3 has `POST /oauth/start` with PKCE S256, a five-minute, single-use,
profile-and-loopback-origin-bound state, and `GET /oauth/callback`. Configure
the **public** Google desktop client ID in the selected profile's `config.yaml`
under `plugins.rhythm.google_desktop_client_id`; do not put it in plugin source
or invent a client ID. Before creating PKCE state or opening Google, the plugin
requires `GET https://api.vcrcapps.com/auth/google/desktop-login-capability`
to return `{ "loginOnlyDesktopExchange": true }`; otherwise it returns a
recoverable 503 with no browser authorization URL. The browser authorization
code is exchanged only through
`POST https://api.vcrcapps.com/auth/google/desktop-login-exchange` with
`{code,codeVerifier,redirectUri}`. The plugin stores the returned Rhythm
`sessionToken`, not a Google access token. A missing/invalid public client ID
fails before OAuth state is created. The operator should use the visible
Desktop browser sign-in path; the host and provider registration still require
live qualification.

**Production blocker:** the deployed `/auth/google/desktop-exchange` handler
unconditionally calls `storeDesktopIntegration` after login, and that method
upserts Google Calendar/Gmail credentials and scopes. A basic-login OAuth grant
can replace an existing broader integration. The login-only capability and
exchange are implemented and tested locally in the Rhythm API worktree but
are not yet deployed. The plugin deliberately fails closed against the old
server. The one-time code from the prior attempt is consumed; do not inspect
or reuse it.

An Aug 22 record is **not automatically reused**: older records lack the new
`origin: https://api.vcrcapps.com` binding (and may lack a completion generation).
The installer preserves `auth.json`, but the plugin treats an unbound/other-host
record as disconnected without transmitting its token. AJ can explicitly supply
a token known to belong to this API; successful validation saves a new binding
and generation. Already-bound records in the same profile can be reused while
the token remains valid. Never print the old stored record to inspect it.

Do not type or copy a bearer token into CLI prompts, command arguments, source,
config, logs, screenshots, or test fixtures for this gate. The operator enters
the public client ID in the selected profile only; the browser handles consent
and the plugin's profile-scoped auth store handles the session token.

## 4. Read-only live slice and network assertion (CLI + AJ Desktop/browser)

Establish the connection **before** capturing this slice. Browse only Dashboard,
Tasks, and task inspection, then click **Ask Hermes about this**. Do not click
complete, reschedule, or any other mutation control in this slice. Assert an
editable draft with bounded Rhythm context opens, **no message is sent**, no
agent turn starts, and the task remains unchanged after reload.

For a method-only hosted trace of the actual Desktop requests, the orchestrator
may start this temporary, instrumented backend, connect Desktop to its loopback
URL using the normal authenticated connection setup, and perform the slice there.
The worker did not start it. Keep Hermes's normal local authentication enabled.
Use a free port; stop only this process with Ctrl-C when finished.

```bash
"$RHYTHM_PYTHON" -I - <<'PY'
import atexit
import json
import sys
import httpx
counts = {'GET': 0, 'POST': 0, 'PATCH': 0, 'PUT': 0, 'DELETE': 0}
send = httpx.Client.send

def audited_send(client, request, *args, **kwargs):
    if request.url.host == 'api.rhythm.app':
        raise RuntimeError('Retired Rhythm host is forbidden')
    if request.url.host == 'api.vcrcapps.com':
        if request.url.scheme != 'https' or request.url.port not in (None, 443):
            raise RuntimeError('Unexpected Rhythm origin')
        method = request.method
        counts[method] = counts.get(method, 0) + 1
        # No headers, bodies, query strings, task ids, or tokens are logged.
        print('RHYTHM_HOSTED_METHOD', method, flush=True)
        if method != 'GET':
            raise RuntimeError('Read-only gate attempted a hosted mutation')
    return send(client, request, *args, **kwargs)

httpx.Client.send = audited_send
atexit.register(lambda: print('RHYTHM_READONLY_COUNTS', json.dumps(counts, sort_keys=True)))
from hermes_cli.main import main
sys.argv = ['hermes', 'serve', '--host', '127.0.0.1', '--port', '48761', '--isolated']
main()
PY
```

Capture only `RHYTHM_HOSTED_METHOD`/`RHYTHM_READONLY_COUNTS` lines as evidence, not
raw server logs. Require GET > 0 and POST = PATCH = PUT = DELETE = 0, no attempted
mutation error, and successful rendered data. An empty trace is a failure (wrong
backend or no request). The guard reports attempted writes before refusing them;
a blocked write **fails** the gate. Browser DevTools should additionally show
only namespaced local Rhythm requests and no direct hosted bearer request from
the renderer. This audits the synchronous httpx transport used by the plugin;
if that transport changes, update the trace before treating it as evidence.

In a fresh opted-in agent session, ask for `rhythm_get_dashboard` and
`rhythm_list_tasks`. Confirm bounded results agree with the visible workspace,
and no read tool asks for or leaks the hosted token. Verify the same zero-write
trace. Keep **Ask Hermes** draft testing separate from intentionally sending
these read-tool requests.

## 5. Approval-bound task completion (separate mutation slice; AJ/client)

Stop the read-only guarded backend. Choose one disposable, owned task and record
its current status. Run an ACP-capable Hermes client in interactive approval mode
(`hermes acp` is the server command; the client supplies ACP session/permissions).
Invoke `rhythm_complete_task` for that exact task ID. First deny: no PATCH, status
unchanged on `rhythm_list_tasks` read-back. Invoke again and select **allow once**:
expect exactly one hosted PATCH `/tasks/<id>` with `{"status":"done"}`, followed
by GET of that exact task, and confirm `status=done` in UI and native read-back.
Record method/path/status only; omit headers, payload user text and credentials.
No other hosted data origin is allowed. Never fabricate the ACP requester or use
a persistent auto-approval mode to pass this gate.

The implementation deliberately returns `acp_approval_required` when no trusted
ACP session/requester or origin-bound connection generation is available. A
normal Desktop/CLI session without that requester proves rejection only, **not**
successful completion. Record that case as incomplete and use an ACP-capable
client for the allow-once gate. Conflict, expired/cross-profile receipt, ambiguous
transport, or changed canonical state must fail closed without retry/false success.

## 6. Disable → uninstall → diagnostics (CLI plus AJ Desktop)

```bash
hermes plugins disable rhythm
hermes plugins list --enabled --plain
hermes plugins doctor rhythm --ci
hermes doctor
# After verifying disabled behavior and finishing active turns:
hermes plugins remove rhythm
# CLI removal owns the Python half; remove only the standalone desktop half:
rm -rf "$HOME/.hermes/desktop-plugins/rhythm"
hermes plugins list --user --plain
hermes doctor
```

Toggle Rhythm off in Desktop Settings → Plugins before removal, restart Desktop
and its backend, then confirm its route/sidebar/palette are gone, native tools
are absent in a **new** conversation, and the public OAuth callback is unavailable.
After removal, `hermes plugins doctor rhythm --ci` must report absent/error rather
than falsely claiming an installed plugin. Do not delete dated backups or the
profile's auth record during this gate. Restoring the old code means extracting
the corresponding `backup.tar` into its parent plugin root with Desktop stopped;
the record remains disconnected until explicitly revalidated if unbound.

## Automated coverage and live ownership

All Python paths below are relative to `tests/plugins/rhythm/`. These are
socket-free fixtures; none proves a credentialed live outcome. Desktop specs
already exist under `apps/desktop/src/contrib/` and were **not run** because
`apps/desktop/node_modules` is absent. No Playwright/server/Electron run was made.

| Check | Existing automated evidence | Live operator |
| --- | --- | --- |
| Install, immutable backups, exact files, rollback | `test_rhythm_install_local.py` (all); `test_rhythm_packaging_scaffold.py::test_temp_home_lifecycle_is_opt_in_reversible_and_confined_to_rhythm_tree` | CLI; close Desktop first |
| One bundle, no React/maps/env/development JSX | `test_rhythm_packaging_scaffold.py::test_build_rebuilds_both_bundles_with_only_host_imports_and_no_secret_sources`, `test_package_gate_rejects_unsafe_code_in_either_bundle`, repeatable-build test | CLI/pytest |
| Doctor and uninstall | `test_rhythm_packaging_scaffold.py::test_doctor_uses_installed_manifest_and_redacts_raised_probe_errors`, temporary-home lifecycle test | CLI; Desktop removal observation requires AJ |
| Sidebar, route, reload, disposal | `test_rhythm_contracts.py::TestArchitectureContractStructure`; actual rendered lifecycle: `rhythm-shell.test.ts` owns one route/sidebar and reloads without duplicates | AJ Desktop; Python contract is not render proof |
| Connection/origin/privacy and old record rejection | `test_rhythm_backend.py::test_connection_lifecycle_validates_then_persists_redacted_metadata`, `test_auth_store_is_profile_isolated_and_private`, `test_legacy_or_other_origin_connection_is_not_reused`, `test_saved_connection_is_bound_to_the_one_approved_host` | AJ token or browser sign-in; CLI validation |
| Callback disabled/replay/origin isolation | `test_rhythm_mounted_oauth.py` (all); backend PKCE tests | CLI/pytest; actual OAuth registration needs browser/provider verification |
| Dashboard/tasks read and zero hosted writes | `test_rhythm_backend.py::test_read_only_dashboard_and_tasks_are_sanitized`, `test_dashboard_and_task_writes_are_unreachable`; M10 exact GET trace; `rhythm-workspace-ui.test.tsx` read-only mounted screens | CLI trace + AJ Desktop/browser |
| Native reads bounded/untrusted | `test_rhythm_m8_native_tools.py::test_issue_12_registers_only_the_three_native_tools_and_reads_are_bounded_untrusted` | CLI/agent client + live comparison |
| Complete deny/allow once/read-back | `test_rhythm_m8_native_tools.py` missing/denied ACP, exact prestate/single-use, altered scope, changed canonical state, uncertain transport tests; `test_rhythm_backend.py::test_task_mutation_is_one_exact_patch_with_stable_idempotency_and_canonical_readback` | AJ interactive ACP client and disposable task |
| Ask Hermes draft, never send | `test_rhythm_contracts.py::TestPermissionsContract::test_ask_hermes_never_auto_sends` is policy only; behavioral specs: `rhythm-workspace-ui.test.tsx` “maps accepted follow-up context to exactly one bounded unsent host draft” and “keeps detail failure local…” | AJ Desktop, new draft and no turn/network send observed |
| Final M10 and disabled actions | `test_rhythm_m10_cutover.py` (all), `test_rhythm_m7_contract.py::test_issue_11_allowlist_contains_only_classified_reads` | CLI/pytest plus all live gates above |

Do not close live acceptance based on the historical M10 ledger's mounted/a11y
labels: the Python cutover generator carries those labels forward; it does not
execute a renderer. Current installed Desktop behavior, axe/zoom/RTL checks,
real API schema compatibility, and signed/notarized release remain separate gates.
