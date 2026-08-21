/**
 * Read-only host integration for the accepted @ajhochy/rhythm-workspace-ui
 * artifact, built from accepted source revision
 * 685ab24ed67b598109fd8b5fd85b1b8292e065b1 (see vendor provenance).
 * The package remains the owner of Dashboard/Tasks JSX and styles; this file
 * owns only the Hermes transport, lifecycle and bounded chat handoff.
 */
import { host, type HermesPlugin, PALETTE_AREA, ROUTES_AREA, SIDEBAR_NAV_AREA, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useMemo } from 'react'
import {
  DashboardScreen,
  AutomationsScreen,
  IntegrationsScreen,
  ArtifactsScreen,
  defaultRhythmTokens,
  RhythmGatewayError,
  RhythmWorkspaceProvider,
  TasksScreen,
  PlannerScreen,
  RhythmsScreen,
  ProjectsScreen,
  type RhythmDomainGateway,
  type RhythmHostAdapter,
  type RhythmProject,
  type RhythmProjectTemplate,
  type RhythmRhythm,
  type RhythmScreenId,
  type RhythmTask,
  type RhythmTaskOperationConfirmation,
  type RhythmWorkspaceOperationConfirmation,
  type ArtifactHostCapabilityResult,
  type ArtifactHostDocument,
  type ArtifactHostPort,
} from '../vendor/rhythm-workspace-ui/dist/index.js'
import '../vendor/rhythm-workspace-ui/dist/styles/rhythm.css'

import { rhythmRouteTarget } from './route-state'

type Rest = PluginContext['rest']
type RestFailure = { statusCode?: unknown; status?: unknown; detail?: unknown; body?: unknown; response?: { status?: unknown; statusCode?: unknown; detail?: unknown; body?: unknown; data?: unknown } }

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

function knownOperationOutcome(error: unknown): 'conflict' | 'uncertain' | undefined {
  const parse = (value: unknown): unknown => {
    if (typeof value !== 'string' || value.length > 512) return value
    try { return JSON.parse(value) } catch { return undefined }
  }
  const queue: unknown[] = [error]
  for (let index = 0; index < queue.length && index < 12; index += 1) {
    const value = parse(queue[index])
    if (!value || typeof value !== 'object' || Array.isArray(value)) continue
    const record = value as Record<string, unknown>
    if (record.error === 'conflict' || record.error === 'uncertain') return record.error
    queue.push(record.detail, record.body, record.data, record.response)
  }
  return undefined
}

function gatewayError(error: unknown): RhythmGatewayError {
  if (error instanceof RhythmGatewayError) return error
  const outcome = knownOperationOutcome(error)
  if (outcome === 'conflict') return new RhythmGatewayError('conflict', 'Rhythm changed elsewhere. Reload and retry the task operation.')
  if (outcome === 'uncertain') return new RhythmGatewayError('uncertain', 'Rhythm could not verify the task operation. Reload before retrying.')
  const status = statusOf(error)
  if (status === 401 || status === 403) return new RhythmGatewayError('forbidden', 'Rhythm access is restricted.')
  if (status === 409) return new RhythmGatewayError('conflict', 'Rhythm changed elsewhere. Reload and retry the task operation.')
  if (status === 404 || status === 502 || status === 503 || status === 504) return new RhythmGatewayError('unavailable', 'Rhythm is unavailable.')
  return new RhythmGatewayError('server_error', 'Rhythm could not load safely.')
}

function read<T>(rest: Rest, path: string): Promise<T> {
  return rest<T>(path).catch(error => Promise.reject(gatewayError(error)))
}

/** The only live port methods are pinned, namespaced GETs. Every write-shaped
 * accepted-package port rejects locally, so a future screen interaction cannot
 * silently turn this M4a slice into a mutation channel. */
function write<T>(rest: Rest, path: string, body: unknown): Promise<T> {
  return (rest as unknown as (path: string, init: { method: string; body: unknown }) => Promise<T>)(path, { method: 'POST', body }).catch(error => Promise.reject(gatewayError(error)))
}

/** The artifact document is a server-sanitized value, not a URL or transport.
 * The capability endpoint is local-only and returns conflict generations
 * unchanged so independent artifact/state concurrency remains visible. */
function createArtifactHostPort(rest: Rest): ArtifactHostPort {
  return {
    open: artifactId => read<ArtifactHostDocument>(rest, `/artifacts/${encodeURIComponent(artifactId)}/document`),
    receive: message => write<ArtifactHostCapabilityResult>(rest, `/artifacts/${encodeURIComponent(message.artifactId)}/capability`, message),
  }
}

function confirmationKey(confirmation: RhythmTaskOperationConfirmation | RhythmWorkspaceOperationConfirmation): string {
  if ('taskId' in confirmation) return JSON.stringify([confirmation.taskId, confirmation.operation, confirmation.scheduledDate ?? null, confirmation.generation])
  return JSON.stringify([confirmation.entityId, confirmation.operation, confirmation.payload, confirmation.generation])
}

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>
    return `{${Object.keys(record).sort().map(key => `${JSON.stringify(key)}:${canonicalJson(record[key])}`).join(',')}}`
  }
  return JSON.stringify(value)
}

