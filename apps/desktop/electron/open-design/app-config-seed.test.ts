import assert from 'node:assert/strict'

import { test } from 'vitest'

import { seedHermesOpenDesignDefaults } from './app-config-seed'

const ORIGIN = 'http://127.0.0.1:5173'
const CLOCK_MS = 1_776_000_000_000
const now = () => CLOCK_MS

interface RecordedCall {
  url: string
  method: string
  headers: Record<string, string>
  body?: string
}

function makeFetch(responses: Array<{ status: number; body: string }>) {
  const calls: RecordedCall[] = []

  const fetch = async (
    url: string,
    init: { method: 'GET' | 'PUT'; headers: Record<string, string>; body?: string; timeoutMs: number }
  ) => {
    calls.push({ url, method: init.method, headers: init.headers, body: init.body })
    const next = responses.shift()

    if (!next) {
      throw new Error('no more mock responses queued')
    }

    return { status: next.status, body: next.body }
  }

  return { fetch, calls }
}

// The real daemon (apps/daemon/src/routes/media.ts, GET /api/app-config)
// always wraps the config in an envelope: `res.json({ config })`.
const FRESH_ENVELOPE = JSON.stringify({ config: { telemetry: { metrics: true, content: true } } })
const FRESH_EMPTY_ENVELOPE = JSON.stringify({ config: {} })

const FRESH_WITH_INSTALLATION_ID_ENVELOPE = JSON.stringify({
  config: { telemetry: { metrics: true, content: true }, installationId: 'abc-123' }
})

test('rejects an invalid origin without making any request', async () => {
  const { fetch, calls } = makeFetch([])

  const result = await seedHermesOpenDesignDefaults({ origin: 'https://127.0.0.1:5173', fetch, now })

  assert.deepEqual(result, { status: 'failed', errorCode: 'invalid_origin' })
  assert.equal(calls.length, 0)
})

test('seeds a truly fresh config (real {config} envelope, server telemetry defaults) with the minimal exact PUT body', async () => {
  const { fetch, calls } = makeFetch([
    { status: 200, body: FRESH_ENVELOPE },
    { status: 200, body: JSON.stringify({ config: {} }) }
  ])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'seeded' })
  assert.equal(calls.length, 2)

  const [getCall, putCall] = calls
  assert.equal(getCall.method, 'GET')
  assert.equal(getCall.url, `${ORIGIN}/api/app-config`)
  assert.equal(getCall.headers.Origin, ORIGIN)
  assert.equal(getCall.headers.Referer, `${ORIGIN}/`)

  assert.equal(putCall.method, 'PUT')
  assert.equal(putCall.url, `${ORIGIN}/api/app-config`)
  assert.equal(putCall.headers.Origin, ORIGIN)
  assert.equal(putCall.headers.Referer, `${ORIGIN}/`)
  assert.equal(putCall.headers['Content-Type'], 'application/json')

  const sentBody = JSON.parse(putCall.body ?? '{}')
  assert.deepEqual(sentBody, {
    agentId: 'hermes',
    onboardingCompleted: true,
    telemetry: { metrics: false, content: false },
    privacyDecisionAt: CLOCK_MS,
    allowSilentUpdates: false
  })
  assert.equal(typeof sentBody.privacyDecisionAt, 'number')

  // Never echoes/resends the fetched config (e.g. the server-injected telemetry-true default).
  assert.equal(sentBody.telemetry.metrics, false)

  // No credential, model, CLI env, PostHog, telemetry-endpoint, or updater keys.
  const forbiddenKeys = [
    'apiKey',
    'providerApiKey',
    'credentials',
    'model',
    'cliEnv',
    'posthogKey',
    'telemetryEndpoint',
    'updaterUrl'
  ]

  for (const key of forbiddenKeys) {
    assert.equal(Object.prototype.hasOwnProperty.call(sentBody, key), false, key)
  }
})

test('seeds a fresh config that also carries an empty object body', async () => {
  const { fetch, calls } = makeFetch([
    { status: 200, body: FRESH_EMPTY_ENVELOPE },
    { status: 200, body: FRESH_EMPTY_ENVELOPE }
  ])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'seeded' })
  assert.equal(calls.length, 2)
})

test('seeds a fresh config that carries only server telemetry defaults plus a non-empty installationId', async () => {
  const { fetch, calls } = makeFetch([
    { status: 200, body: FRESH_WITH_INSTALLATION_ID_ENVELOPE },
    { status: 200, body: FRESH_WITH_INSTALLATION_ID_ENVELOPE }
  ])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'seeded' })
  assert.equal(calls.length, 2)
})

test('preserves when telemetry is explicitly false rather than the server default true/true', async () => {
  const { fetch, calls } = makeFetch([
    { status: 200, body: JSON.stringify({ config: { telemetry: { metrics: false, content: false } } }) }
  ])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'preserved' })
  assert.equal(calls.length, 1)
})

