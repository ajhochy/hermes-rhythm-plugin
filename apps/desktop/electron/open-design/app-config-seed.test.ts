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

test('rejects an invalid origin without making any request', async () => {
  const { fetch, calls } = makeFetch([])

  const result = await seedHermesOpenDesignDefaults({ origin: 'https://127.0.0.1:5173', fetch, now })

  assert.deepEqual(result, { status: 'failed', errorCode: 'invalid_origin' })
  assert.equal(calls.length, 0)
})

test('seeds a truly fresh (empty object) daemon config with the minimal exact PUT body', async () => {
  const { fetch, calls } = makeFetch([
    { status: 200, body: '{}' },
    { status: 200, body: '{}' }
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
    privacyDecisionAt: new Date(CLOCK_MS).toISOString(),
    allowSilentUpdates: false
  })

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

test('preserves a non-empty config and never PUTs, even when agentId is null', async () => {
  const { fetch, calls } = makeFetch([{ status: 200, body: '{"agentId":null}' }])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'preserved' })
  assert.equal(calls.length, 1)
  assert.equal(calls[0].method, 'GET')
})

test('preserves a config with an unrelated single key without mutating it', async () => {
  const { fetch, calls } = makeFetch([{ status: 200, body: '{"someUnknownField":"secret-ish"}' }])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'preserved' })
  assert.equal(calls.length, 1)
})

test('a second call after seeding sees the now-populated config and does not PUT again', async () => {
  const seededBody = JSON.stringify({
    agentId: 'hermes',
    onboardingCompleted: true,
    telemetry: { metrics: false, content: false },
    privacyDecisionAt: new Date(CLOCK_MS).toISOString(),
    allowSilentUpdates: false
  })

  const { fetch, calls } = makeFetch([{ status: 200, body: seededBody }])

  const result = await seedHermesOpenDesignDefaults({ origin: ORIGIN, fetch, now })

  assert.deepEqual(result, { status: 'preserved' })
  assert.equal(calls.length, 1)
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
  const hugeBody = `{"padding":"${'x'.repeat(200_000)}"}`
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
    { status: 200, body: '{}' },
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
      return { status: 200, body: '{}' }
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
