import assert from 'node:assert/strict'

import { test } from 'vitest'

import { createOpenDesignAppConfigFetch, OpenDesignTransportError } from './app-config-transport'

function utf8Stream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  let index = 0

  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (index >= chunks.length) {
        controller.close()

        return
      }

      controller.enqueue(encoder.encode(chunks[index]))
      index += 1
    }
  })
}

function fakeResponse(options: {
  status: number
  chunks: string[]
  headers?: Record<string, string>
}): Response {
  const headers = new Headers(options.headers ?? {})
  const body = utf8Stream(options.chunks)

  return {
    status: options.status,
    headers,
    body,
    async text() {
      throw new Error('unbounded text() must never be called by the transport')
    },
    async arrayBuffer() {
      throw new Error('unbounded arrayBuffer() must never be called by the transport')
    }
  } as unknown as Response
}

test('returns status and materialized UTF-8 body for a small response', async () => {
  const fetchImpl = async () => fakeResponse({ status: 200, chunks: ['{"config":{}}'] })
  const fetch = createOpenDesignAppConfigFetch({ fetchImpl })

  const result = await fetch('http://127.0.0.1:5173/api/app-config', {
    method: 'GET',
    headers: {},
    timeoutMs: 5_000
  })

  assert.deepEqual(result, { status: 200, body: '{"config":{}}' })
})

test('assembles a body split across multiple stream chunks', async () => {
  const fetchImpl = async () => fakeResponse({ status: 200, chunks: ['{"config"', ':{}}'] })
  const fetch = createOpenDesignAppConfigFetch({ fetchImpl })

  const result = await fetch('http://127.0.0.1:5173/api/app-config', {
    method: 'GET',
    headers: {},
    timeoutMs: 5_000
  })

  assert.deepEqual(result, { status: 200, body: '{"config":{}}' })
})

test('counts UTF-8 bytes, not JS character length, against the cap', async () => {
  // Each euro sign is 1 JS UTF-16 code unit but 3 UTF-8 bytes.
  const euros = '€€€€'
  const fetchImpl = async () => fakeResponse({ status: 200, chunks: [euros] })
  const fetch = createOpenDesignAppConfigFetch({ fetchImpl, maxResponseBytes: 10 })

  await assert.rejects(
    fetch('http://127.0.0.1:5173/api/app-config', { method: 'GET', headers: {}, timeoutMs: 5_000 }),
    (error: unknown) => error instanceof OpenDesignTransportError && error.code === 'oversized_response'
  )
})

test('rejects via Content-Length precheck before reading the stream', async () => {
  let streamRead = false

  const fetchImpl = async () => {
    const response = fakeResponse({
      status: 200,
      chunks: ['ignored'],
      headers: { 'content-length': '999999' }
    })

    const originalGetReader = response.body!.getReader.bind(response.body)

    response.body!.getReader = (...args) => {
      streamRead = true

      return originalGetReader(...args)
    }

    return response
  }

  const fetch = createOpenDesignAppConfigFetch({ fetchImpl, maxResponseBytes: 1_000 })

  await assert.rejects(
    fetch('http://127.0.0.1:5173/api/app-config', { method: 'GET', headers: {}, timeoutMs: 5_000 }),
    (error: unknown) => error instanceof OpenDesignTransportError && error.code === 'oversized_response'
  )

  assert.equal(streamRead, false)
})

test('aborts and rejects mid-stream once the incremental byte cap is exceeded', async () => {
  let cancelled = false

  const fetchImpl = async () => {
    const response = fakeResponse({ status: 200, chunks: ['aaaaa', 'bbbbb', 'ccccc'] })
    const originalGetReader = response.body!.getReader.bind(response.body)

    response.body!.getReader = () => {
      const reader = originalGetReader()
      const originalCancel = reader.cancel.bind(reader)

      reader.cancel = async (...args) => {
        cancelled = true

        return originalCancel(...args)
      }

      return reader
    }

    return response
  }

  const fetch = createOpenDesignAppConfigFetch({ fetchImpl, maxResponseBytes: 8 })

  await assert.rejects(
    fetch('http://127.0.0.1:5173/api/app-config', { method: 'GET', headers: {}, timeoutMs: 5_000 }),
    (error: unknown) => error instanceof OpenDesignTransportError && error.code === 'oversized_response'
  )

  assert.equal(cancelled, true)
})

