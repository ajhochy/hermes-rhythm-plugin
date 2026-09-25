import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import { contrastRatio } from '@/themes/color'
import { contributedThemes, resolveTheme } from '@/themes/user-themes'

import plugin from '../../../../plugins/rhythm/desktop/src/plugin'
import { rhythmDesktopTheme } from '../../../../plugins/rhythm/desktop/src/theme'
import { createPluginContext } from './plugin'

const tokens = JSON.parse(
  readFileSync(join(__dirname, '../../../../plugins/rhythm/theme/tokens.json'), 'utf-8')
) as { light: Record<string, string>; dark: Record<string, string> }

describe('Rhythm desktop theme contribution (#1543-a)', () => {
  it('tokens.json declares the exact canonical brand hexes', () => {
    expect(tokens.light.primary).toBe('#4F6AF5')
    expect(tokens.light.sidebar).toBe('#F8F9FA')
    expect(tokens.light.border).toBe('#E5E7EB')
    expect(tokens.light.textPrimary).toBe('#111827')
    expect(tokens.light.textSecondary).toBe('#6B7280')
    expect(tokens.light.textMuted).toBe('#9CA3AF')
    expect(tokens.light.error).toBe('#EF4444')
    expect(tokens.light.success).toBe('#10B981')
    expect(tokens.dark).toBeTruthy()
  })

  it('every accessible foreground/background pair clears WCAG AA (4.5:1) in light and dark', () => {
    const pairs: Array<[fg: string, bg: string]> = [
      [rhythmDesktopTheme.colors.foreground, rhythmDesktopTheme.colors.background],
      [rhythmDesktopTheme.colors.primaryForeground, rhythmDesktopTheme.colors.primary],
      [rhythmDesktopTheme.colors.destructiveForeground, rhythmDesktopTheme.colors.destructive],
      [tokens.light.successAccessible, rhythmDesktopTheme.colors.background],
      [rhythmDesktopTheme.darkColors.foreground, rhythmDesktopTheme.darkColors.background],
      [rhythmDesktopTheme.darkColors.primaryForeground, rhythmDesktopTheme.darkColors.primary],
      [rhythmDesktopTheme.darkColors.destructiveForeground, rhythmDesktopTheme.darkColors.destructive],
      [tokens.dark.successAccessible, rhythmDesktopTheme.darkColors.background]
    ]

    for (const [fg, bg] of pairs) {
      expect(contrastRatio(fg, bg)).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('registers through THEMES_AREA and disposes cleanly, falling back to no active contribution', () => {
    const disposers: Array<() => void> = []
    plugin.register(createPluginContext('rhythm', dispose => disposers.push(dispose)))

    expect(contributedThemes().map(theme => theme.name)).toContain('rhythm')
    expect(resolveTheme('rhythm')?.name).toBe('rhythm')

    disposers.forEach(dispose => dispose())

    expect(contributedThemes().map(theme => theme.name)).not.toContain('rhythm')
    expect(resolveTheme('rhythm')).toBeUndefined()
  })
})
