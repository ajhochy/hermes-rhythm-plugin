/**
 * Read-only host integration for the accepted rhythm-workspace-ui visual
 * language (bc7626ea).  The host owns routing, transport and chat drafts;
 * this plugin deliberately owns neither credentials nor mutation verbs.
 */
import { host, type HermesPlugin, PALETTE_AREA, ROUTES_AREA, SIDEBAR_NAV_AREA, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useEffect, useRef, useState } from 'react'

import { rhythmRouteTarget } from './route-state'

interface Identity { id: string; email?: string }
interface Workspace { id: string; name?: string }
interface SummaryTask { id: string; title: string; notes: string; status: 'open' | 'done'; bucket: string; dueLabel: string }
interface DashboardSummary { identity: Identity; workspace: Workspace; openTaskCount: number; threadCount: number; tasks: SummaryTask[]; project: null; unreadThreads: [] }
interface Task { id: string; title: string; notes: string; status: string; bucket: string; priority: number; tags: string[]; dueDate?: string; scheduledDate?: string; createdAt: string; createdBy: string; sourceName?: string }
type Rest = PluginContext['rest']
type Surface = 'loading' | 'ready' | 'empty' | 'forbidden' | 'unavailable' | 'error'

function errorSurface(error: unknown): Surface {
  const status = Number((error as { status?: number })?.status)
  if (status === 401 || status === 403) return 'forbidden'
  if (status === 404 || status === 502 || status === 504) return 'unavailable'
  return 'error'
}

function StatePanel({ state, retry }: { state: Exclude<Surface, 'ready'>; retry(): void }) {
  const copy = {
    loading: ['Loading Rhythm…', 'Refreshing the workspace summary and task queue.'],
    empty: ['Nothing planned yet', 'This connected workspace has no visible tasks.'],
    forbidden: ['Rhythm access is restricted', 'Reconnect with a workspace account that can view planning data.'],
    unavailable: ['Rhythm is unavailable', 'The connected service could not be reached.'],
    error: ['Could not load Rhythm', 'The service returned data we could not safely display.']
  }[state]
  return <section className="rhythm-state" role={state === 'error' || state === 'forbidden' ? 'alert' : 'status'} data-testid={`rhythm-state-${state}`}><h2>{copy[0]}</h2><p>{copy[1]}</p>{['unavailable', 'error'].includes(state) && <button type="button" onClick={retry}>Retry</button>}</section>
}

function askHermes(task: { id: string; title: string }, workspace: Workspace) {
  // host.newChat only stashes an editable draft. It never submits a prompt.
  host.newChat({
    prefill: `Help me think through the Rhythm task: ${task.title}`,
    profile: host.state.profile.get(),
    source: { label: 'Rhythm task', metadata: { taskId: task.id, workspaceId: workspace.id, workspace: workspace.name ?? '' } }
  })
}

