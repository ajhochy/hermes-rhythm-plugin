# Terra core/security repair — 2026-08-19

- Base: `806bc6e34c92f90978c783a557a45f7b00c71b7a` (rejected final-review base).
- Scope: authoritative HCW core, schemas, native HCW plugin guard, and focused tests only.
- Repairs: fail-closed native mutation policy; exact stage-bound lifecycle terminal parsing; exact plan command contracts; RED dirty-path enforcement; scoped service-owned commits; ordered verify/live transitions; immutable Kanban task bodies and compensating graph cleanup; bounded goal and dispatch attribution; repair attempt binding; symlink-root and evidence artifact integrity checks.
- Hook authority: the native plugin `pre_tool_call` hook governs Hermes-dispatched tools. It cannot intercept external Codex app-server command/file events; installer/runtime bridge enforcement remains outside this repair owner’s scope.
- Validation: focused core/plugin tests, Python compile, wheel build, and scoped diff checks (no network, installation, push, merge, or commit).
# Superseded by [terra-final-reconcile.md](terra-final-reconcile.md).
