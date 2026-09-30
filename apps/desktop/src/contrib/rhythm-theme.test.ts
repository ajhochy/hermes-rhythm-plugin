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
  it('uses the canonical Rhythm Electron palette instead of the old indigo skin', () => {
    expect(tokens.light).toMatchObject({
      background: '#ECF6F2',
      card: '#F8FDFB',
      popover: '#FFFFFF',
      sidebar: '#D8EEE5',
      border: '#C0D7D1',
      input: '#5D837B',
      textPrimary: '#03201D',
      textSecondary: '#19403A',
      textMuted: '#2E5951',
      primary: '#007760',
      primaryForeground: '#F2FBF7',
      destructiveForeground: '#FFF6F6',
      error: '#AC1730',
      success: '#00631B',
      warning: '#6D4800'
    })
    expect(tokens.dark).toMatchObject({
      background: '#252727',
      card: '#2B2E2D',
      popover: '#363C39',
      sidebar: '#323735',
      border: '#3E4542',
      textPrimary: '#DEDFDF',
      textSecondary: '#BFC6C3',
      textMuted: '#ABB2B0',
      primary: '#42C3A6',
      primaryForeground: '#010E0C',
      destructiveForeground: '#140707',
      error: '#FF666F',
      success: '#60C473',
      warning: '#F0BB3B'
    })
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
