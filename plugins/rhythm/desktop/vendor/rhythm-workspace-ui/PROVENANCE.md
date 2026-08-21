# Vendored accepted artifact

Source: `@ajhochy/rhythm-workspace-ui` 0.2.0

Source revision: `704fd53e73f985bfa5eeeb08f1bc499762742dd3` (accepted shared package source; copied without local source edits).

Transformation: none. `dist/` and `package.json` are copied verbatim from the source build, including ESM/CJS source maps and every npm-published file.

This directory is the package's production `dist/` output plus its published manifest. It is intentionally imported as one externalized React peer graph; the host Vite configuration aliases and deduplicates React/React DOM.

M6 artifact SHA-256: `index.js 0f00b178fc46335d35bf1c4a26a7d328c4fce4031f9a18ab3e12e6e371bd9a64`; `index.cjs 7c5ae845fd3ca4bc5d8455ccecd36cf630a6ba7a994790732d946707d789ceda`; `index.d.ts 795ef1e000d361f19d911174211e886d919e2fefd5798de83af3364601d555c0`. React/React DOM are external peers: `^18.3.1 || ^19.2.0`.
