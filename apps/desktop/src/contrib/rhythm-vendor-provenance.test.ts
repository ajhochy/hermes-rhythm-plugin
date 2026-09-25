// HD-3 (§5.4, #1540 P4): the vendored Desktop artifact must match the hash
// recorded in its own PROVENANCE.md and name the accepted source revision —
// the guard against a hand-edited or stale vendor drop after a re-vendor.
// Mirrors tests/plugins/rhythm/test_rhythm_m7_contract.py's Python-side check
// for the same file, so both suites catch drift.
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

const VENDOR_DIR = join(__dirname, '../../../../plugins/rhythm/desktop/vendor/rhythm-workspace-ui')

describe('vendored rhythm-workspace-ui dist (HD-3)', () => {
  it('index.js matches the SHA-256 recorded in PROVENANCE.md', () => {
    const runtime = readFileSync(join(VENDOR_DIR, 'dist/index.js'))
    const provenance = readFileSync(join(VENDOR_DIR, 'PROVENANCE.md'), 'utf8')
    const recorded = /`index\.js`\s*`([0-9a-f]{64})`/.exec(provenance)

    expect(recorded).not.toBeNull()
    expect(createHash('sha256').update(runtime).digest('hex')).toBe(recorded?.[1])
  })

  it('names the accepted #1540 P4 source revision', () => {
    const provenance = readFileSync(join(VENDOR_DIR, 'PROVENANCE.md'), 'utf8')

    expect(provenance).toContain('98874481285250b7441b68744787051a4b286fc1')
  })
})
