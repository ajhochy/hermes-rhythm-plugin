# Vendored accepted artifact

Source: `@ajhochy/rhythm-workspace-ui` 0.2.0

Source revision: `98874481285250b7441b68744787051a4b286fc1` (Rhythm `.mega-wt/integration`, branch `mega/2026-09-18-mobile-electron-hermes`; accepted #1540 P4 package source, includes the S6 shared-agent catalog/editor and the P2/P3 ListInspector screens; copied without local source edits).

Transformation: none. `dist/` and `package.json` are copied verbatim from the source build (`npm run build`, i.e. `tsup` + `scripts/copy-styles.mjs`, run against the package's own installed `node_modules` outside this checkout), including ESM/CJS source maps and every npm-published file. The source build bundles the real `lucide-react` icon runtime while React/React DOM remain external peers ("react" and "react/jsx-runtime" only appear as import specifiers in the built JS; `react-dom` is not imported), so the unified feature pack requires no second UI implementation or icon runtime.

This directory is the package's production `dist/` output plus its published manifest. It is intentionally imported as one externalized React peer graph; the desktop packaging build (`plugins/rhythm/packaging/build.py`) externalizes exactly `@hermes/plugin-sdk`, `react`, `react/jsx-runtime`, `react/jsx-dev-runtime` (`DESKTOP_BUNDLE_EXTERNALS`) when it folds this vendor artifact into the single desktop ESM bundle.

Dist SHA-256 (source revision 98874481285250b7441b68744787051a4b286fc1):
- `index.cjs` `21e4ceba710b516a3d52c1154ba6f4afec7d9081251f539cd4bd43ce8bab3adf`
- `index.cjs.map` `c17361149af436adab587b6f002d506e0bb40b123dbe59b5921f841e016b4545`
- `index.d.cts` `038d85a3956c5a85b739e8e9717e44c0f0f0272c8e7ee595ad7a0ef901a035ff`
- `index.d.ts` `038d85a3956c5a85b739e8e9717e44c0f0f0272c8e7ee595ad7a0ef901a035ff`
- `index.js` `2c6e8e3a30b13addd2a29e07a16e938465be55db63639b1ad9c5e77f1d8bd53a`
- `index.js.map` `cf12d693c76b2379077e7b07b06bbe9fc454e69f7f88869c36ea01c01e2ee31c`
- `styles/base.css` `4c6163d1b9e9079f2100a0d50fd669425789b4108ce9ccb37bc66e914c4275d7`
- `styles/collaboration.css` `b3cefa2841cdabca8ba5b807f9b00c6ff8122b37b7f2a1180c42588ab89c5277`
- `styles/list-inspector.css` `cf1755b4b775824cf931ede56d666b14f9c13b69a1fe82ec50e322deb53bb903`
- `styles/operations.css` `bc582cf2ad85f21c8968e5e6274b033591340bf5ba1605cb8dbfce91bbd4ee50`
- `styles/rhythm.css` `92143f8af5fad18c3c5802f63d237e0559eee1d3bb92724a9f8946b84ca788d4`
- `styles/screens/automations.css` `df25ff82794bae371b51f8a6354fe3a3b85020fa43f5a86c6e89bbf74c2b6d4d`
- `styles/screens/dashboard.css` `23af6e09fa80b418a031bc1b0f9ede0d6349e0ff2f9d94005335160c75df82bb`
- `styles/screens/facilities.css` `840132665e3a302a4aac22b84409d1155816c1dda624530a44196c8b5310457b`
- `styles/screens/integrations.css` `3c97232e1dbde21e787e6cf71ff1b5c75f5fc684756701ea29cb1810b01c27e6`
- `styles/screens/messages.css` `58104437da21a00f0728511428af811fbfcd56b3f8673e914533bcd2d97eedda`
- `styles/screens/planner.css` `01e77f16f0e7f9f007011ef8c5a6be8230701270f679661b89ce0d49d7748a12`
- `styles/screens/projects.css` `c83bdf83c355225d24ba3c1513c84f43a58acfbe1464fd838a80f83aecfa18dd`
- `styles/screens/rhythms.css` `de95bbb16d34adbb623cfe15a032804944abdc352eea3df865ba2a0ddebcd03f`
- `styles/screens/shared-agents.css` `85eac6807088c0ae66cf25b0cfa757573688dca7f940c64aaa6bba8fe65d3721`
- `styles/screens/tasks.css` `bed290a40c9e910ee036945e746d865c5a638477e4d50213f36b6841bd88493e`

React/React DOM are external peers: `^18.3.1 || ^19.2.0`. `list-inspector.css` and `screens/shared-agents.css` are new relative to the prior `d676faae` vendor drop (P2/P3 ListInspector primitive and the S6 shared-agent catalog/editor screen); no file present before was removed.