test('classifies a deadline abort as a typed timeout error', async () => {
  const fetchImpl = (_url: string, init: RequestInit) =>
    new Promise<Response>((_resolve, reject) => {
      init.signal?.addEventListener('abort', () => {
        reject(new Error('AbortError'))
      })
    })

  const fetch = createOpenDesignAppConfigFetch({ fetchImpl })

  await assert.rejects(
    fetch('http://127.0.0.1:5173/api/app-config', { method: 'GET', headers: {}, timeoutMs: 10 }),
    (error: unknown) => error instanceof OpenDesignTransportError && error.code === 'timeout'
  )
})

test('classifies a non-abort fetch rejection as a typed network error', async () => {
  const fetchImpl = async () => {
    throw new Error('ECONNREFUSED')
  }

  const fetch = createOpenDesignAppConfigFetch({ fetchImpl })

  await assert.rejects(
    fetch('http://127.0.0.1:5173/api/app-config', { method: 'GET', headers: {}, timeoutMs: 5_000 }),
    (error: unknown) => error instanceof OpenDesignTransportError && error.code === 'network_error'
  )
})

test('passes redirect: "error" so the daemon response cannot silently redirect off-origin', async () => {
  let observedRedirectMode: RequestRedirect | undefined

  const fetchImpl = async (_url: string, init: RequestInit) => {
    observedRedirectMode = init.redirect

    return fakeResponse({ status: 200, chunks: ['{}'] })
  }

  const fetch = createOpenDesignAppConfigFetch({ fetchImpl })
  await fetch('http://127.0.0.1:5173/api/app-config', { method: 'GET', headers: {}, timeoutMs: 5_000 })

  assert.equal(observedRedirectMode, 'error')
})

test('bounds a PUT response body too, even though the caller ignores it', async () => {
  const fetchImpl = async () => fakeResponse({ status: 200, chunks: ['x'.repeat(50)] })
  const fetch = createOpenDesignAppConfigFetch({ fetchImpl, maxResponseBytes: 10 })

  await assert.rejects(
    fetch('http://127.0.0.1:5173/api/app-config', {
      method: 'PUT',
      headers: {},
      body: '{}',
      timeoutMs: 5_000
    }),
    (error: unknown) => error instanceof OpenDesignTransportError && error.code === 'oversized_response'
  )
})

test('the deadline aborts a stalled body read, not just fetch/header setup', async () => {
  let cancelled = false

  const stalledStream = new ReadableStream<Uint8Array>({
    pull() {
      // Never enqueue or close: simulates a connection that sends headers
      // then stalls mid-body, forever, below the byte cap.
    },
    cancel() {
      cancelled = true
    }
  })

  const fetchImpl = async () =>
    ({
      status: 200,
      headers: new Headers(),
      body: stalledStream,
      async text() {
        throw new Error('unbounded text() must never be called by the transport')
      },
      async arrayBuffer() {
        throw new Error('unbounded arrayBuffer() must never be called by the transport')
      }
    }) as unknown as Response

  const fetch = createOpenDesignAppConfigFetch({ fetchImpl })

  const fetchPromise = fetch('http://127.0.0.1:5173/api/app-config', {
    method: 'GET',
    headers: {},
    timeoutMs: 10
  })

  const safetyTimeout = new Promise((_resolve, reject) => {
    setTimeout(
      () => reject(new Error('test safety timeout: transport did not honor timeoutMs across the body read')),
      200
    )
  })

  await assert.rejects(
    Promise.race([fetchPromise, safetyTimeout]),
    (error: unknown) => error instanceof OpenDesignTransportError && error.code === 'timeout'
  )

  assert.equal(cancelled, true)
})

test('a response with no body stream resolves to an empty string', async () => {
  const fetchImpl = async () =>
    ({ status: 204, headers: new Headers(), body: null }) as unknown as Response

  const fetch = createOpenDesignAppConfigFetch({ fetchImpl })

  const result = await fetch('http://127.0.0.1:5173/api/app-config', {
    method: 'GET',
    headers: {},
    timeoutMs: 5_000
  })

  assert.deepEqual(result, { status: 204, body: '' })
})
