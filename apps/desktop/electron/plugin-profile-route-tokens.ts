import crypto from 'node:crypto'

import type { OpaqueProfileRoute } from './plugin-profile-routes'

export interface IssuedPluginProfileRoute extends OpaqueProfileRoute {
  /** Opaque, Electron-owned capability for this exact profile route. */
  token: string
}

interface PluginProfileRouteTokensOptions {
  createToken?: () => string
  now?: () => number
  ttlMs?: number
}

interface TokenRecord {
  expiresAt: number
  route: OpaqueProfileRoute
}

const DEFAULT_TTL_MS = 10 * 60_000

function routeKey(route: OpaqueProfileRoute): string {
  return [route.connectionId, route.mode, route.profile, route.targetProfile].join('\0')
}

function sameRoute(left: OpaqueProfileRoute, right: OpaqueProfileRoute): boolean {
  return routeKey(left) === routeKey(right)
}

/**
 * Electron is the authority for profile-route membership. Tokens are kept only
 * in main, bind every field of the public descriptor, expire, and are revoked
 * when a route inventory update no longer contains the same route.
 */
export class PluginProfileRouteTokens {
  private readonly createToken: () => string
  private readonly now: () => number
  private readonly ttlMs: number
  private readonly records = new Map<string, TokenRecord>()

  constructor({ createToken = () => crypto.randomUUID(), now = Date.now, ttlMs = DEFAULT_TTL_MS }: PluginProfileRouteTokensOptions = {}) {
    this.createToken = createToken
    this.now = now
    this.ttlMs = ttlMs
  }

  issue(routes: OpaqueProfileRoute[]): IssuedPluginProfileRoute[] {
    const now = this.now()
    const current = new Set(routes.map(routeKey))

    for (const [token, record] of this.records) {
      if (record.expiresAt <= now || !current.has(routeKey(record.route))) {
        this.records.delete(token)
      }
    }

    return routes.map(route => {
      const existing = [...this.records.entries()].find(([, record]) => sameRoute(record.route, route))
      const token = existing?.[0] ?? this.createToken()

      this.records.set(token, { expiresAt: now + this.ttlMs, route: { ...route } })

      return { ...route, token }
    })
  }

  validate(candidate: unknown): OpaqueProfileRoute {
    if (!candidate || typeof candidate !== 'object') {
      throw new Error('Invalid or stale Electron-issued plugin profile route.')
    }

    const { token, ...route } = candidate as Partial<IssuedPluginProfileRoute>
    const record = typeof token === 'string' ? this.records.get(token) : undefined

    const expired = Boolean(record && record.expiresAt <= this.now())

    if (!record || expired || !sameRoute(route as OpaqueProfileRoute, record.route)) {
      // A forged descriptor must not be able to revoke another renderer's
      // legitimate pin just by guessing/observing its opaque token.
      if (expired && typeof token === 'string') {
        this.records.delete(token)
      }

      throw new Error('Invalid or stale Electron-issued plugin profile route.')
    }

    return { ...record.route }
  }
}

function isPluginApiPath(path: unknown): boolean {
  try {
    return new URL(String(path ?? ''), 'http://hermes.local').pathname.startsWith('/api/plugins/')
  } catch {
    return false
  }
}

/** Guard the generic IPC bridge before it resolves a backend or performs I/O. */
export function validatePluginApiRouteRequest(
  tokens: PluginProfileRouteTokens,
  request: { connectionId?: null | string; path?: unknown; pluginRoute?: unknown; profile?: null | string } | null | undefined
): void {
  const connectionId = String(request?.connectionId ?? '').trim()
  const hasPluginRoute = Boolean(request && Object.hasOwn(request, 'pluginRoute'))

  if (!isPluginApiPath(request?.path)) {
    return
  }

  // The v1 path was unpinned: both fields were absent. Every other shape is
  // a pinned request and must prove its Electron-issued capability before
  // backend resolution. In particular, a valid route cannot be downgraded to
  // a local/profile request by omitting its connection ID.
  if (!hasPluginRoute && !connectionId) {
    return
  }

  const route = tokens.validate(request?.pluginRoute)

  if (route.connectionId !== connectionId || route.profile !== String(request?.profile ?? '').trim()) {
    throw new Error('Invalid or stale Electron-issued plugin profile route.')
  }
}
