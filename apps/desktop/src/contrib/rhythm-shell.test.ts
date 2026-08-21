import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import { PALETTE_AREA } from '@/app/command-palette/contrib'
import { contributedRoutes, SIDEBAR_NAV_AREA } from '@/app/routes'
import { registry } from '@/contrib/registry'

import plugin from '../../../../plugins/rhythm/desktop/src/plugin'
import { rhythmRouteTarget } from '../../../../plugins/rhythm/desktop/src/route-state'

const rhythmPluginSource = resolve(process.cwd(), '../../plugins/rhythm/desktop/src/plugin.tsx')

describe('Rhythm desktop shell (#5)', () => {
  it('owns exactly one route and one sidebar row, with allowlisted query state', async () => {
    const disposers: Array<() => void> = []
    plugin.register((await import('./plugin')).createPluginContext('rhythm', dispose => disposers.push(dispose)))

    expect(contributedRoutes().filter(route => route.path === '/rhythm')).toHaveLength(1)
    expect(registry.getArea(SIDEBAR_NAV_AREA).filter(c => (c.data as { path?: string }).path === '/rhythm')).toHaveLength(1)
    expect(rhythmRouteTarget('?tab=tasks&workspace=team_1')).toBe('/rhythm?tab=tasks&workspace=team_1')
    expect(rhythmRouteTarget('?tab=admin&workspace=<script>')).toBe('/rhythm')

    disposers.forEach(dispose => dispose())
    expect(contributedRoutes().filter(route => route.path === '/rhythm')).toHaveLength(0)
  })

  it('reloads without duplicate contributions', async () => {
    const { createPluginContext } = await import('./plugin')
    const first: Array<() => void> = []
    plugin.register(createPluginContext('rhythm', dispose => first.push(dispose)))
    first.forEach(dispose => dispose())
    const second: Array<() => void> = []
    plugin.register(createPluginContext('rhythm', dispose => second.push(dispose)))

    expect(contributedRoutes().filter(route => route.path === '/rhythm')).toHaveLength(1)
    expect(registry.getArea(PALETTE_AREA).filter(c => c.source === 'plugin:rhythm')).toHaveLength(1)
    second.forEach(dispose => dispose())
  })

  it('keeps the packaged workspace route read-only and hands Ask Hermes an unsent bounded draft', async () => {
    const source = await readFile(rhythmPluginSource, 'utf8')

    expect(source).toContain("rest<DashboardSummary>('/dashboard-summary')")
    expect(source).toContain("rest<{ tasks: Task[] }>('/tasks')")
    expect(source).toContain('host.newChat({')
    expect(source).toContain('source: { label: \'Rhythm task\'')
    expect(source).toContain('data-readonly="true"')
    expect(source).not.toMatch(/rest<[^>]+>\([^\n]+method:\s*['"](?:POST|PUT|PATCH|DELETE)/)
  })
})
