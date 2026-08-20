import { isValidOpenDesignRuntimeOrigin } from './runtime-origin'

export type SeedHermesOpenDesignDefaultsStatus = 'seeded' | 'preserved' | 'failed'

export type SeedHermesOpenDesignDefaultsErrorCode =
  | 'invalid_origin'
  | 'network_error'
  | 'timeout'
  | 'invalid_response'
  | 'oversized_response'
  | 'http_error'
  | 'invalid_clock'

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
 * A production implementation should throw an `Error` carrying a `code` of
 * `'timeout' | 'network_error' | 'oversized_response'` so this module can
 * classify the failure without regexing the error message (see
 * `app-config-transport.ts`); an untyped `Error` still falls back to
 * message-sniffing for compatibility with simpler transports/test doubles.
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

const TRANSPORT_ERROR_CODES: ReadonlySet<string> = new Set(['timeout', 'network_error', 'oversized_response'])

function classifyFetchThrow(error: unknown): 'timeout' | 'network_error' | 'oversized_response' {
  if (error instanceof Error) {
    const code = (error as Error & { code?: unknown }).code

    if (typeof code === 'string' && TRANSPORT_ERROR_CODES.has(code)) {
      return code as 'timeout' | 'network_error' | 'oversized_response'
    }

    if (/timeout|timed out|aborted/i.test(error.message)) {
      return 'timeout'
    }
  }

  return 'network_error'
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

function isValidTransportResponse(value: unknown): value is OpenDesignAppConfigFetchResponse {
  return (
    isPlainObject(value) &&
    typeof (value as { status?: unknown }).status === 'number' &&
    typeof (value as { body?: unknown }).body === 'string'
  )
}

/**
 * The real daemon's `GET /api/app-config` wire body is an envelope,
 * `{ "config": {...} }` (apps/daemon/src/routes/media.ts), not the config's
 * own keys. Rejects any shape that isn't exactly that one-key envelope with
 * a plain-object config.
 */
function parseAppConfigEnvelope(body: string): Record<string, unknown> | undefined {
  let parsed: unknown

  try {
    parsed = JSON.parse(body)
  } catch {
    return undefined
  }

  if (!isPlainObject(parsed)) {
    return undefined
  }

  const keys = Object.keys(parsed)

  if (keys.length !== 1 || keys[0] !== 'config') {
    return undefined
  }

  const config = (parsed as { config: unknown }).config

  if (!isPlainObject(config)) {
    return undefined
  }

  return config
}

function isServerTelemetryDefault(value: unknown): boolean {
  return (
    isPlainObject(value) &&
    Object.keys(value).length === 2 &&
    value.metrics === true &&
    value.content === true
  )
}

function isNonEmptyString(value: unknown): boolean {
  return typeof value === 'string' && value.length > 0
}

/**
 * "Fresh" means the config carries nothing but what the real daemon itself
 * injects into an otherwise-untouched config
 * (apps/daemon/src/app-config.ts `applyTelemetryDefaults`/`readAppConfig`):
 * an exact `telemetry: {metrics:true, content:true}` and/or a non-empty
 * `installationId`. Any other key — including an explicit non-default
 * telemetry value, `agentId` (even `null`), onboarding state, a privacy
 * decision, any preference, or an unknown field — means a real client or a
 * prior seed already touched this config, so it must be preserved.
 */
function isFreshServerDefaultConfig(config: Record<string, unknown>): boolean {
  return Object.entries(config).every(([key, value]) => {
    if (key === 'telemetry') {
      return isServerTelemetryDefault(value)
    }

    if (key === 'installationId') {
      return isNonEmptyString(value)
    }

    return false
  })
}

function canonicalizeOrigin(origin: string): string {
  return origin.endsWith('/') ? origin.slice(0, -1) : origin
}

function isValidClockMs(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0
}

/**
 * Seeds the Open Design daemon's app-config with Hermes's minimal defaults,
 * but only when the config is truly fresh — untouched beyond what the
 * daemon itself injects. Any config already carrying an agent/provider
 * preference, onboarding state, a privacy decision, or an unrecognized field
 * is preserved byte-for-behavior: this never PUTs over it, and never
 * echoes/resends the fetched config back to the daemon.
 */
export async function seedHermesOpenDesignDefaults(
  options: SeedHermesOpenDesignDefaultsOptions
): Promise<SeedHermesOpenDesignDefaultsResult> {
  const { fetch, now } = options
  const timeoutMs = options.timeoutMs ?? DEFAULT_SEED_TIMEOUT_MS
  const maxResponseBytes = options.maxResponseBytes ?? DEFAULT_SEED_MAX_RESPONSE_BYTES

  if (!isValidOpenDesignRuntimeOrigin(options.origin)) {
    return { status: 'failed', errorCode: 'invalid_origin' }
  }

  const origin = canonicalizeOrigin(options.origin)
  const url = `${origin}${APP_CONFIG_PATH}`
  const headers = sameOriginHeaders(origin)

  let getResponse: OpenDesignAppConfigFetchResponse

  try {
    const rawGetResponse = await fetch(url, { method: 'GET', headers, timeoutMs })

    if (!isValidTransportResponse(rawGetResponse)) {
      return { status: 'failed', errorCode: 'invalid_response' }
    }

    getResponse = rawGetResponse
  } catch (error) {
    return { status: 'failed', errorCode: classifyFetchThrow(error) }
  }

  if (!isHttpOk(getResponse.status)) {
    return { status: 'failed', errorCode: 'http_error' }
  }

  if (Buffer.byteLength(getResponse.body, 'utf-8') > maxResponseBytes) {
    return { status: 'failed', errorCode: 'oversized_response' }
  }

  const config = parseAppConfigEnvelope(getResponse.body)

  if (config === undefined) {
    return { status: 'failed', errorCode: 'invalid_response' }
  }

  if (!isFreshServerDefaultConfig(config)) {
    return { status: 'preserved' }
  }

  let nowMs: number

  try {
    nowMs = now()
  } catch {
    return { status: 'failed', errorCode: 'invalid_clock' }
  }

  if (!isValidClockMs(nowMs)) {
    return { status: 'failed', errorCode: 'invalid_clock' }
  }

  const seedBody = {
    agentId: 'hermes',
    onboardingCompleted: true,
    telemetry: { metrics: false, content: false },
    privacyDecisionAt: nowMs,
    allowSilentUpdates: false
  }

  let putResponse: OpenDesignAppConfigFetchResponse

  try {
    const rawPutResponse = await fetch(url, {
      method: 'PUT',
      headers: { ...headers, 'Content-Type': 'application/json' },
      body: JSON.stringify(seedBody),
      timeoutMs
    })

    if (!isValidTransportResponse(rawPutResponse)) {
      return { status: 'failed', errorCode: 'invalid_response' }
    }

    putResponse = rawPutResponse
  } catch (error) {
    return { status: 'failed', errorCode: classifyFetchThrow(error) }
  }

  if (Buffer.byteLength(putResponse.body, 'utf-8') > maxResponseBytes) {
    return { status: 'failed', errorCode: 'oversized_response' }
  }

  if (!isHttpOk(putResponse.status)) {
    return { status: 'failed', errorCode: 'http_error' }
  }

  return { status: 'seeded' }
}
