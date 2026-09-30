# M10 post-cutover deletion plan (approval required)

This is a planning record only. Issue #14 does not remove Electron code, agent
navigation, adapters, screens, or plugin files.

Before any deletion is approved, AJ must complete the manual cutover and merge
gate, and a signed/notarized release must pass its separate release gate. A
follow-up issue must then inventory each proposed removal, identify its owning
surface and rollback path, prove it has no active import/route/tool references,
and run the full desktop/shared-runtime/package lifecycle suite on a dedicated
branch. The removal change must remain reversible until the next dogfood cycle
passes.
