const TABS = new Set(['overview', 'tasks'])
const WORKSPACE = /^[A-Za-z0-9_-]{1,64}$/

/** Return the only canonical Rhythm deep link. Unknown keys, invalid enum
 * values, and unsafe workspace ids are dropped rather than echoed into the
 * router. This keeps refresh/back links shareable without making query state
 * a second routing surface. */
export function rhythmRouteTarget(search = ''): string {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
  const next = new URLSearchParams()
  const tab = params.get('tab')
  const workspace = params.get('workspace')

  if (tab && TABS.has(tab)) next.set('tab', tab)
  if (workspace && WORKSPACE.test(workspace)) next.set('workspace', workspace)

  const query = next.toString()
  return query ? `/rhythm?${query}` : '/rhythm'
}