function RhythmShell({ rest }: { rest: Rest }) {
  const profile = useValue(host.state.profile)
  const target = rhythmRouteTarget(window.location.hash.split('?')[1] ? `?${window.location.hash.split('?')[1]}` : '')
  const [tab, setTab] = useState<'overview' | 'tasks'>(target.includes('tab=tasks') ? 'tasks' : 'overview')
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [tasks, setTasks] = useState<Task[]>([])
  const [selected, setSelected] = useState<Task | null>(null)
  const [surface, setSurface] = useState<Surface>('loading')
  const request = useRef(0)

  const load = async () => {
    const generation = ++request.current
    setSurface('loading')
    try {
      const [nextSummary, nextTasks] = await Promise.all([rest<DashboardSummary>('/dashboard-summary'), rest<{ tasks: Task[] }>('/tasks')])
      if (generation !== request.current) return
      setSummary(nextSummary)
      setTasks(nextTasks.tasks)
      setSurface(nextTasks.tasks.length || nextSummary.tasks.length ? 'ready' : 'empty')
    } catch (error) {
      if (generation === request.current) setSurface(errorSurface(error))
    }
  }

  useEffect(() => { void load(); return () => { request.current += 1 } }, [rest, profile])
  const select = async (id: string) => {
    const generation = ++request.current
    try {
      const detail = await rest<Task>(`/tasks/${encodeURIComponent(id)}`)
      if (generation === request.current) setSelected(detail)
    } catch (error) { if (generation === request.current) setSurface(errorSurface(error)) }
  }
  const switchTab = (next: 'overview' | 'tasks') => { setTab(next); window.location.hash = rhythmRouteTarget(`?tab=${next}`) }

  return <main className="rhythm-shell rhythm-workspace-root" aria-label="Rhythm workspace" data-testid="rhythm-workspace-readonly" data-readonly="true">
    <header className="rhythm-header"><div><span>CONNECTED WORKSPACE</span><h1>{summary?.workspace.name ?? 'Rhythm'}</h1></div><strong>Read-only</strong></header>
    <nav aria-label="Rhythm sections"><button type="button" aria-pressed={tab === 'overview'} onClick={() => switchTab('overview')}>Dashboard</button><button type="button" aria-pressed={tab === 'tasks'} onClick={() => switchTab('tasks')}>Tasks</button></nav>
    {surface !== 'ready' ? <StatePanel state={surface} retry={() => void load()} /> : tab === 'overview' ? <section className="rhythm-dashboard" data-testid="rhythm-dashboard"><div className="rhythm-metrics"><p><strong>{summary!.openTaskCount}</strong> open tasks</p><p><strong>{summary!.threadCount}</strong> unread threads</p></div><h2>Today’s focus</h2><div className="rhythm-task-list">{summary!.tasks.map(task => <article key={task.id}><button type="button" onClick={() => { switchTab('tasks'); void select(task.id) }}><strong>{task.title}</strong><span>{task.dueLabel}</span></button></article>)}</div></section> : <section className="rhythm-tasks" data-testid="rhythm-tasks"><p className="rhythm-readonly-notice">Tasks are inspect-only in this Hermes release.</p><div className="rhythm-task-list">{tasks.map(task => <article key={task.id}><button type="button" onClick={() => void select(task.id)}><strong>{task.title}</strong><span>{task.status} · {task.dueDate ?? task.scheduledDate ?? 'No date'}</span></button></article>)}</div>{selected && <aside aria-label="Task detail" data-testid="rhythm-task-detail"><button type="button" onClick={() => setSelected(null)}>Close</button><p>{selected.status}</p><h2>{selected.title}</h2><p>{selected.notes || 'No notes provided.'}</p><dl><dt>Created by</dt><dd>{selected.createdBy}</dd><dt>Source</dt><dd>{selected.sourceName ?? 'Rhythm task'}</dd></dl><button type="button" onClick={() => askHermes(selected, summary!.workspace)} data-testid="rhythm-ask-hermes">Ask Hermes</button></aside>}</section>}
  </main>
}

const CSS = `.rhythm-shell{height:100%;overflow:auto;padding:2rem;background:var(--background,#171a1b);color:var(--foreground,#f3f6f5);font:14px system-ui}.rhythm-header,.rhythm-header div,.rhythm-task-list article button{display:flex;gap:1rem}.rhythm-header{justify-content:space-between;align-items:start;border-bottom:1px solid #40504d;padding-bottom:1rem}.rhythm-header div{display:block}.rhythm-header span,.rhythm-readonly-notice{color:#9fb0ad;font-size:.75rem;letter-spacing:.08em}.rhythm-shell nav{display:flex;gap:.5rem;margin:1rem 0}.rhythm-shell button{background:#26312f;color:inherit;border:1px solid #4d6260;border-radius:.5rem;padding:.55rem .75rem;cursor:pointer}.rhythm-shell button[aria-pressed=true]{background:#4fb8a0;color:#0c1716}.rhythm-state,.rhythm-tasks,.rhythm-dashboard{max-width:54rem;padding:1.25rem;border:1px solid #33403e;border-radius:1rem}.rhythm-metrics{display:flex;gap:1rem}.rhythm-metrics p{padding:1rem;background:#1f2426;border-radius:.75rem}.rhythm-metrics strong{font-size:1.5rem}.rhythm-task-list{display:grid;gap:.5rem}.rhythm-task-list article button{width:100%;justify-content:space-between;text-align:left}.rhythm-task-list span{color:#9fb0ad}.rhythm-tasks{display:grid;grid-template-columns:minmax(0,1fr) minmax(18rem,24rem);gap:1rem}.rhythm-tasks .rhythm-readonly-notice{grid-column:1/-1}.rhythm-tasks aside{border-left:1px solid #40504d;padding-left:1rem}.rhythm-tasks dt{color:#9fb0ad}@media(max-width:700px){.rhythm-tasks{grid-template-columns:1fr}.rhythm-tasks aside{border-left:0;border-top:1px solid #40504d;padding:1rem 0}}`

const plugin: HermesPlugin = { id: 'rhythm', name: 'Rhythm', description: 'Rhythm workspace', defaultEnabled: false, register(ctx) { ctx.css(CSS); ctx.registerMany([{ area: ROUTES_AREA, data: { path: '/rhythm' }, id: 'page', render: () => <RhythmShell rest={ctx.rest} />, title: 'Rhythm' }, { area: SIDEBAR_NAV_AREA, data: { codicon: 'pulse', label: 'Rhythm', path: '/rhythm' }, id: 'nav' }, { area: PALETTE_AREA, data: { id: 'open-rhythm', label: 'Open Rhythm', keywords: ['rhythm', 'tasks', 'overview'], run: () => { window.location.hash = rhythmRouteTarget() } }, id: 'palette' }]) } }

export default plugin
