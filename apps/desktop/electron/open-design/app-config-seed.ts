import { isValidOpenDesignRuntimeOrigin } from './runtime-origin'

export type SeedHermesOpenDesignDefaultsStatus = 'seeded' | 'preserved' | 'failed'

export type SeedHermesOpenDesignDefaultsErrorCode =
  'invalid_origin' | 'network_error' | 'timeout' | 'invalid_response' | 'oversized_response' | 'http_error'

export interface SeedHermesOpenDesignDefaultsResult {
  status: SeedHermesOpenDesignDefaultsStatus
  errorCode?: SeedHermesOpenDesignDefaultsErrorCode
}

export interface OpenDesignAppConfigFetchResponse {
  status: number
  body: string
}

export type OpenDesignAppConfigFetchInit = {
  method: 'GET' | 'PUT'
  headers: Readonly<Record<string, string>>
  body?: string
  timeoutMs: number
}

/**
 * Injected transport. The caller (owned by runtime wiring, not this module)
 * is responsible for actually enforcing `timeoutMs` against the wire and for
 * bounding how many bytes it reads off the socket before resolving `body` —
 * this module additionally re-checks the materialized body length as a
 * defense-in-depth bound, but cannot itself limit a stream it never sees.
 */
export type OpenDesignAppConfigFetch = (
  url: string,
  init: OpenDesignAppConfigFetchInit
) => Promise<OpenDesignAppConfigFetchResponse>

export interface SeedHermesOpenDesignDefaultsOptions {
  origin: string
  fetch: OpenDesignAppConfigFetch
  now: () => number
  timeoutMs?: number
  maxResponseBytes?: number
}

export const DEFAULT_SEED_TIMEOUT_MS = 5_000
export const DEFAULT_SEED_MAX_RESPONSE_BYTES = 65_536

const APP_CONFIG_PATH = '/api/app-config'

function isTimeoutError(error: unknown): boolean {
  return error instanceof Error && /timeout|timed out|aborted/i.test(error.message)
}

function sameOriginHeaders(origin: string): Record<string, string> {
  return { Origin: origin, Referer: `${origin}/` }
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isHttpOk(status: number): boolean {
  return status >= 200 && status < 300
}

/**
 * Seeds the Open Design daemon's app-config with Hermes's minimal defaults,
 * but only when it is a truly fresh (empty object) config. Any existing
 * config — including one holding only `{agentId: null}` — is preserved
 * byte-for-behavior: this never PUTs over an already-initialized config, so
 * it can never overwrite a user's agent/provider preferences or resend an
 * unknown field it doesn't understand the meaning of.
 */
export async function seedHermesOpenDesignDefaults(
  options: SeedHermesOpenDesignDefaultsOptions
): Promise<SeedHermesOpenDesignDefaultsResult> {
  const { origin, fetch, now } = options
  const timeoutMs = options.timeoutMs ?? DEFAULT_SEED_TIMEOUT_MS
  const maxResponseBytes = options.maxResponseBytes ?? DEFAULT_SEED_MAX_RESPONSE_BYTES

  if (!isValidOpenDesignRuntimeOrigin(origin)) {
    return { status: 'failed', errorCode: 'invalid_origin' }
  }

  const url = `${origin}${APP_CONFIG_PATH}`
  const headers = sameOriginHeaders(origin)

  let getResponse: OpenDesignAppConfigFetchResponse

  try {
    getResponse = await fetch(url, { method: 'GET', headers, timeoutMs })
  } catch (error) {
    return { status: 'failed', errorCode: isTimeoutError(error) ? 'timeout' : 'network_error' }
  }

  if (!isHttpOk(getResponse.status)) {
    return { status: 'failed', errorCode: 'http_error' }
  }

  if (getResponse.body.length > maxResponseBytes) {
    return { status: 'failed', errorCode: 'oversized_response' }
  }

  let config: unknown

  try {
    config = JSON.parse(getResponse.body)
  } catch {
    return { status: 'failed', errorCode: 'invalid_response' }
  }

  if (!isPlainObject(config)) {
    return { status: 'failed', errorCode: 'invalid_response' }
  }

  if (Object.keys(config).length > 0) {
    return { status: 'preserved' }
  }

  const seedBody = {
    agentId: 'hermes',
    onboardingCompleted: true,
    telemetry: { metrics: false, content: false },
    privacyDecisionAt: new Date(now()).toISOString(),
    allowSilentUpdates: false
  }

  let putResponse: OpenDesignAppConfigFetchResponse

  try {
    putResponse = await fetch(url, {
      method: 'PUT',
      headers: { ...headers, 'Content-Type': 'application/json' },
      body: JSON.stringify(seedBody),
      timeoutMs
    })
  } catch (error) {
    return { status: 'failed', errorCode: isTimeoutError(error) ? 'timeout' : 'network_error' }
  }

  if (!isHttpOk(putResponse.status)) {
    return { status: 'failed', errorCode: 'http_error' }
  }

  return { status: 'seeded' }
}
