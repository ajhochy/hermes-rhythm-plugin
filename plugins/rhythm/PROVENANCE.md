# Rhythm package provenance

Source: Hermes Rhythm feature-pack source tree.

Revision: fork build base `c2133cc477` plus the B1 working-tree packaging and
host-origin changes recorded in the 2026-09-18 worker report. Vendored UI source
is `98874481285250b7441b68744787051a4b286fc1` (#1540 P4 re-vendor).

Transformation: deterministic local feature-pack build.  The package builder
stages the declared source, rebuilds the API-only dashboard entry, and emits one
Desktop ESM artifact with React peers external and Lucide embedded. Production
JSX, disabled environment inlining, no source maps, and a checked dependency
graph are required. The builder never signs, notarizes, publishes, or installs.
The separate install-local.sh script is an explicit operator action.

Vendored workspace UI provenance remains in
`desktop/vendor/rhythm-workspace-ui/PROVENANCE.md`. Final package provenance is
included in the final closed package manifest. Vendored maps remain source-tree
provenance only; none ships in the closed package.
