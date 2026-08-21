# Vendored accepted artifact

Source: `@ajhochy/rhythm-workspace-ui` 0.2.0

Source revision: `b3cd1719b441fd399252e0adbfecd66ef3e02250` (accepted shared package source; copied without local source edits).

Transformation: none. `dist/` and `package.json` are copied verbatim from the source build, including ESM/CJS source maps and every npm-published file.

This directory is the package's production `dist/` output plus its published manifest. It is intentionally imported as one externalized React peer graph; the host Vite configuration aliases and deduplicates React/React DOM.

M5 artifact SHA-256: `index.js b2dd9cb9d66e64b590ee73fb00a1640e3ae616feb53c04794afded28ebae4604`; `index.cjs 26e4cd7f9b40c97b1d21b21d450c004f9e1f9a6d2a1b2528549710cd896ed760`; `index.d.ts 33d802c0d68138bd23d36d3e85755d98816b6c2d7bfd9298f959a4e259e2a16a`. React/React DOM are external peers: `^18.3.1 || ^19.2.0`.
