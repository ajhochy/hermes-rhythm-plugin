import { act, cleanup, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { rhythmDesktopTheme } from '../../../../plugins/rhythm/desktop/src/theme'
import { __resetBackendSkinSync, ingestBackendSkin } from './backend-sync'
import { skinPref, ThemeProvider, useTheme } from './context'
import { DEFAULT_SKIN_NAME, midnightTheme } from './presets'

// The live-authoring loop: Hermes writes/edits one skin file and every surface
// repaints. An in-place edit keeps the NAME — only the palette moves.
const bloomberg = (foreground: string) => ({
  name: 'bloomberg',
  colors: { background: '#000000', ui_text: foreground, ui_accent: '#ff8000' }
})

const cssVar = (name: string) => window.document.documentElement.style.getPropertyValue(name)

describe('ThemeProvider ← backend skin sync', () => {
  beforeEach(() => {
    window.localStorage.clear()
    __resetBackendSkinSync()
  })

  afterEach(cleanup)

  it('applies an activated backend skin', () => {
    render(
      <ThemeProvider>
        <div />
      </ThemeProvider>
    )

    act(() => ingestBackendSkin(bloomberg('#ff9f0a'), { apply: true }))

    expect(cssVar('--theme-foreground')).toBe('#ff9f0a')
    expect(cssVar('--theme-background-seed')).toBe('#000000')
  })

  it('repaints an in-place edit of the ACTIVE skin (same name, new palette)', () => {
    render(
      <ThemeProvider>
        <div />
      </ThemeProvider>
    )

    act(() => ingestBackendSkin(bloomberg('#ff9f0a'), { apply: true }))
    expect(cssVar('--theme-foreground')).toBe('#ff9f0a')

    // Recolor the same skin file. The same-name apply guard correctly no-ops
    // (protects manual desktop picks), so the repaint must come from the
    // registry update reaching the active theme derivation.
    act(() => ingestBackendSkin(bloomberg('#ff2d95'), { apply: true }))
    expect(cssVar('--theme-foreground')).toBe('#ff2d95')
  })

  it('does not repaint an edit to an INACTIVE skin', () => {
    render(
      <ThemeProvider>
        <div />
      </ThemeProvider>
    )

    act(() => ingestBackendSkin(bloomberg('#ff9f0a'), { apply: true }))

    // A different skin registered without apply (e.g. seeded on reconnect)
    // must not touch the painted theme.
    act(() =>
      ingestBackendSkin({ name: 'forest', colors: { background: '#001100', ui_text: '#66ff66' } }, { apply: false })
    )
    expect(cssVar('--theme-foreground')).toBe('#ff9f0a')
  })
})

describe('ThemeProvider highlight preview', () => {
  beforeEach(() => {
    window.localStorage.clear()
    __resetBackendSkinSync()
  })

  afterEach(cleanup)

  // Read the live context so the tests drive the real provider, not a mock.
  let ctx: ReturnType<typeof useTheme>

  function Probe() {
    ctx = useTheme()

    return null
  }

  const renderProbe = () =>
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>
    )

  it('paints the previewed theme without persisting it', () => {
    renderProbe()

    const committed = ctx.themeName

    act(() => ctx.previewTheme('midnight', 'dark'))

    expect(cssVar('--theme-foreground')).toBe(midnightTheme.colors.foreground)
    // The commit surface does not change. The context name and the stored
    // preference keep their values.
    expect(ctx.themeName).toBe(committed)
    expect(skinPref.resolve('default')).toBe(committed)
  })

  it('clearThemePreview repaints the committed appearance', () => {
    renderProbe()

    act(() => ctx.previewTheme('midnight', 'dark'))
    expect(cssVar('--theme-foreground')).toBe(midnightTheme.colors.foreground)

    act(() => ctx.clearThemePreview())
    expect(cssVar('--theme-foreground')).not.toBe(midnightTheme.colors.foreground)
  })

  it('a commit replaces the preview and persists', () => {
    renderProbe()

    act(() => ctx.previewTheme('midnight', 'dark'))
    act(() => ctx.setTheme('mono'))

    expect(ctx.themeName).toBe('mono')
    expect(skinPref.resolve('default')).toBe('mono')
    expect(cssVar('--theme-foreground')).not.toBe(midnightTheme.colors.foreground)
  })

  it('ignores a preview of an unknown theme', () => {
    renderProbe()

    const painted = cssVar('--theme-foreground')

    act(() => ctx.previewTheme('does-not-exist', 'dark'))
    expect(cssVar('--theme-foreground')).toBe(painted)
  })
})

// #1543-b: an embedding host may bundle its own theme data and ask for a
// default skin while a profile has no explicit stored preference yet. This
// file has no knowledge of any particular host or skin name -- 'example-host-
// theme' below is an arbitrary generic name, standing in for whatever any
// host might pass.
describe('ThemeProvider ← embedding host default skin', () => {
  // Reuse the real #1543-a theme contribution as the "bundled by the host"
  // fixture: it is a genuine, fully-specified DesktopTheme (unlike a
  // hand-rolled partial one, `applyTheme` needs every color role), and it
  // proves the two slices work together end to end. This file still has no
  // knowledge of any particular host or skin name; the name only appears here,
  // in test data.
  const hostTheme = { ...rhythmDesktopTheme, name: 'example-host-theme', label: 'Example host theme' }

  beforeEach(() => {
    window.localStorage.clear()
    __resetBackendSkinSync()
  })

  afterEach(() => {
    cleanup()
    delete (window as { hermesDesktop?: unknown }).hermesDesktop
  })

  function mockEmbeddedHost(metadata: Record<string, unknown>) {
    ;(window as unknown as { hermesDesktop: unknown }).hermesDesktop = {
      embedded: { enabled: true, metadata: () => Promise.resolve(metadata) }
    }
  }

  it('applies the host default skin when the profile has no stored preference', async () => {
    mockEmbeddedHost({ embedded: true, defaultSkin: 'example-host-theme', themes: [hostTheme] })

    render(
      <ThemeProvider>
        <div />
      </ThemeProvider>
    )

    await waitFor(() => expect(cssVar('--theme-primary')).toBe(hostTheme.colors.primary))
    expect(cssVar('--theme-background-seed')).toBe(hostTheme.colors.background)
    expect(cssVar('--theme-sidebar-seed')).toBe(hostTheme.colors.sidebarBackground)
    expect(skinPref.resolve('default')).toBe('example-host-theme')
  })

  it('keeps a stored user skin instead of the host default', async () => {
    skinPref.assign('default', 'midnight')
    mockEmbeddedHost({ embedded: true, defaultSkin: 'example-host-theme', themes: [hostTheme] })

    let ctx: ReturnType<typeof useTheme>
    function Probe() {
      ctx = useTheme()
      return null
    }
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>
    )

    // Give the async metadata fetch a turn; it must be a no-op here.
    await act(async () => Promise.resolve())
    expect(ctx!.themeName).toBe('midnight')
    expect(cssVar('--theme-primary')).not.toBe(hostTheme.colors.primary)
  })

  it('falls back to the built-in default and never throws for an unknown defaultSkin or missing theme data', async () => {
    mockEmbeddedHost({ embedded: true, defaultSkin: 'not-a-real-theme', themes: [] })

    let ctx: ReturnType<typeof useTheme>
    function Probe() {
      ctx = useTheme()
      return null
    }
    expect(() =>
      render(
        <ThemeProvider>
          <Probe />
        </ThemeProvider>
      )
    ).not.toThrow()

    await act(async () => Promise.resolve())
    expect(ctx!.themeName).toBe(DEFAULT_SKIN_NAME)
  })
})
