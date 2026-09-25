import { createElement } from 'react'
import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PALETTE_AREA } from '@/app/command-palette/contrib'
import { contributedRoutes, SIDEBAR_NAV_AREA } from '@/app/routes'
import { registry } from '@/contrib/registry'

import plugin, { RhythmWorkspace } from '../../../../plugins/rhythm/desktop/src/plugin'
import { rhythmRouteTarget } from '../../../../plugins/rhythm/desktop/src/route-state'
import type { RhythmHostAdapter } from '../../../../plugins/rhythm/desktop/vendor/rhythm-workspace-ui/dist/index.js'

const providerCaptures = vi.hoisted(() => ({ hosts: [] as RhythmHostAdapter[] }))

vi.mock('../../../../plugins/rhythm/desktop/vendor/rhythm-workspace-ui/dist/index.js', async importOriginal => {
  const actual = await importOriginal<typeof import('../../../../plugins/rhythm/desktop/vendor/rhythm-workspace-ui/dist/index.js')>()
  return {
    ...actual,
    RhythmWorkspaceProvider: (props: React.ComponentProps<typeof actual.RhythmWorkspaceProvider>) => {
      providerCaptures.hosts.push(props.host)
      return createElement(actual.RhythmWorkspaceProvider, props)
    },
  }
})

const summary = { openTaskCount: 0, threadCount: 0, tasks: [], project: null, unreadThreads: [] }
const routeFixtureRest = vi.fn(async (path: string) => {
  if (path === '/connection') return { connected: true }
  if (path === '/dashboard-summary') return summary
  if (path === '/tasks') return { tasks: [] }
  if (path.startsWith('/planner/weeks/')) return { weekLabel: 'Fixture week', weekStart: '2026-09-21', backlog: [], days: [] }
  if (path === '/rhythm-rules' || path === '/project-templates' || path === '/project-instances' || path === '/automations/rules') return { items: [] }
  if (path === '/messages' || path === '/directory' || path === '/facilities' || path.startsWith('/facilities/reservations')) return []
  if (path === '/automations/catalog') return { providers: [], triggers: {}, actions: [] }
  if (path === '/integrations/status') return { accounts: [] }
  if (path === '/integrations/settings') return { calendarSources: [] }
  if (path === '/artifacts') return { items: [] }
  if (path === '/shared-agents') return { schema: 'rhythm.shared-agent-catalog.v1', scope: 'fixture', generatedAt: '2026-09-25T00:00:00Z', agents: [] }
  throw new Error(`unexpected route fixture GET ${path}`)
})

afterEach(() => {
  cleanup()
  providerCaptures.hosts.length = 0
  window.location.hash = ''
})

describe('Rhythm desktop shell (#5)', () => {
  it.each(['messages', 'facilities'] as const)('issue-1540-P1-route-%s: workspace selection uses the canonical screen route without a mutation', async destination => {
    routeFixtureRest.mockClear()
    render(createElement(RhythmWorkspace, { rest: routeFixtureRest as never, openExternal: vi.fn() }))
    await screen.findByTestId('rhythm-dashboard-screen')
    const adapter = providerCaptures.hosts.at(-1)
    expect(adapter).toBeDefined()

    act(() => adapter?.onNavigateToScreen?.(destination))

    expect(window.location.hash).toBe(`#${rhythmRouteTarget(`?tab=${destination}`)}`)
    expect(window.location.hash).toBe(`#/rhythm?tab=${destination}`)
    expect(routeFixtureRest.mock.calls.every(args => args.length === 1)).toBe(true)
  })

  it('issue-1540-P1-route-roundtrip-ten: every approved canonical link survives workspace reload parsing', async () => {
    const destinations = [
      ['overview', 'rhythm-dashboard-screen'],
      ['tasks', 'rhythm-tasks-screen'],
      ['planner', 'rhythm-planner-screen'],
      ['rhythms', 'rhythm-rhythms-screen'],
      ['projects', 'rhythm-projects-screen'],
      ['messages', 'rhythm-messages-screen'],
      ['facilities', 'rhythm-facilities-screen'],
      ['automations', 'rhythm-automations-screen'],
      ['integrations', 'rhythm-integrations-screen'],
      ['artifacts', 'rhythm-artifacts-screen'],
    ] as const

    for (const [destination, testId] of destinations) {
      routeFixtureRest.mockClear()
      window.location.hash = rhythmRouteTarget(`?tab=${destination}&workspace=team_1`)
      const view = render(createElement(RhythmWorkspace, { rest: routeFixtureRest as never, openExternal: vi.fn() }))
      expect(await screen.findByTestId(testId)).not.toBeNull()
      expect(rhythmRouteTarget(window.location.hash.split('?')[1] ? `?${window.location.hash.split('?')[1]}` : '')).toBe(`/rhythm?tab=${destination}&workspace=team_1`)
      expect(routeFixtureRest.mock.calls.every(args => args.length === 1)).toBe(true)
      view.unmount()
    }
  })

  it('issue-1540-P1-route-sanitization: unknown tabs and unsafe workspace values stay out of the mounted route', async () => {
    window.location.hash = '/rhythm?tab=admin&workspace=%3Cscript%3E'
    render(createElement(RhythmWorkspace, { rest: routeFixtureRest as never, openExternal: vi.fn() }))

    expect(await screen.findByTestId('rhythm-dashboard-screen')).not.toBeNull()
    expect(rhythmRouteTarget('?tab=admin&workspace=<script>')).toBe('/rhythm')
    expect(providerCaptures.hosts.at(-1)?.onNavigateToScreen).toBeTypeOf('function')
  })

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

  it('HD-4: the agents tab round-trips through rhythmRouteTarget and the desktop route count stays unchanged', async () => {
    const disposers: Array<() => void> = []
    plugin.register((await import('./plugin')).createPluginContext('rhythm', dispose => disposers.push(dispose)))

    // Round trip: the new tab value is neither dropped (unknown tab) nor
    // routed to a second page.
    expect(rhythmRouteTarget('?tab=agents')).toBe('/rhythm?tab=agents')
    expect(rhythmRouteTarget('?tab=agents&workspace=team_1')).toBe('/rhythm?tab=agents&workspace=team_1')
    // Route count is unchanged: still exactly one `/rhythm` page, matching the
    // desktop route contract (§5.4 — "the desktop route contract stays
    // ['/rhythm']").
    expect(contributedRoutes().filter(route => route.path === '/rhythm')).toHaveLength(1)

    routeFixtureRest.mockClear()
    window.location.hash = rhythmRouteTarget('?tab=agents')
    render(createElement(RhythmWorkspace, { rest: routeFixtureRest as never, openExternal: vi.fn() }))
    expect(await screen.findByTestId('shared-agents-screen')).not.toBeNull()
    expect(routeFixtureRest.mock.calls.some(([path]) => path === '/shared-agents')).toBe(true)

    disposers.forEach(dispose => dispose())
  })
})
