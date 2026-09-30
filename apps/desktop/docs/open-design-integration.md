# Hermes Desktop + Open Design 0.20.0

This fork intentionally carries a first-class Open Design workspace even though the upstream Nous repository keeps third-party product integrations outside core. All Open Design-specific behavior stays behind `electron/open-design/` and `src/app/open-design/` so upstream rebases remain auditable.

The immutable acceptance source is [`open-design-integration.contract.json`](./open-design-integration.contract.json). Verification evidence belongs in a separate report; it must not weaken the frozen criteria after implementation starts.

## Product flow

```text
Hermes sidebar → Design
        │
        ▼
Hermes /design workspace (full-bleed; no browser chrome)
        │
        ▼
Sandboxed Electron <webview>
  exact loopback origin only
  profile-scoped persistent partition
        │
        ▼
Open Design 0.20.0 Next.js web sidecar
        │
        ▼
Open Design daemon sidecar
        │
        └── agentId: "hermes"
                │
                ▼
        HERMES_BIN acp --accept-hooks
                │
                ▼
        active compatible local Hermes profile
        and its existing provider credentials
```

No provider key crosses the Hermes/Open Design boundary. Open Design receives a Hermes executable location and profile-scoped process environment, then uses its existing Hermes ACP adapter.

## Runtime flow

```text
                        ┌──────────────────────────────┐
Hermes /design ─start─► │ OpenDesignRuntimeSupervisor │
                        └──────────────┬───────────────┘
                                       │
                    packaged? ─────────┼──────── installed fallback?
                       yes             │              yes
                        │              │               │
                        ▼              │               ▼
          staged signed OD 0.20 app        │     compatible Open Design.app
                        │              │               │
                        └──────────────┴───────────────┘
                                       │
                                       ▼
                    official packaged headless entry
                    (Open Design owns daemon/web sidecars,
                     readiness IPC, restart, and cleanup)
                                       │
                                       ▼
                         validated runtime identity
                         + bounded HTTP health probe
                                       │
                                       ▼
                        sanitized URL/state to renderer
```

Packaged builds download the official platform release asset into an external cache, verify the contract SHA-256, and stage the complete signed application payload through `electron-builder` as an extra resource. Hermes launches that application with `--headless`; Open Design creates no `BrowserWindow` and remains the lifecycle owner of its daemon and web sidecars. Installer/runtime binaries never enter Git.

The original Resources-only reuse assumption was falsified against the packaged Hermes executable: a renamed packaged Electron binary ignores an alternate `main.cjs` app path and boots its own embedded Hermes application. The release payload also contains no plain-Node headless bundle. [Amendment 1](./open-design-integration.amendment-1.json) records the evidence, size impact, rejected lifecycle-reimplementation alternative, and unchanged acceptance invariants.

## Skin flow

```text
Hermes ThemeProvider
  skin + light/dark mode + computed semantic tokens
        │
        ▼
versioned Open Design token adapter
        │
        ▼
webview.insertCSS + document data-hermes-theme attribute
        │
        ├── Open Design shell, panels, controls, editor, terminal
        └── excludes nested user preview documents and exported artifacts
```

The adapter targets Open Design semantic custom properties, never generated Next.js/Tailwind class hashes. Theme changes update the existing guest without navigation or reload.

## Non-negotiable boundaries

- No direct Next.js-to-Vite source merge.
- No provider credential copying, proxying, or renderer exposure.
- No arbitrary renderer-supplied URL, path, command, or environment crossing IPC.
- No Node integration or preload in the Open Design guest.
- No browser address bar, URL text, tab strip, or navigation chrome.
- No killing an attached Open Design runtime that Hermes did not start.
- No unverified vendor asset enters a package.
- No claim of completion without a real Hermes ACP generation and an installed-app-independent packaged smoke.

## Delivery slices

1. Contract and test harness.
2. Checksum-pinned runtime staging and lifecycle supervisor.
3. Typed IPC, hardened guest attachment, and built-in `/design` route.
4. Live skin bridge and polished loading/failure/focus UX.
5. Real Hermes ACP generation, visual/security regression, and self-contained package smoke.
6. Independent spec/security/maintainability review, repair, push, and PR.
