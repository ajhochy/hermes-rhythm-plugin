import { host as hermesHost } from '@hermes/plugin-sdk'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { askHermes, confirmationKey, createGateway, gatewayError } from '../../../../plugins/rhythm/desktop/src/plugin'
import {
  DashboardScreen,
  defaultRhythmTokens,
  type RhythmDomainGateway,
  type RhythmHostAdapter,
  RhythmWorkspaceProvider,
  TasksScreen,
} from '../../../../plugins/rhythm/desktop/vendor/rhythm-workspace-ui/dist/index.js'

const host: RhythmHostAdapter = {
  tokens: defaultRhythmTokens,
  viewport: 'expanded',
  currentUser: { displayName: 'Hermes', initials: 'H', collaborationCapability: 'read' },
}

const task = {
  id: 'task-1', title: 'Review brief', notes: 'Read the accepted artifact.', status: 'open' as const,
  bucket: 'today' as const, priority: 1 as const, tags: ['work'], createdAt: '2026-08-21',
  createdBy: 'Hermes', ownerId: 'H', isShared: false, sourceType: 'manual' as const,
  preferredAgent: '' as const, energy: '' as const, collaborators: [],
}

const summary = { openTaskCount: 1, threadCount: 0, tasks: [{ id: task.id, title: task.title, notes: task.notes, status: 'open' as const, bucket: 'today' as const, dueLabel: 'Today' }], project: null, unreadThreads: [] }

function renderScreen(screenNode: React.ReactNode, gateway: RhythmDomainGateway, adapter = host) {
  return render(<div className="rhythm-workspace-root" data-readonly="true"><RhythmWorkspaceProvider gateway={gateway} host={adapter}>{screenNode}</RhythmWorkspaceProvider></div>)
}

function restFor(value: unknown | Error) {
  const request = vi.fn(async (path: string) => {
    if (value instanceof Error) {throw value}

    if (path === '/dashboard-summary') {return summary}

    if (path === '/tasks') {return { tasks: [task] }}
    throw new Error(`unexpected GET ${path}`)
  })

  return request as unknown as Parameters<typeof createGateway>[0]
}

