# Rhythm release signing gate

This feature pack has deterministic local build, package-tree, temporary-home,
and unsigned macOS fixture checks. It does **not** assert that a production
Hermes.app is signed, notarized, or stapled.

Before a release, a credentialed release operator must independently verify:

1. `codesign --verify --deep --strict Hermes.app`
2. notarization acceptance for the exact release artifact
3. `xcrun stapler validate Hermes.app`

No local automated M9 check claims those three production credentials or
outcomes. This manual release gate remains pending.
