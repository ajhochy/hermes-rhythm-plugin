# Rhythm package provenance

Source: Hermes Rhythm feature-pack source tree.

Revision: fully integrated base `4a1578ae6dcb9f91f1912f464bd2a3608011cecf`.

Transformation: deterministic local feature-pack build.  The package builder
stages the declared source, emits one Desktop ESM artifact with React peers
external and Lucide embedded, and never signs, notarizes, publishes, or
touches a real Hermes home.

Vendored workspace UI provenance remains in
`desktop/vendor/rhythm-workspace-ui/PROVENANCE.md`. Final package provenance is
is included in the final closed package manifest.