describe('accepted Rhythm workspace package', () => {
  it('mounts the actual Dashboard and Tasks screens read-only through their provider', async () => {
    const rest = restFor(summary)
    const gateway = createGateway(rest)
    const view = renderScreen(<DashboardScreen />, gateway)
    await screen.findByTestId('rhythm-dashboard-screen')
    expect(screen.getByText('Dashboard')).not.toBeNull()
    expect(view.container.querySelector('[data-readonly="true"]')).not.toBeNull()
    view.unmount()

    renderScreen(<TasksScreen />, gateway)
    expect(await screen.findByTestId('rhythm-tasks-screen')).not.toBeNull()
    expect(screen.getByText('Review brief')).not.toBeNull()
    expect((rest as unknown as { mock: { calls: Array<[string]> } }).mock.calls.map(([path]) => path)).toEqual(expect.arrayContaining(['/dashboard-summary', '/tasks']))
  })

  it.each([
    ['forbidden', { statusCode: 403 }],
    ['unavailable', { status: 503 }],
    ['server_error', { statusCode: 500 }],
  ])('maps the real bridge error shape to %s', (kind, shape) => {
    expect(gatewayError(shape).kind).toBe(kind)
  })

  it('maps accepted follow-up context to exactly one bounded unsent host draft', () => {
    const newChat = vi.spyOn(hermesHost, 'newChat').mockImplementation(() => undefined)
    askHermes({ screen: 'tasks', label: 'Help me finish this', action: 'help', relatedId: 'task-1' })
    expect(newChat).toHaveBeenCalledTimes(1)
    expect(newChat).toHaveBeenCalledWith(expect.objectContaining({
      prefill: 'Help me with Rhythm: Help me finish this',
      source: expect.objectContaining({ label: 'Rhythm', metadata: expect.objectContaining({ screen: 'tasks', taskId: 'task-1' }) }),
    }))
  })

  it('renders loading, empty, forbidden, unavailable, and error states from gateway behavior', async () => {
    let resolveSummary: (value: typeof summary) => void = () => undefined
    const pending = new Promise<typeof summary>(resolve => { resolveSummary = resolve })
    const deferredGateway = { ...createGateway(restFor(summary)), dashboard: { ...createGateway(restFor(summary)).dashboard, summary: () => pending, members: async () => [] } }
    const loading = renderScreen(<DashboardScreen />, deferredGateway)
    expect(screen.getByTestId('page-state-loading')).not.toBeNull()
    resolveSummary(summary)
    await screen.findByText('Dashboard')
    loading.unmount()

    for (const [expected, failure] of [
      ['page-state-empty', { openTaskCount: 0, threadCount: 0, tasks: [], project: null, unreadThreads: [] }],
      ['page-state-forbidden', new (class extends Error { statusCode = 403 })()],
      ['page-state-unavailable', new (class extends Error { status = 503 })()],
      ['page-state-server-error', new (class extends Error { statusCode = 500 })()],
    ] as const) {
      const rest = failure instanceof Error
        ? restFor(failure)
        : vi.fn(async (path: string) => path === '/dashboard-summary' ? failure : { tasks: [] }) as never

      const gateway = createGateway(rest)
      const view = renderScreen(<DashboardScreen />, gateway)
      await screen.findByTestId(expected)
      view.unmount()
    }
  })

  it('keeps detail failure local, sends one bounded Ask Hermes follow-up, and never invokes a mutation transport', async () => {
    const followUp = vi.fn()
    const rest = restFor(summary)
    const gateway = createGateway(rest)
    renderScreen(<DashboardScreen />, gateway, { ...host, onRequestFollowUp: followUp })
    await screen.findByTestId('quick-action-help-me-finish-this')
    fireEvent.click(screen.getByTestId('quick-action-help-me-finish-this'))
    expect(followUp).toHaveBeenCalledTimes(1)
    expect(followUp.mock.calls[0][0]).toMatchObject({ screen: 'dashboard', relatedId: 'task-1' })

    renderScreen(<TasksScreen />, gateway, { ...host, onRequestFollowUp: followUp })
    await screen.findByTestId('task-select-task-1')
    fireEvent.click(screen.getByTestId('task-select-task-1'))
    expect(await screen.findByTestId('task-inspector')).not.toBeNull()
    await expect(gateway.tasks.update('task-1', { status: 'done' })).rejects.toMatchObject({ kind: 'unavailable' })
    expect((rest as unknown as { mock: { calls: Array<[string]> } }).mock.calls.every(([path]) => ['/dashboard-summary', '/tasks'].includes(path))).toBe(true)
  })

  it('makes every visible Dashboard and Tasks mutation control inert without host write capabilities while preserving inspection and Ask Hermes', async () => {
    const rest = restFor(summary)
    const gateway = createGateway(rest)
    const followUp = vi.fn()
    const dashboard = renderScreen(<DashboardScreen />, gateway, { ...host, onRequestFollowUp: followUp })
    await screen.findByTestId('dashboard-header-add-task')
    for (const testId of ['dashboard-header-add-task', 'task-toggle-task-1']) {
      const control = screen.getByTestId(testId) as HTMLButtonElement
      expect(control.disabled).toBe(true)
      fireEvent.click(control)
    }

    fireEvent.click(screen.getByTestId('task-row-task-1'))
    expect(await screen.findByTestId('task-inspector')).not.toBeNull()

    for (const testId of ['task-inspector-title', 'task-inspector-notes', 'task-inspector-scheduled', 'task-inspector-due', 'task-inspector-save']) {
      expect((screen.getByTestId(testId) as HTMLInputElement | HTMLTextAreaElement | HTMLButtonElement).disabled).toBe(true)
    }

    fireEvent.click(screen.getByTestId('quick-action-help-me-finish-this'))
    expect(followUp).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('rhythm-dashboard-screen')).not.toBeNull()
    dashboard.unmount()

    const tasks = renderScreen(<TasksScreen />, gateway, { ...host, onRequestFollowUp: followUp })
    await screen.findByTestId('tasks-header-add-task')
    expect((screen.getByTestId('tasks-header-add-task') as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByTestId('task-complete-task-1') as HTMLInputElement).disabled).toBe(true)
    fireEvent.click(screen.getByTestId('tasks-header-add-task'))
    fireEvent.click(screen.getByTestId('task-complete-task-1'))
    fireEvent.click(screen.getByTestId('task-menu-task-1'))
    expect((await screen.findByTestId('task-delete-task-1') as HTMLButtonElement).disabled).toBe(true)

    fireEvent.click(screen.getByTestId('task-select-task-1'))

    for (const testId of ['task-edit-title', 'task-edit-notes', 'task-edit-scheduled-date', 'task-edit-due-date', 'task-edit-agent', 'task-edit-energy', 'task-detail-complete', 'task-save', 'task-add-collaborator']) {
      expect((screen.getByTestId(testId) as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement | HTMLButtonElement).disabled).toBe(true)
    }

    fireEvent.click(screen.getByTestId('quick-action-help-finish'))
    expect(followUp).toHaveBeenCalledTimes(2)
    expect(screen.getByTestId('rhythm-tasks-screen')).not.toBeNull()
    expect((rest as unknown as { mock: { calls: Array<[string]> } }).mock.calls.every(([path]) => ['/dashboard-summary', '/tasks'].includes(path))).toBe(true)
    tasks.unmount()
  })

  it('does not let a deferred old gateway publish after a provider re-home', async () => {
    let resolveOld: (value: typeof summary) => void = () => undefined
    const oldSummary = new Promise<typeof summary>(resolve => { resolveOld = resolve })
    const old = { ...createGateway(restFor(summary)), dashboard: { ...createGateway(restFor(summary)).dashboard, summary: () => oldSummary, members: async () => [] } }
    const fresh = createGateway(restFor(summary))
    const view = renderScreen(<DashboardScreen key="old" />, old)
    expect(screen.getByTestId('page-state-loading')).not.toBeNull()
    view.rerender(<div className="rhythm-workspace-root" data-readonly="true"><RhythmWorkspaceProvider gateway={fresh} host={host} key="new"><DashboardScreen /></RhythmWorkspaceProvider></div>)
    await screen.findAllByText('Review brief')
    resolveOld({ ...summary, tasks: [] })
    await waitFor(() => expect(screen.getAllByText('Review brief').length).toBeGreaterThan(0))
  })

  it('mounts the actual TasksScreen adapter: local confirm then one bound operation, with no token or broad writes', async () => {
    const confirmations = new Map<string, string>()
    const token = 'confirmation-secret-never-rendered'
    const rest = vi.fn(async (path: string, init?: { method: string, body: unknown }) => {
      if (path === '/tasks') return { tasks: [task] }
      if (path === '/tasks/task-1/confirmation') return { confirmation: token }
      if (path === '/tasks/task-1/operations') {
        expect(init).toMatchObject({ method: 'POST', body: { operation: 'complete', confirmation: token } })
        return { ...task, status: 'done' }
      }
      throw new Error(`unexpected route ${path}`)
    })
    const gateway = createGateway(rest as never, confirmations)
    const adapter: RhythmHostAdapter = {
      ...host,
      currentUser: { displayName: 'Hermes', initials: 'H', capabilities: ['tasks.complete', 'tasks.reschedule'] },
      confirmTaskOperation: async confirmation => {
        const receipt = await rest(`/tasks/${confirmation.taskId}/confirmation`, { method: 'POST', body: confirmation }) as { confirmation: string }
        confirmations.set(confirmationKey(confirmation), receipt.confirmation)
        return true
      },
    }
    const view = renderScreen(<TasksScreen />, gateway, adapter)
    await screen.findByTestId('task-complete-task-1')
    expect((screen.getByTestId('tasks-header-add-task') as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(screen.getByTestId('task-complete-task-1'))
    expect(rest.mock.calls.map(([path]) => path)).toEqual(['/tasks'])
    expect(screen.getByTestId('task-operation-confirmation')).not.toBeNull()
    fireEvent.click(screen.getByTestId('task-operation-confirm'))
    await waitFor(() => expect(rest.mock.calls.map(([path]) => path)).toEqual(['/tasks', '/tasks/task-1/confirmation', '/tasks/task-1/operations']))
    expect(view.container.textContent).not.toContain(token)
    await expect(gateway.tasks.complete?.('task-1', 'changed-generation')).rejects.toMatchObject({ kind: 'unavailable' })
    expect(confirmations.size).toBe(0)
    view.unmount()
  })
})
