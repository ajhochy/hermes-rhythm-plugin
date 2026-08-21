import { describe, expect, it, vi } from 'vitest'

import { PluginProfileRouteTokens, validatePluginApiRouteRequest } from './plugin-profile-route-tokens'

const route = {
  connectionId: 'homelab',
  mode: 'remote' as const,
  profile: 'rhythm',
  targetProfile: 'rhythm'
}

describe('PluginProfileRouteTokens', () => {
  it('authorizes only the exact Electron-issued profile route', () => {
    const tokens = new PluginProfileRouteTokens({ createToken: () => 'issued-token' })
    const [issued] = tokens.issue([route])

    expect(tokens.validate(issued)).toEqual(route)
    expect(() => tokens.validate({ ...issued, profile: 'forged' })).toThrow(/invalid or stale/i)
    expect(() => tokens.validate({ ...issued, targetProfile: 'forged' })).toThrow(/invalid or stale/i)
    expect(() => tokens.validate({ ...issued, connectionId: 'other-host' })).toThrow(/invalid or stale/i)
    expect(() => tokens.validate({ ...issued, mode: 'local' })).toThrow(/invalid or stale/i)
  })

  it('expires an otherwise valid route before it can reach a backend', () => {
    const now = vi.fn(() => 1_000)
    const tokens = new PluginProfileRouteTokens({ createToken: () => 'issued-token', now, ttlMs: 50 })
    const [issued] = tokens.issue([route])

    now.mockReturnValue(1_051)

    expect(() => tokens.validate(issued)).toThrow(/invalid or stale/i)
  })

  it('keeps an unchanged issued route valid across inventory refreshes, but invalidates changed routes', () => {
    let next = 0
    const tokens = new PluginProfileRouteTokens({ createToken: () => `token-${++next}` })
    const [first] = tokens.issue([route])
    const [same] = tokens.issue([route])

    expect(same.token).toBe(first.token)
    expect(tokens.validate(first)).toEqual(route)

    const [updated] = tokens.issue([{ ...route, targetProfile: 'new-target' }])

    expect(updated.token).not.toBe(first.token)
    expect(() => tokens.validate(first)).toThrow(/invalid or stale/i)
    expect(tokens.validate(updated)).toEqual({ ...route, targetProfile: 'new-target' })
  })

  it('rejects forged and stale explicit plugin requests before the network boundary', async () => {
    const tokens = new PluginProfileRouteTokens({ createToken: () => 'issued-token' })
    const [issued] = tokens.issue([route])
    const fetch = vi.fn()

    const request = async (candidate: Record<string, unknown>) => {
      validatePluginApiRouteRequest(tokens, candidate)

      return fetch()
    }

    await expect(
      request({ connectionId: 'homelab', path: '/api/plugins/rhythm/tasks', pluginRoute: { ...issued, profile: 'forged' }, profile: 'forged' })
    ).rejects.toThrow(/invalid or stale/i)

    await expect(request({ connectionId: 'homelab', path: '/api/plugins/rhythm/tasks', profile: 'rhythm' })).rejects.toThrow(
      /invalid or stale/i
    )
    await expect(
      request({ connectionId: 'homelab', path: '/api/plugins/rhythm/tasks', pluginRoute: issued, profile: 'rhythm' })
    ).resolves.toBeUndefined()

    expect(fetch).toHaveBeenCalledTimes(1)
  })
})
