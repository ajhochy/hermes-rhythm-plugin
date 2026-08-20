import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = await readFile(new URL('../../desktop/plugin.js', import.meta.url), 'utf8')
const data = value => `data:text/javascript;base64,${Buffer.from(value).toString('base64')}`
// These are the exact public names exposed by Hermes Desktop's disk-plugin SDK.
const react = data(`export default {}; export const useEffect = fn => fn(); export const useState = value => [value, () => {}];`)
const jsx = data(`export const jsx=(type,props)=>({type,props}); export const jsxs=jsx;`)
const sdk = data(`export const PALETTE_AREA='palette'; export const ROUTES_AREA='routes'; export const SIDEBAR_NAV_AREA='nav'; export const Button='Button'; export const Select='Select'; export const SelectContent='SelectContent'; export const SelectItem='SelectItem'; export const SelectTrigger='SelectTrigger'; export const SelectValue='SelectValue'; export const host={navigate:()=>{}}; export const useQuery=({queryKey})=>globalThis.__queries?.[queryKey.join('|')] ?? {data:{}};`)

async function loadPlugin() {
  const rewritten = source.replace("'@hermes/plugin-sdk'", `'${sdk}'`).replace("'react'", `'${react}'`).replace("'react/jsx-runtime'", `'${jsx}'`)
  return (await import(data(rewritten))).default
}

function text(tree) {
  if (tree == null || typeof tree === 'boolean') return ''
  if (typeof tree === 'string' || typeof tree === 'number') return String(tree)
  const children = tree?.props?.children
  return Array.isArray(children) ? children.map(text).join(' ') : text(children)
}

function find(tree, predicate) {
  if (!tree || typeof tree !== 'object') return null
  if (predicate(tree)) return tree
  const children = tree?.props?.children
  for (const child of Array.isArray(children) ? children : [children]) {
    const result = find(child, predicate)
    if (result) return result
  }
  return null
}

test('production ESM registers the current Hermes SDK route, sidebar, and palette controls', async () => {
  const plugin = await loadPlugin()
  assert.deepEqual([...source.matchAll(/from '([^']+)'/g)].map(match => match[1]), ['react', '@hermes/plugin-sdk', 'react/jsx-runtime'])
  const batches = []
  plugin.register({ registerMany: entries => batches.push(entries) })
  assert.equal(plugin.id, 'hermes-coding-workflow')
  assert.deepEqual(batches[0].map(entry => [entry.area, entry.data.path ?? entry.data.id]), [['routes', '/coding-runs'], ['nav', '/coding-runs'], ['palette', 'coding-runs.open']])
  assert.equal(typeof batches[0][0].render, 'function')
  assert.doesNotMatch(source, /(?:POST|PUT|PATCH|DELETE|fetch\()/)
})

test('detail renderer exposes authoritative dispatches and service-shaped reviews without raw paths or mutation controls', async () => {
  const { renderRunDetail } = await import(data(source.replace("'@hermes/plugin-sdk'", `'${sdk}'`).replace("'react'", `'${react}'`).replace("'react/jsx-runtime'", `'${jsx}'`)))
  const tree = renderRunDetail({ run: { id: 'run-1', attempt: 2, current_dispatch: { stage: 'green', profile: 'terra', provider: 'hermes', model: 'gpt-5', task_id: 'task-green', attempt: 2 }, branch: 'feat/x', base_sha: 'a'.repeat(40), candidate_sha: 'b'.repeat(40) }, stages: [{ id: 'build', status: 'blocked', task_id: 'task-build', profile: 'terra', dispatch: { model: 'gpt-5' }, depends_on: ['red'] }], reviews: [{ reviewer: { profile: 'dev-spec', task_id: 'task-spec' }, decision: 'changes_requested', findings: [{ severity: 'blocker', description: 'Needs test', disposition: 'accepted' }] }], evidence: [{ name: 'verification', status: 'pass', summary: '12 passed' }], blockers: [{ kind: 'review', summary: 'Needs test' }], attempt_history: [{ attempt: 1, status: 'rejected' }], health: { stale: true, status: 'stale' }, handoff: { pr_url: 'https://github.com/acme/repo/pull/1' }, artifacts: [{ id: 'handoff', label: 'Handoff' }] })
  const rendered = text(tree)
  for (const expected of ['run-1', 'Active green', 'terra', 'gpt-5', 'feat/x', 'Stages', 'Reviews', 'Needs test', 'Attempts', 'Blockers', 'Evidence', 'Stale candidate', 'Draft PR', 'Local artifacts are available']) assert.match(rendered, new RegExp(expected))
  assert.doesNotMatch(rendered, /\/Users\/|secret|prompt|transcript/i)
  let opened = false
  const unsafe = renderRunDetail({ run: { id: 'run-2' }, handoff: { pr_url: 'https://github.com.evil.invalid/acme/repo/pull/1' } }, { os: { openExternal: () => { opened = true } } })
  assert.equal(find(unsafe, node => node.props?.['aria-label'] === 'Open draft pull request'), null)
  assert.equal(opened, false)
})

test('page uses keyed list/detail polling, reset on board change, and native accessible controls', async () => {
  const plugin = await loadPlugin(); const entries = []; plugin.register({ registerMany: value => entries.push(...value) })
  const Page = entries.find(entry => entry.id === 'page').render().type
  globalThis.__queries = { 'coding-runs|boards': { data: { boards: [] } } }
  assert.match(text(Page({ ctx: { rest: () => Promise.resolve({}) } })), /No coding workflow boards/)
  globalThis.__queries = { 'coding-runs|boards': { isError: true, data: {} } }
  assert.match(text(Page({ ctx: { rest: () => Promise.resolve({}) } })), /could not be loaded/)
  assert.match(source, /\['coding-runs', 'detail', board, selectedRun\]/)
  assert.match(source, /refetchInterval: 5000/)
  assert.match(source, /setSelectedRun\(''\)/)
  assert.match(source, /data-theme-safe/)
})
