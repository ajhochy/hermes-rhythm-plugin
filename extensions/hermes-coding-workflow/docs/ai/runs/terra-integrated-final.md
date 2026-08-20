# Integrated final repair — 2026-08-19

- Replaced rejected pre-v1 plugin fixtures with authoritative `hcw/v1` state and real Hermes v0.20 package scanning.
- Added the stable native bootstrap marker, absolute installed launcher guidance, bare role-skill registration, and a testable fail-closed guard decision path.
- Persisted per-stage status in the authoritative run record and updated it with every lifecycle transition.
- Made Kanban graph linking use Hermes's real non-JSON link command and kept command execution argv-only with redacted, hashed evidence.
- Converted the disposable-repository test into an always-executed installed lifecycle proof using actual Hermes boards, role homes, task identities, checks, reviews, verifier, recorder, doctor, and native plugin guard behavior.
- Validation target: Python suite with `-ra` and no skipped/xfailed tests, Node test/build, wheel build, Hermes package doctors, and secret/diff scans.
# Superseded by [terra-final-reconcile.md](terra-final-reconcile.md).