test('preserves when telemetry is malformed (partial keys) rather than the exact server default', async () => {
  const { fetch, calls } = makeFetch([
    { status: 200, body: JSON.stringify({ config: { telemetry: { metrics: true } } }) }
  ])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'preserved' })
  assert.equal(calls.length, 1)
})

test('preserves when installationId is present but empty', async () => {
  const { fetch, calls } = makeFetch([
    {
      status: 200,
      body: JSON.stringify({
        config: { telemetry: { metrics: true, content: true }, installationId: '' }
      })
    }
  ])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'preserved' })
  assert.equal(calls.length, 1)
})

test('preserves a non-empty config and never PUTs, even when agentId is null', async () => {
  const { fetch, calls } = makeFetch([
    { status: 200, body: JSON.stringify({ config: { agentId: null } }) }
  ])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'preserved' })
  assert.equal(calls.length, 1)
  assert.equal(calls[0].method, 'GET')
})

test('preserves a config with an unrelated single key without mutating it', async () => {
  const { fetch, calls } = makeFetch([
    { status: 200, body: JSON.stringify({ config: { someUnknownField: 'secret-ish' } }) }
  ])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'preserved' })
  assert.equal(calls.length, 1)
})

test('preserves an onboarding-completed config', async () => {
  const { fetch, calls } = makeFetch([
    {
      status: 200,
      body: JSON.stringify({
        config: { telemetry: { metrics: true, content: true }, onboardingCompleted: true }
      })
    }
  ])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'preserved' })
  assert.equal(calls.length, 1)
})

test('preserves a config carrying a privacy decision timestamp', async () => {
  const { fetch, calls } = makeFetch([
    {
      status: 200,
      body: JSON.stringify({
        config: { telemetry: { metrics: true, content: true }, privacyDecisionAt: 1_700_000_000_000 }
      })
    }
  ])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'preserved' })
  assert.equal(calls.length, 1)
})

test('preserves a config carrying a provider/CLI field (agentCliEnv)', async () => {
  const { fetch, calls } = makeFetch([
    {
      status: 200,
      body: JSON.stringify({
        config: {
          telemetry: { metrics: true, content: true },
          agentCliEnv: { claude: { ANTHROPIC_API_KEY: 'sk-x' } }
        }
      })
    }
  ])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'preserved' })
  assert.equal(calls.length, 1)
})

test('a second call after seeding sees the now-populated real-envelope config and does not PUT again', async () => {
  const seededEnvelope = JSON.stringify({
    config: {
      agentId: 'hermes',
      onboardingCompleted: true,
      telemetry: { metrics: false, content: false },
      privacyDecisionAt: CLOCK_MS,
      allowSilentUpdates: false
    }
  })

  const { fetch, calls } = makeFetch([{ status: 200, body: seededEnvelope }])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'preserved' })
  assert.equal(calls.length, 1)
})

test('rejects a GET body with no envelope (flat config used to be treated as the wire shape)', async () => {
  const { fetch, calls } = makeFetch([{ status: 200, body: '{}' }])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'failed', errorCode: 'invalid_response' })
  assert.equal(calls.length, 1)
})

test('rejects an envelope with extra top-level keys beyond config', async () => {
  const { fetch } = makeFetch([
    { status: 200, body: JSON.stringify({ config: {}, extra: 'unexpected' }) }
  ])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'failed', errorCode: 'invalid_response' })
})

test('rejects an envelope whose config value is not a plain object', async () => {
  const { fetch } = makeFetch([{ status: 200, body: JSON.stringify({ config: [1, 2, 3] }) }])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'failed', errorCode: 'invalid_response' })
})

test('rejects an envelope whose config value is null', async () => {
  const { fetch } = makeFetch([{ status: 200, body: JSON.stringify({ config: null }) }])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'failed', errorCode: 'invalid_response' })
})

test('rejects a top-level array as the envelope', async () => {
  const { fetch } = makeFetch([{ status: 200, body: '[1,2,3]' }])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'failed', errorCode: 'invalid_response' })
})

test('a GET network failure produces a static failure code without leaking the error', async () => {
  const fetch = async () => {
    throw new Error('ECONNREFUSED 127.0.0.1:5173')
  }

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'failed', errorCode: 'network_error' })
})

test('a GET timeout produces a static timeout failure code', async () => {
  const fetch = async () => {
    throw new Error('timeout of 5000ms exceeded')
  }

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'failed', errorCode: 'timeout' })
})

test('a typed oversized-response transport error is classified without regexing the message', async () => {
  const fetch = async () => {
    const error = new Error('irrelevant message that does not mention size at all')

    ;(error as Error & { code?: string }).code = 'oversized_response'
    throw error
  }

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'failed', errorCode: 'oversized_response' })
})

test('an invalid JSON GET body produces a static invalid_response failure code', async () => {
  const { fetch } = makeFetch([{ status: 200, body: 'not json' }])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'failed', errorCode: 'invalid_response' })
})

test('a non-object GET body (array) produces a static invalid_response failure code', async () => {
  const { fetch } = makeFetch([{ status: 200, body: '[1,2,3]' }])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'failed', errorCode: 'invalid_response' })
})

