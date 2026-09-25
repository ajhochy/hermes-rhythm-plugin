import { describe, expect, it } from 'vitest'

import { isEmbeddedDesktop } from './embedded-mode'

describe('isEmbeddedDesktop', () => {
  it('only enables host mode for the explicit embedded=1 renderer URL', () => {
    expect(isEmbeddedDesktop('?embedded=1')).toBe(true)
    expect(isEmbeddedDesktop('?embedded=0')).toBe(false)
    expect(isEmbeddedDesktop('?win=hud')).toBe(false)
    expect(isEmbeddedDesktop('?embedded=1&win=hud')).toBe(false)
  })
})
