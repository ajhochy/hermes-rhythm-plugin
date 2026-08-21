import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setApiRequestConnection, setApiRequestProfile } from './client'
import { pluginRest } from './plugins'

describe('pluginRest explicit route pinning', () => {
  const api = vi.fn(async (request: unknown) => request)

  beforeEach(() => {
    ;(window as unknown as { hermesDesktop: unknown }).hermesDesktop = { api }
    setApiRequestConnection('ambient-a')
    setApiRequestProfile('ambient-profile')
    api.mockClear()
  })

  afterEach(() => {
    delete (window as unknown as { hermesDesktop?: unknown }).hermesDesktop
    setApiRequestConnection(null)
    setApiRequestProfile(null)
  })

  it('keeps a designated plugin request on its original backend after ambient profile switches', async () => {
    const route = {
      connectionId: 'rhythm-backend',
      mode: 'remote' as const,
      profile: 'rhythm',
      targetProfile: 'rhythm',
      token: 'electron-issued-route-token'
    }

    await pluginRest('rhythm', '/tasks', { route })
    setApiRequestConnection('different-backend')
    setApiRequestProfile('different-profile')
    await pluginRest('rhythm', '/tasks', { route })

    expect(api.mock.calls.map(([request]) => request)).toEqual([
      {
        connectionId: 'rhythm-backend',
        path: '/api/plugins/rhythm/tasks',
        pluginRoute: route,
        profile: 'rhythm'
      },
      {
        connectionId: 'rhythm-backend',
        path: '/api/plugins/rhythm/tasks',
        pluginRoute: route,
        profile: 'rhythm'
      }
    ])
  })

  it('fails closed rather than falling back when the designated route is malformed', async () => {
    await expect(pluginRest('rhythm', '/tasks', { route: { connectionId: '', profile: 'rhythm' } as never })).rejects.toThrow(
      /valid route descriptor/i
    )
    expect(api).not.toHaveBeenCalled()
  })

  it('fails closed before the Electron API bridge when a route has no Electron-issued token', async () => {
    await expect(
      pluginRest('rhythm', '/tasks', {
        route: { connectionId: 'rhythm-backend', mode: 'remote', profile: 'rhythm', targetProfile: 'rhythm' } as never
      })
    ).rejects.toThrow(/valid route descriptor/i)

    expect(api).not.toHaveBeenCalled()
  })
})
