import React, { useEffect, useState } from 'react'
import { Button, PALETTE_AREA, ROUTES_AREA, SIDEBAR_NAV_AREA, Select, SelectContent, SelectItem, SelectTrigger, SelectValue, host, useQuery } from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'

const text = value => String(value ?? '')
const get = (ctx, path) => ctx.rest(path, { method: 'GET' })
const list = value => Array.isArray(value) ? value : []
const githubPr = value => typeof value === 'string' && /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/pull\/[1-9][0-9]*$/.test(value)

function rows(title, items, render) {
  return jsxs('section', { 'aria-label': title, children: [jsx('h3', { children: title }), jsx('ul', { children: list(items).map((item, index) => jsx('li', { children: render(item) }, `${title}-${index}`)) })] })
}

export function renderRunDetail(detail, ctx) {
  const run = detail?.run
  if (!run) return null
  const pr = detail.handoff?.pr_url
  const openPr = () => { if (githubPr(pr)) ctx?.os?.openExternal?.(pr) }
  return jsxs('article', { 'aria-label': `Run ${run.id}`, children: [
    jsx('h2', { children: text(run.id) }),
    jsx('p', { children: `Active ${text(run.current_dispatch?.stage)} · ${text(run.current_dispatch?.profile)} · ${text(run.current_dispatch?.provider)} · ${text(run.current_dispatch?.model)} · task ${text(run.current_dispatch?.task_id)} · attempt ${text(run.current_dispatch?.attempt ?? run.attempt)}` }),
    jsx('p', { children: `Branch ${text(run.branch)} · base ${text(run.base_sha)} · candidate ${text(run.candidate_sha)}` }),
    detail.health?.stale && jsx('p', { role: 'status', children: 'Stale candidate: reviews or evidence may require renewal.' }),
    rows('Stages', detail.stages, stage => `${text(stage.id)}: ${text(stage.status)}${stage.profile ? ` · ${text(stage.profile)}` : ''}${stage.task_id ? ` · task ${text(stage.task_id)}` : ''}${stage.dispatch?.model ? ` · ${text(stage.dispatch.model)}` : ''}${list(stage.depends_on).length ? ` (after ${list(stage.depends_on).join(', ')})` : ''}`),
    rows('Reviews', detail.reviews, review => jsxs('span', { children: [`${text(review.reviewer?.profile)} · task ${text(review.reviewer?.task_id)}: ${text(review.decision)}`, jsx('ul', { children: list(review.findings).map((finding, index) => jsx('li', { children: `${text(finding.severity)} ${text(finding.description)} — ${text(finding.disposition)}` }, index)) })] })),
    rows('Attempts', detail.attempt_history, item => `Attempt ${text(item.attempt)}: ${text(item.status)}${item.summary ? ` — ${text(item.summary)}` : ''}`),
    rows('Blockers', detail.blockers, item => `${text(item.kind)}: ${text(item.summary)}`),
    rows('Evidence', detail.evidence, item => `${text(item.name)}: ${text(item.status)} — ${text(item.summary)}`),
    githubPr(pr) && jsx(Button, { type: 'button', onClick: openPr, 'aria-label': 'Open draft pull request', children: 'Draft PR' }),
    list(detail.artifacts).length > 0 && jsx('p', { children: `Local artifacts are available: ${list(detail.artifacts).map(item => text(item.label)).join(', ')}. They cannot be opened from this read-only view.` })
  ] })
}

export function CodingRunsPage({ ctx }) {
  const [board, setBoard] = useState('')
  const [selectedRun, setSelectedRun] = useState('')
  const boardQuery = useQuery({ queryKey: ['coding-runs', 'boards'], queryFn: () => get(ctx, '/boards'), refetchInterval: 5000 })
  const boards = list(boardQuery.data?.boards)
  useEffect(() => { if (!board && boards[0]?.id) setBoard(boards[0].id) }, [board, boards])
  useEffect(() => { setSelectedRun('') }, [board])
  const runsQuery = useQuery({ queryKey: ['coding-runs', 'runs', board], enabled: Boolean(board), queryFn: () => get(ctx, `/runs?board=${encodeURIComponent(board)}`), refetchInterval: 5000 })
  const detailQuery = useQuery({ queryKey: ['coding-runs', 'detail', board, selectedRun], enabled: Boolean(board && selectedRun), queryFn: () => get(ctx, `/runs/${encodeURIComponent(selectedRun)}?board=${encodeURIComponent(board)}`), refetchInterval: 5000 })
  if (boardQuery.isLoading || (board && runsQuery.isLoading)) return jsx('p', { role: 'status', children: 'Loading Coding Runs…' })
  if (boardQuery.isError || runsQuery.isError || detailQuery.isError) return jsx('p', { role: 'alert', children: 'Coding Runs could not be loaded. Polling will retry.' })
  if (!boards.length) return jsx('p', { children: 'No coding workflow boards are available.' })
  const runs = list(runsQuery.data?.runs)
  return jsxs('section', { 'aria-label': 'Coding Runs', 'data-theme-safe': 'native', children: [
    jsxs('label', { children: ['Board', jsx(Select, { value: board, onValueChange: setBoard, children: [jsx(SelectTrigger, { 'aria-label': 'Coding Runs board', children: jsx(SelectValue, { placeholder: 'Select a board' }) }), jsx(SelectContent, { children: boards.map(item => jsx(SelectItem, { value: item.id, children: text(item.label) }, item.id)) })] })] }),
    jsx('h2', { children: 'Runs' }),
    runs.length ? jsx('ul', { children: runs.map(item => jsx('li', { children: jsx(Button, { type: 'button', variant: 'ghost', onClick: () => setSelectedRun(item.id), 'aria-label': `Open run ${item.id}`, children: `${text(item.id)}: ${text(item.status)}` }) }, item.id)) }) : jsx('p', { children: 'No workflow runs are available for this board.' }),
    renderRunDetail(detailQuery.data, ctx)
  ] })
}

const plugin = { id: 'hermes-coding-workflow', name: 'Coding Runs', description: 'Read-only workflow run visibility.', defaultEnabled: false, register(ctx) {
  ctx.registerMany([
    { id: 'page', area: ROUTES_AREA, data: { path: '/coding-runs' }, render: () => jsx(CodingRunsPage, { ctx }) },
    { id: 'nav', area: SIDEBAR_NAV_AREA, data: { codicon: 'run-all', label: 'Coding Runs', path: '/coding-runs' } },
    { id: 'open', area: PALETTE_AREA, data: { id: 'coding-runs.open', label: 'Coding Runs: Open', keywords: ['coding', 'runs', 'workflow'], run: () => host.navigate('/coding-runs') } }
  ])
} }
export default plugin
