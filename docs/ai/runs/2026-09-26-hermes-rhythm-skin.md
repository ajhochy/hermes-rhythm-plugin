---
date: 2026-09-26
repo: hermes-rhythm-plugin
branch: codex/hermes-theme
pr: null
issues: [1543, 1570]
status: pass
tags: [run, hermes-rhythm-plugin]
---

# Hermes Rhythm skin palette and embedded artifact

## Files

- Replaced the old indigo Rhythm tokens with the canonical Electron teal/neutral palette.
- Regenerated dashboard CSS and Desktop TypeScript from `tokens.json`.
- Added generated `rhythm-theme.json` and made `build:rhythm-embedded` package it for offline embedded resolution.

## Checks

- RED: `cd apps/desktop && npm exec vitest run --project ui src/contrib/rhythm-theme.test.ts` — canonical-palette assertion failed against `#4F6AF5`; unrelated Planner tests also failed because that project command selected the full UI project.
- `cd apps/desktop && npm exec vitest run src/contrib/rhythm-theme.test.ts --config vite.config.ts` — 3/3 pass.
- `uv run --with pytest python -m pytest tests/plugins/rhythm -q` — 320/320 pass.
- `uv run python plugins/rhythm/theme/generate.py --check` — pass.
- `cd apps/desktop && npm exec vitest run scripts/build-embedded-artifact.test.mjs electron/embedded-host-theme.test.ts --project electron` — 1,503 pass, 2 skipped across the selected Electron project.
- `git diff --check` — pass.

## Notes

- OKLCH values were converted with the CSS Color 4 OKLab-to-linear-sRGB matrix, clamped to sRGB, gamma encoded, and rounded to 8-bit hex.
- GitNexus impact was attempted before implementation, but both indexed repos returned a LadybugDB storage-version mismatch (database 42, runtime 41); exact import/string references were inspected as fallback.
- The clean committed artifact build and visual receipts are recorded in the corresponding Rhythm integration run note.
