---
date: 2026-09-19
repo: hermes-rhythm-plugin
branch: mega/2026-09-18-rhythm-plugin-finish
pr: 17
issues: []
status: pending
tags: [run, hermes-rhythm-plugin]
---

## Files

- No plugin source changed. `~/.hermes/config.yaml`: added `plugins.rhythm.google_desktop_client_id`
  (the public PKCE desktop client, `GOOGLE_AUTH_CLIENT_ID` from the shipped Rhythm build).
  Backup written alongside as `config.yaml.bak-rhythm-<epoch>`.

## Checks

- `packaging/build.py` → validated package; `install-local.sh` → installed into `~/.hermes`.
- `hermes plugins doctor rhythm --ci`: OK, 3 tools, 0 hooks. `hermes plugins list`: rhythm enabled 0.1.0.
- `hermes plugins enable rhythm --no-allow-tool-override`, then `hermes gateway restart`
  (launchd-supervised; `gateway run --replace` is refused) and a full Hermes Desktop restart.
- `gui.log`: `Mounted plugin API routes: /api/plugins/rhythm/`.
- `GET /api/plugins/rhythm/connection` (authenticated, Desktop backend): `200 {"connected":false}`.
- Desktop screen renders the Rhythm nav entry and the sign-in prompt; no error boundary crash.
- `POST /api/plugins/rhythm/oauth/start`: was `503 oauth_client_not_configured`; after the config
  change it is `503 oauth_login_only_unavailable` — the documented fail-closed state.
- `GET https://api.vcrcapps.com/auth/google/desktop-login-capability`: **404**.

## Notes

- The plugin's OAuth path cannot complete: the login-only capability/exchange routes it requires
  were removed from the Rhythm API by the 2026-09-19 desktop-login revert (Rhythm
  `docs/ai/runs/2026-09-19-desktop-login-revert.md`), which was made by request to restore the
  Electron desktop sign-in. The plugin deliberately fails closed rather than use the old
  `/auth/google/desktop-exchange`, which upserts Google Calendar/Gmail credentials and can
  downgrade existing scopes (LIVE-GATE §3 "Production blocker").
- Two ways forward, both needing AJ: (a) `PUT /api/plugins/rhythm/connection` with a Rhythm
  session token (the documented "AJ credentials; then CLI" path), or (b) restore and deploy the
  login-only routes, which reopens the question the revert settled.
- `hermes plugins reload` does not exist in this CLI; `install-local.sh`'s printed hint is stale.

## Follow-up — the second server path was unnecessary (a5a4818f25)

The plugin now uses the deployed `POST /auth/google/desktop-exchange`, the same
endpoint the Electron app uses. It never needed its own.

`storeDesktopIntegration` upserts the single Google account row with **this
grant's** `tokens.scope` and `tokens.refresh_token ?? null`. The plugin asked for
`openid email profile` with no `access_type`/`prompt`/`include_granted_scopes`,
so a plugin sign-in narrowed the row's scope to identity-only *and* nulled the
refresh token — that is the Calendar/Gmail downgrade, and the reason a
"login-only" exchange got built. Requesting the identical grant turns the same
write into a refresh.

- `GOOGLE_DESKTOP_SCOPES` mirrors `apps/electron/src/google-oauth-core.mjs`;
  `access_type=offline`, `prompt=consent`, `include_granted_scopes=true` added.
- `require_login_only_capability` and its 503 precondition removed.
- `POST /oauth/start` verified live: HTTP 200 with a real
  `accounts.google.com` URL carrying the four Electron scopes.
- 295 plugin tests pass; the scope-parity test was mutation-checked by removing
  `calendar.readonly` (it fails, as intended).

Remaining: AJ completes the Google sign-in in the browser. No Rhythm API deploy
and no Electron change are required.
