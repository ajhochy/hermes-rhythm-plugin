/**
 * Read-only host integration for the accepted @ajhochy/rhythm-workspace-ui
 * artifact, built from accepted source revision
 * 8187ed025f678779cd9c8a779074d8e54f4c8ddc (see vendor provenance).
 * The package remains the owner of Dashboard/Tasks JSX and styles; this file
 * owns only the Hermes transport, lifecycle and bounded chat handoff.
 */
import { host, type HermesPlugin, PALETTE_AREA, ROUTES_AREA, SIDEBAR_NAV_AREA, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useMemo } from 'react'
import {
  DashboardScreen,
  defaultRhythmTokens,
  RhythmGatewayError,
  RhythmWorkspaceProvider,
  TasksScreen,
  type RhythmDomainGateway,
  type RhythmHostAdapter,
  type RhythmScreenId,
  type RhythmTask,
} from '../vendor/rhythm-workspace-ui/dist/index.js'
import '../vendor/rhythm-workspace-ui/dist/styles/rhythm.css'

import { rhythmRouteTarget } from './route-state'

type Rest = PluginContext['rest']
type RestFailure = { statusCode?: unknown; status?: unknown; response?: { status?: unknown; statusCode?: unknown } }

const unavailable = () => Promise.reject(new RhythmGatewayError('unavailable', 'Rhythm is read-only in this Hermes release.'))
const unavailablePort = new Proxy({}, { get: () => unavailable })

function statusOf(error: unknown): number | undefined {
  const failure = error as RestFailure | undefined
  for (const value of [failure?.statusCode, failure?.status, failure?.response?.statusCode, failure?.response?.status]) {
    const status = typeof value === 'number' ? value : Number(value)
    if (Number.isInteger(status)) return status
  }
  return undefined
}

function gatewayError(error: unknown): RhythmGatewayError {
  if (error instanceof RhythmGatewayError) return error
  const status = statusOf(error)
  if (status === 401 || status === 403) return new RhythmGatewayError('forbidden', 'Rhythm access is restricted.')
  if (status === 404 || status === 502 || status === 503 || status === 504) return new RhythmGatewayError('unavailable', 'Rhythm is unavailable.')
  return new RhythmGatewayError('server_error', 'Rhythm could not load safely.')
}

function read<T>(rest: Rest, path: string): Promise<T> {
  return rest<T>(path).catch(error => Promise.reject(gatewayError(error)))
}

/** The only live port methods are pinned, namespaced GETs. Every write-shaped
 * accepted-package port rejects locally, so a future screen interaction cannot
 * silently turn this M4a slice into a mutation channel. */
function createGateway(rest: Rest): RhythmDomainGateway {
  return {
    dashboard: {
      summary: () => read(rest, '/dashboard-summary'),
      members: () => Promise.resolve([]),
      createTask: unavailable,
      updateTask: unavailable,
      updateProjectStep: unavailable,
    },
    tasks: {
      list: async () => (await read<{ tasks: RhythmTask[] }>(rest, '/tasks')).tasks,
      members: () => Promise.resolve([]),
      create: unavailable,
      update: unavailable,
      delete: unavailable,
      addCollaborator: unavailable,
      removeCollaborator: unavailable,
    },
    planner: unavailablePort,
    projects: unavailablePort,
    rhythms: unavailablePort,
    messages: unavailablePort,
    facilities: unavailablePort,
    integrations: unavailablePort,
    automations: unavailablePort,
  } as unknown as RhythmDomainGateway
}

function askHermes(context: { screen: string; label: string; action?: string; relatedId?: string }): void {
  // newChat stashes one editable draft; it never submits or creates an agent turn.
  host.newChat({
    prefill: `Help me with Rhythm: ${context.label}`.slice(0, 1_024),
    profile: host.state.profile.get(),
    source: { label: 'Rhythm', metadata: { screen: context.screen.slice(0, 64), action: (context.action ?? '').slice(0, 64), taskId: (context.relatedId ?? '').slice(0, 120) } },
  })
}

function RhythmWorkspace({ rest }: { rest: Rest }) {
  const profile = useValue(host.state.profile)
  const connectionId = useValue(host.state.connectionId) ?? 'local'
  const gatewayState = useValue(host.state.gateway)
  const target = rhythmRouteTarget(window.location.hash.split('?')[1] ? `?${window.location.hash.split('?')[1]}` : '')
  const tab = target.includes('tab=tasks') ? 'tasks' : 'overview'
  // A changed identity is a synchronous re-home: React unmounts old screen
  // state before the replacement gateway can publish, invalidating stale work.
  const generation = `${connectionId}:${profile}:${gatewayState}`
  const gateway = useMemo(() => createGateway(rest), [rest, generation])
  const adapter = useMemo<RhythmHostAdapter>(() => ({
    tokens: defaultRhythmTokens,
    viewport: 'expanded',
    currentUser: { displayName: 'Hermes', initials: 'H', collaborationCapability: 'read' },
    onNavigateToScreen: (screen: RhythmScreenId) => {
      if (screen === 'tasks') window.location.hash = rhythmRouteTarget('?tab=tasks')
    },
    onRequestFollowUp: askHermes,
  }), [])

  return <main className="rhythm-workspace-root" aria-label="Rhythm workspace" data-testid="rhythm-workspace-readonly" data-readonly="true">
    <RhythmWorkspaceProvider gateway={gateway} host={adapter} key={generation}>
      {tab === 'tasks' ? <TasksScreen /> : <DashboardScreen />}
    </RhythmWorkspaceProvider>
  </main>
}

const plugin: HermesPlugin = {
  id: 'rhythm', name: 'Rhythm', description: 'Rhythm workspace', defaultEnabled: false,
  register(ctx) {
    ctx.registerMany([
      { area: ROUTES_AREA, data: { path: '/rhythm' }, id: 'page', render: () => <RhythmWorkspace rest={ctx.rest} />, title: 'Rhythm' },
      { area: SIDEBAR_NAV_AREA, data: { codicon: 'pulse', label: 'Rhythm', path: '/rhythm' }, id: 'nav' },
      { area: PALETTE_AREA, data: { id: 'open-rhythm', label: 'Open Rhythm', keywords: ['rhythm', 'tasks', 'overview'], run: () => { window.location.hash = rhythmRouteTarget() } }, id: 'palette' },
    ])
  },
}

export { askHermes, createGateway, gatewayError }
export default plugin
