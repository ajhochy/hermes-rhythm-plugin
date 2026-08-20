import type { OpenDesignAppConfigFetch, OpenDesignAppConfigFetchResponse } from './app-config-seed'
import { DEFAULT_SEED_MAX_RESPONSE_BYTES } from './app-config-seed'

export type OpenDesignTransportErrorCode = 'timeout' | 'network_error' | 'oversized_response'

/**
 * Thrown by `createOpenDesignAppConfigFetch`. Carries a static `code` so
 * `app-config-seed.ts` can classify the failure without regexing an
 * arbitrary error message.
 */
export class OpenDesignTransportError extends Error {
  readonly code: OpenDesignTransportErrorCode

  constructor(code: OpenDesignTransportErrorCode, message: string) {
    super(message)
    this.name = 'OpenDesignTransportError'
    this.code = code
  }
}

type FetchLike = (input: string, init: RequestInit) => Promise<Response>

export interface CreateOpenDesignAppConfigFetchOptions {
  /** The global/injected `fetch` implementation. Never called with a network in tests. */
  fetchImpl: FetchLike
  maxResponseBytes?: number
}

/**
 * Builds the production `OpenDesignAppConfigFetch` transport: a bounded
 * deadline via `AbortController`, `redirect: 'error'` so a redirecting
 * daemon response is rejected rather than silently followed off-origin, a
 * `Content-Length` precheck, and an incremental `ReadableStream` byte cap
 * enforced while reading — never `response.text()`/`arrayBuffer()`
 * unbounded — so a misbehaving or malicious local daemon cannot exhaust
 * process memory before the cap is checked. The byte cap counts UTF-8 bytes
 * off the wire, not JS string/character length.
 */
export function createOpenDesignAppConfigFetch(
  options: CreateOpenDesignAppConfigFetchOptions
): OpenDesignAppConfigFetch {
  const { fetchImpl } = options
  const maxResponseBytes = options.maxResponseBytes ?? DEFAULT_SEED_MAX_RESPONSE_BYTES

  return async (url, init) => {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), init.timeoutMs)

    let response: Response

    try {
      response = await fetchImpl(url, {
        method: init.method,
        headers: init.headers,
        body: init.body,
        redirect: 'error',
        signal: controller.signal
      })
    } catch (error) {
      if (controller.signal.aborted) {
        throw new OpenDesignTransportError('timeout', 'Open Design app-config request deadline exceeded')
      }

      throw new OpenDesignTransportError('network_error', 'Open Design app-config request failed')
    } finally {
      clearTimeout(timer)
    }

    return readBoundedResponse(response, maxResponseBytes)
  }
}

function contentLengthExceedsCap(response: Response, maxResponseBytes: number): boolean {
  const header = response.headers.get('content-length')

  if (header === null) {
    return false
  }

  const declaredLength = Number(header)

  return Number.isFinite(declaredLength) && declaredLength > maxResponseBytes
}

async function readBoundedResponse(
  response: Response,
  maxResponseBytes: number
): Promise<OpenDesignAppConfigFetchResponse> {
  if (contentLengthExceedsCap(response, maxResponseBytes)) {
    await cancelBody(response)
    throw new OpenDesignTransportError('oversized_response', 'Open Design app-config Content-Length exceeds cap')
  }

  const body = await readBoundedUtf8Body(response, maxResponseBytes)

  return { status: response.status, body }
}

async function cancelBody(response: Response): Promise<void> {
  try {
    await response.body?.cancel()
  } catch {
    // Best-effort; the request is already being rejected.
  }
}

async function readBoundedUtf8Body(response: Response, maxResponseBytes: number): Promise<string> {
  const reader = response.body?.getReader()

  if (!reader) {
    return ''
  }

  const chunks: Uint8Array[] = []
  let totalBytes = 0

  while (true) {
    const { done, value } = await reader.read()

    if (done) {
      break
    }

    if (value) {
      totalBytes += value.byteLength

      if (totalBytes > maxResponseBytes) {
        try {
          await reader.cancel()
        } catch {
          // Best-effort; the request is already being rejected.
        }

        throw new OpenDesignTransportError('oversized_response', 'Open Design app-config response body exceeds cap')
      }

      chunks.push(value)
    }
  }

  return Buffer.concat(chunks.map((chunk) => Buffer.from(chunk))).toString('utf-8')
}
