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
