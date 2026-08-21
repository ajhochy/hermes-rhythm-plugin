import { describe, expect, it } from 'vitest'

import { createPluginContext } from './plugin'

describe('plugin-owned runtime CSS', () => {
  it('deduplicates a plugin stylesheet and removes it on dispose', () => {
    const disposers: Array<() => void> = []
    const ctx = createPluginContext('rhythm', dispose => disposers.push(dispose))

    ctx.css('.rhythm-shell { color: red; }')
    ctx.css('.rhythm-shell { color: red; }')

    expect(document.head.querySelectorAll('style[data-hermes-plugin-style="rhythm"]').length).toBe(1)
    disposers.forEach(dispose => dispose())
    expect(document.head.querySelectorAll('style[data-hermes-plugin-style="rhythm"]').length).toBe(0)
  })

  it('rolls a stylesheet back if plugin registration fails', () => {
    const disposers: Array<() => void> = []
    const ctx = createPluginContext('rhythm', dispose => disposers.push(dispose))
    ctx.css('.rhythm-shell { color: red; }')
    disposers.forEach(dispose => dispose())

    expect(document.head.querySelector('[data-hermes-plugin-style="rhythm"]')).toBeNull()
  })
})
