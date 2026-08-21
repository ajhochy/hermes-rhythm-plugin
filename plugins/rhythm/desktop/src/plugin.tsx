import { type HermesPlugin, PALETTE_AREA, ROUTES_AREA, SIDEBAR_NAV_AREA } from '@hermes/plugin-sdk'

import { rhythmRouteTarget } from './route-state'

function RhythmShell() {
  const target = rhythmRouteTarget(window.location.hash.split('?')[1] ? `?${window.location.hash.split('?')[1]}` : '')
  const params = new URLSearchParams(target.split('?')[1] ?? '')
  const tab = params.get('tab') ?? 'overview'

  return (
    <main className="rhythm-shell" aria-label="Rhythm">
      <h1>Rhythm</h1>
      <p>{tab === 'tasks' ? 'Tasks' : 'Overview'}</p>
    </main>
  )
}

const plugin: HermesPlugin = {
  id: 'rhythm',
  name: 'Rhythm',
  description: 'Rhythm workspace',
  defaultEnabled: false,
  register(ctx) {
    ctx.css('.rhythm-shell { height: 100%; overflow: auto; padding: 2rem; }')
    ctx.registerMany([
      {
        area: ROUTES_AREA,
        data: { path: '/rhythm' },
        id: 'page',
        render: () => <RhythmShell />,
        title: 'Rhythm'
      },
      {
        area: SIDEBAR_NAV_AREA,
        data: { codicon: 'pulse', label: 'Rhythm', path: '/rhythm' },
        id: 'nav'
      },
      {
        area: PALETTE_AREA,
        data: {
          id: 'open-rhythm',
          label: 'Open Rhythm',
          keywords: ['rhythm', 'tasks', 'overview'],
          run: () => {
            window.location.hash = rhythmRouteTarget()
          }
        },
        id: 'palette'
      }
    ])
  }
}

export default plugin