test('an oversized GET body produces a static oversized_response failure code', async () => {
  const hugeBody = `{"config":{"padding":"${'x'.repeat(200_000)}"}}`
  const { fetch } = makeFetch([{ status: 200, body: hugeBody }])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now, maxResponseBytes: 1_000 })

  assert.deepEqual(result, { status: 'failed', errorCode: 'oversized_response' })
})

test('a non-2xx GET status produces a static http_error failure code', async () => {
  const { fetch } = makeFetch([{ status: 500, body: '{}' }])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'failed', errorCode: 'http_error' })
})

test('a non-2xx PUT status produces a static http_error failure code and does not report seeded', async () => {
  const { fetch } = makeFetch([
    { status: 200, body: FRESH_EMPTY_ENVELOPE },
    { status: 503, body: '' }
  ])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'failed', errorCode: 'http_error' })
})

test('a PUT network failure produces a static failure code', async () => {
  let call = 0

  const fetch = async () => {
    call += 1

    if (call === 1) {
      return { status: 200, body: FRESH_EMPTY_ENVELOPE }
    }

    throw new Error('socket hang up')
  }

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'failed', errorCode: 'network_error' })
})

test('never returns or leaks the fetched config body on a failure result', async () => {
  const { fetch } = makeFetch([{ status: 500, body: '{"secretProviderKey":"sk-super-secret"}' }])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  const serialized = JSON.stringify(result)
  assert.equal(serialized.includes('secretProviderKey'), false)
  assert.equal(serialized.includes('sk-super-secret'), false)
})

test('a response with a non-string body from the transport produces invalid_response', async () => {
  const fetch = async () => ({ status: 200, body: undefined as unknown as string })

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'failed', errorCode: 'invalid_response' })
})

test('a response with a non-number status from the transport produces invalid_response', async () => {
  const fetch = async () => ({ status: '200' as unknown as number, body: FRESH_EMPTY_ENVELOPE })

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'failed', errorCode: 'invalid_response' })
})

test('an invalid clock (NaN) produces a static failure code rather than throwing', async () => {
  const { fetch, calls } = makeFetch([{ status: 200, body: FRESH_EMPTY_ENVELOPE }])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now: () => Number.NaN })

  assert.deepEqual(result, { status: 'failed', errorCode: 'invalid_clock' })
  // The GET happened (we need the config to know it's fresh) but no PUT was attempted.
  assert.equal(calls.length, 1)
})

test('an invalid clock (negative) produces a static failure code rather than throwing', async () => {
  const { fetch } = makeFetch([{ status: 200, body: FRESH_EMPTY_ENVELOPE }])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now: () => -1 })

  assert.deepEqual(result, { status: 'failed', errorCode: 'invalid_clock' })
})

test('a fresh config whose injected clock throws produces a static failure code rather than throwing', async () => {
  const { fetch, calls } = makeFetch([{ status: 200, body: FRESH_EMPTY_ENVELOPE }])

  const result = await seedHermesOpenDesignDefaults({
    origin: ORIGIN,
    fetch,
    now: () => {
      throw new Error('clock unexpectedly threw')
    }
  })

  assert.deepEqual(result, { status: 'failed', errorCode: 'invalid_clock' })
  // The GET happened (we need the config to know it's fresh) but no PUT was attempted.
  assert.equal(calls.length, 1)
})

test('a preserved result never evaluates the clock at all', async () => {
  const { fetch } = makeFetch([{ status: 200, body: JSON.stringify({ config: { agentId: null } }) }])

  const result = await seedHermesOpenDesignDefaults({
    origin: ORIGIN,
    fetch,
    now: () => {
      throw new Error('clock must not be called when preserving')
    }
  })

  assert.deepEqual(result, { status: 'preserved' })
})

test('canonicalizes a trailing-slash origin so no double slash reaches /api/app-config', async () => {
  const { fetch, calls } = makeFetch([
    { status: 200, body: FRESH_EMPTY_ENVELOPE },
    { status: 200, body: FRESH_EMPTY_ENVELOPE }
  ])

  const result = await seedHermesOpenDesignDefaults({ origin: `${ORIGIN}/`, fetch, now })

  assert.deepEqual(result, { status: 'seeded' })
  assert.equal(calls[0].url, `${ORIGIN}/api/app-config`)
  assert.equal(calls[1].url, `${ORIGIN}/api/app-config`)
  assert.equal(calls[0].headers.Origin, ORIGIN)
  assert.equal(calls[0].headers.Referer, `${ORIGIN}/`)

  for (const call of calls) {
    assert.equal(call.url.includes('//api'), false)
  }
})

test('produces the same canonical URL for the non-slash origin form', async () => {
  const { fetch, calls } = makeFetch([
    { status: 200, body: FRESH_EMPTY_ENVELOPE },
    { status: 200, body: FRESH_EMPTY_ENVELOPE }
  ])

  await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.equal(calls[0].url, `${ORIGIN}/api/app-config`)
})
