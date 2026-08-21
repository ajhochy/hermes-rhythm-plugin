# Vendored accepted artifact

Source: `@ajhochy/rhythm-workspace-ui` 0.2.0

Source revision: `56fe6619299fad2f4cef2ffa8e8a9d681101bfa9` (accepted combined M6+M7 package source; copied without local source edits).

Transformation: none. `dist/` and `package.json` are copied verbatim from the source build, including ESM/CJS source maps and every npm-published file. The source build bundles the real `lucide-react` icon runtime while React/React DOM remain external peers, so the unified feature pack requires no second UI implementation or icon runtime.

This directory is the package's production `dist/` output plus its published manifest. It is intentionally imported as one externalized React peer graph; the host Vite configuration aliases and deduplicates React/React DOM.

Combined M6+M7+M9 artifact SHA-256: `index.js 5b1eb9e918652e25eb6b3c3af1e5d81c5efa92a465e8fe4b5f6c13570ce65df5`; `index.cjs 60725da01e0ef5da83cf0ffae708a636328adc31e385ae5ee8d6fd0236f91c0d`; `index.d.ts 7bb0a77896df5dd7a42f784ffa8ab3b6541e9b14bd14926593d47464366d5a1f`; `index.js.map 66801f553d1839d2f53d49ee3ca06b2ecaa4d199e9c9794c5dd1d13e39152026`; `index.cjs.map e43b9ff7c6679b31c2dbb446fa75c7eefac87108c30963744ed04693a0650d5e`. React/React DOM are external peers: `^18.3.1 || ^19.2.0`.