function workspaceKey(operation: string, entityId: string, payload: Record<string, unknown>): string {
  return canonicalJson([operation, entityId, payload])
}

interface WorkspaceReceipt { receipt: string; generation: string }
type ConfirmationReceipt = string | WorkspaceReceipt

function createGateway(rest: Rest, confirmations = new Map<string, ConfirmationReceipt>()): RhythmDomainGateway {
  async function workspaceOperation<T>(operation: string, entityId: string, payload: Record<string, unknown>): Promise<T> {
    const key = workspaceKey(operation, entityId, payload)
    const bound = confirmations.get(key)
    if (!bound || typeof bound === 'string') return unavailable()
    confirmations.delete(key)
    return write<T>(rest, '/workspace-operations', { operation, entityId, payload, generation: bound.generation, confirmation: bound.receipt })
  }
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
      complete: async (id: string, generation?: string) => {
        const request = { taskId: id, operation: 'complete' as const, generation: generation ?? '' }
        const confirmation = confirmations.get(confirmationKey(request))
        if (!confirmation || typeof confirmation !== 'string') return unavailable()
        confirmations.delete(confirmationKey(request))
        return write<RhythmTask>(rest, `/tasks/${id}/operations`, { operation: 'complete', generation: request.generation, confirmation })
      },
      reschedule: async (id: string, scheduledDate: string, generation?: string) => {
        const request = { taskId: id, operation: 'reschedule' as const, scheduledDate, generation: generation ?? '' }
        const confirmation = confirmations.get(confirmationKey(request))
        if (!confirmation || typeof confirmation !== 'string') return unavailable()
        confirmations.delete(confirmationKey(request))
        return write<RhythmTask>(rest, `/tasks/${id}/operations`, { operation: 'reschedule', scheduledDate, generation: request.generation, confirmation })
      },
    },
    planner: {
      week: (weekStart: string) => read(rest, `/planner/weeks/${encodeURIComponent(weekStart)}`), members: () => Promise.resolve([]),
      scheduleTask: (id: string, input: Record<string, unknown>) => workspaceOperation('planner.schedule-task', id, input),
      update: (id: string, input: Record<string, unknown>) => workspaceOperation('planner.update-task', id, input),
      updateProjectStep: (id: string, input: Record<string, unknown>) => workspaceOperation('planner.update-project-step', id, input),
      scheduleProjectStep: (id: string, input: Record<string, unknown>) => workspaceOperation('planner.schedule-project-step', id, input),
      create: unavailable, addCollaborator: unavailable, removeCollaborator: unavailable,
    },
    rhythms: {
      list: async () => (await read<{ items: RhythmRhythm[] }>(rest, '/rhythm-rules')).items, members: () => Promise.resolve([]),
      create: (input: Record<string, unknown>) => workspaceOperation('rhythms.create-rule', 'new-rule', input),
      update: (id: string, input: Record<string, unknown>) => workspaceOperation('rhythms.update-rule', id, input),
      delete: (id: string) => workspaceOperation('rhythms.delete-rule', id, {}),
      addStep: (id: string, input: Record<string, unknown>) => workspaceOperation('rhythms.create-step', id, input),
      replaceSteps: (id: string, steps: unknown[]) => workspaceOperation('rhythms.update-step', id, { steps }),
      addCollaborator: unavailable, removeCollaborator: unavailable,
    },
    projects: {
      templates: async () => (await read<{ items: RhythmProjectTemplate[] }>(rest, '/project-templates')).items,
      list: async () => (await read<{ items: RhythmProject[] }>(rest, '/project-instances')).items,
      members: () => Promise.resolve([]),
      generate: (id: string, input: Record<string, unknown>) => workspaceOperation('projects.create-instance', id, input),
      createTemplate: (input: Record<string, unknown>) => workspaceOperation('projects.create-template', 'new-template', input),
      updateTemplate: (id: string, input: Record<string, unknown>) => workspaceOperation('projects.update-template', id, input),
      deleteTemplate: (id: string) => workspaceOperation('projects.delete-template', id, {}),
      addTemplateStep: (id: string, input: Record<string, unknown>) => workspaceOperation('projects.create-step', id, input),
      updateTemplateStep: (_templateId: string, stepId: string, input: Record<string, unknown>) => workspaceOperation('projects.update-template-step', stepId, input),
      deleteTemplateStep: (templateId: string, stepId: string) => workspaceOperation('projects.delete-step', stepId, { templateId }),
      // Instance deletion has no M5 semantic grant or server operation.
      delete: unavailable,
      updateStep: (_instanceId: string, stepId: string, input: Record<string, unknown>) => workspaceOperation('projects.update-step', stepId, input),
      addMilestone: (id: string, input: Record<string, unknown>) => workspaceOperation('projects.create-milestone', id, input),
      addCollaborator: unavailable, removeCollaborator: unavailable,
    },
    messages: unavailablePort,
    facilities: unavailablePort,
    integrations: {
      accounts: async () => (await read<{ accounts?: unknown[] }>(rest, '/integrations/status')).accounts ?? [],
      calendarSources: async () => (await read<{ calendarSources?: unknown[] }>(rest, '/integrations/settings')).calendarSources ?? [],
      gmailSignals: async () => [],
      // This named sync port is a classified GET status refresh; controls stay
      // disabled because Hermes grants no integrations.write capability.
      sync: async (id: string) => {
        const response = await read<{ accounts?: Array<{ id: string }> }>(rest, '/integrations/sync')
        const account = response.accounts?.find(candidate => candidate.id === id)
        if (!account) return unavailable()
        return account
      },
      saveCalendarSelection: unavailable,
      disconnect: unavailable,
      requestAuthorization: () => undefined,
    },
    automations: {
      list: async () => (await read<{ items?: unknown[] }>(rest, '/automations/rules')).items ?? [],
      catalog: () => read(rest, '/automations/catalog'),
      preview: (id: string) => read(rest, `/automations/rules/${encodeURIComponent(id)}/preview`),
      create: unavailable, update: unavailable, delete: unavailable,
    },
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
  const tab = (['tasks', 'planner', 'rhythms', 'projects', 'automations', 'integrations', 'artifacts'] as const).find(candidate => target.includes(`tab=${candidate}`)) ?? 'overview'
  // A changed identity is a synchronous re-home: React unmounts old screen
  // state before the replacement gateway can publish, invalidating stale work.
  const generation = `${connectionId}:${profile}:${gatewayState}`
  const confirmations = useMemo(() => new Map<string, ConfirmationReceipt>(), [generation])
  const gateway = useMemo(() => createGateway(rest, confirmations), [rest, confirmations])
  const artifactHostPort = useMemo(() => createArtifactHostPort(rest), [rest])
  const adapter = useMemo<RhythmHostAdapter>(() => ({
    tokens: defaultRhythmTokens,
    viewport: 'expanded',
    // M5 grants are semantic and receipt-bound.  The renderer never receives a
    // bearer token, URL, workspace, or user identity.
    currentUser: { id: 'current-user', displayName: 'Hermes', initials: 'H', collaborationCapability: 'read', capabilities: ['planner.schedule-task', 'planner.update-task', 'planner.update-project-step', 'planner.schedule-project-step', 'rhythms.create-rule', 'rhythms.update-rule', 'rhythms.delete-rule', 'rhythms.create-step', 'rhythms.update-step', 'projects.create-template', 'projects.update-template', 'projects.delete-template', 'projects.create-instance', 'projects.update-step', 'projects.update-template-step', 'projects.create-step', 'projects.delete-step', 'projects.create-milestone'] },
    confirmTaskOperation: async (confirmation: RhythmTaskOperationConfirmation) => {
      const payload = await write<{ confirmation: string }>(rest, `/tasks/${confirmation.taskId}/confirmation`, { ...confirmation })
      confirmations.set(confirmationKey(confirmation), payload.confirmation)
      return true
    },
    confirmWorkspaceOperation: async (confirmation: RhythmWorkspaceOperationConfirmation) => {
      const payload = await write<{ confirmation: string }>(rest, '/workspace-operations/confirmation', confirmation)
      confirmations.set(workspaceKey(confirmation.operation, confirmation.entityId, confirmation.payload), { receipt: payload.confirmation, generation: confirmation.generation })
      return true
    },
    onNavigateToScreen: (screen: RhythmScreenId) => {
      if (['tasks', 'planner', 'rhythms', 'projects', 'automations', 'integrations', 'artifacts'].includes(screen)) window.location.hash = rhythmRouteTarget(`?tab=${screen}`)
    },
    onRequestFollowUp: askHermes,
  }), [confirmations, rest])

  return <main className="rhythm-workspace-root" aria-label="Rhythm workspace" data-testid="rhythm-workspace-readonly" data-readonly="false">
    <RhythmWorkspaceProvider gateway={gateway} host={adapter} key={generation}>
      {tab === 'tasks' ? <TasksScreen /> : tab === 'planner' ? <PlannerScreen /> : tab === 'rhythms' ? <RhythmsScreen /> : tab === 'projects' ? <ProjectsScreen /> : tab === 'automations' ? <AutomationsScreen /> : tab === 'integrations' ? <IntegrationsScreen /> : tab === 'artifacts' ? <ArtifactsScreen artifactsGateway={{ list: async () => (await read<{ items?: Array<{ id: string; title: string; kind: 'document' | 'image' | 'other' }> }>(rest, '/artifacts')).items ?? [] }} artifactHostPort={artifactHostPort} /> : <DashboardScreen />}
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

export { askHermes, confirmationKey, createArtifactHostPort, createGateway, gatewayError, workspaceKey }
export default plugin
