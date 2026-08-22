# Vendored accepted artifact

Source: `@ajhochy/rhythm-workspace-ui` 0.2.0

Source revision: `d676faae5aff11796f39cb5f09031f57d5c5d061` (accepted final M10 package source; copied without local source edits).

Transformation: none. `dist/` and `package.json` are copied verbatim from the source build, including ESM/CJS source maps and every npm-published file. The source build bundles the real `lucide-react` icon runtime while React/React DOM remain external peers, so the unified feature pack requires no second UI implementation or icon runtime.

This directory is the package's production `dist/` output plus its published manifest. It is intentionally imported as one externalized React peer graph; the host Vite configuration aliases and deduplicates React/React DOM.

Final M10 artifact SHA-256: `index.js c93f1375705a6310c232fad0d0382f1a07475494b0f19cd17b8929a3b2dc279d`; `index.cjs 19d91c30990958efd40ca323d7faca4af973b8ceef8f85b19325247efcb646ab`; `index.d.ts 7bb0a77896df5dd7a42f784ffa8ab3b6541e9b14bd14926593d47464366d5a1f`; `index.js.map 93e06327ea09f50f0e4b7eb43d8dcf0c3dc2dd8119e6b1bccaf05823292c7b79`; `index.cjs.map bad379a99df4bcad81f0a5c2073c265b612bbbe9a3ec4c6f35338325379026a0`. React/React DOM are external peers: `^18.3.1 || ^19.2.0`.
