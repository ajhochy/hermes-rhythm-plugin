/**
 * Hermes desktop adapter for the shared-agent catalog/editor (§5.4, S7).
 *
 * Uses ONLY the plugin's own `ctx.rest` helper against the local dashboard
 * routes in `dashboard/shared_agents_api.py` (§5.3) — never a bearer token,
 * never a second HTTP client, never the bridge capability directly.
 */
import { host, type PluginContext } from '@hermes/plugin-sdk'

import {
  RhythmGatewayError,
  type SharedAgent,
  type SharedAgentCatalog,
  type SharedAgentChanges,
  type SharedAgentsPort
} from '../vendor/rhythm-workspace-ui/dist/index.js'

type Rest = PluginContext['rest']

const AGENT_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/
const INTERACTIVE_SELECTION_RE = /^rhythm-shared-agent:v1:[A-Za-z0-9][A-Za-z0-9._-]{0,127}@\d{1,15}$/
const SAVE_STATUS_POLL_MS = 1_000
const SAVE_STATUS_TIMEOUT_MS = 130_000

type SaveStatus = { status?: unknown; confirmationId?: unknown }

function statusOf(error: unknown): number | undefined {
  const failure = error as
    | { statusCode?: unknown; status?: unknown; response?: { statusCode?: unknown; status?: unknown } }
    | undefined
  for (const value of [failure?.statusCode, failure?.status, failure?.response?.statusCode, failure?.response?.status]) {
    const status = typeof value === 'number' ? value : Number(value)
    if (Number.isInteger(status)) return status
  }
  return undefined
}

/** Maps a thrown `ctx.rest` failure to the SharedAgentsPort error contract.
 *  Deliberately local to this file rather than shared with plugin.tsx's own
 *  gatewayError: that one also parses task/workspace-operation confirmation
 *  envelopes this port never sees. */
function gatewayError(error: unknown): RhythmGatewayError {
  if (error instanceof RhythmGatewayError) return error
  const status = statusOf(error)
  if (status === 401 || status === 403) return new RhythmGatewayError('forbidden', 'Rhythm access is restricted.')
  if (status === 409) return new RhythmGatewayError('conflict', 'Changed elsewhere, reload.')
  if (status === 404 || status === 502 || status === 503 || status === 504) {
    return new RhythmGatewayError('unavailable', 'Rhythm is unavailable.')
  }
  return new RhythmGatewayError('server_error', 'Rhythm could not save safely.')
}

function agentPath(id: string): string {
  if (!AGENT_ID_RE.test(id)) {
    throw new RhythmGatewayError('server_error', 'Invalid agent id.')
  }
  return `/shared-agents/${encodeURIComponent(id)}`
}

function isSharedAgent(body: unknown): body is SharedAgent {
  return (
    !!body &&
    typeof body === 'object' &&
    typeof (body as { id?: unknown }).id === 'string' &&
    typeof (body as { revision?: unknown }).revision === 'number'
  )
}

function isPendingConfirmation(body: unknown): body is { status: 'confirmation_required'; confirmationId: string } {
  const candidate = body as SaveStatus | null
  return !!candidate && candidate.status === 'confirmation_required' && typeof candidate.confirmationId === 'string'
}

/** Bounded save-status poll (§5.4: every 1s for up to 130s after a 202). The
 *  bridge's approval decision is a small enum the renderer never needs to
 *  memorize the exact shape of: 'pending' keeps polling, a full SharedAgent
 *  body resolves immediately, and anything else terminal (rejected/expired/
 *  superseded/unrecognized) is 'forbidden' so the caller's draft is kept
 *  rather than silently discarded (§5.1). */
async function waitForSaveStatus(rest: Rest, id: string, confirmationId: string): Promise<SharedAgent> {
  const deadline = Date.now() + SAVE_STATUS_TIMEOUT_MS

  for (;;) {
    let body: unknown
    try {
      body = await rest(`${agentPath(id)}/save-status`, { method: 'POST', body: { confirmationId } })
    } catch (error) {
      throw gatewayError(error)
    }

    if (isSharedAgent(body)) return body

    if ((body as SaveStatus | null)?.status === 'pending') {
      if (Date.now() >= deadline) {
        throw new RhythmGatewayError('server_error', 'Rhythm did not confirm this change in time.')
      }
      await new Promise(resolve => setTimeout(resolve, SAVE_STATUS_POLL_MS))
      continue
    }

    throw new RhythmGatewayError('forbidden', 'The change was not confirmed in Rhythm.')
  }
}

export function createHermesSharedAgentsPort(rest: Rest): SharedAgentsPort {
  return {
    hostRuntime: 'hermes',
    list: async () => {
      try {
        return await rest<SharedAgentCatalog>('/shared-agents')
      } catch (error) {
        throw gatewayError(error)
      }
    },
    get: async (id: string) => {
      try {
        return await rest<SharedAgent>(agentPath(id))
      } catch (error) {
        throw gatewayError(error)
      }
    },
    save: async (id: string, expectedRevision: number, changes: SharedAgentChanges, opts) => {
      let body: unknown
      try {
        body = await rest(`${agentPath(id)}/save`, { method: 'POST', body: { expectedRevision, changes } })
      } catch (error) {
        throw gatewayError(error)
      }
      if (isSharedAgent(body)) return body
      if (isPendingConfirmation(body)) {
        opts?.onConfirmationRequired?.()
        return waitForSaveStatus(rest, id, body.confirmationId)
      }
      throw new RhythmGatewayError('server_error', 'Rhythm returned an unexpected save response.')
    },
    launch: async (id: string, expectedRevision: number) => {
      if (!AGENT_ID_RE.test(id) || !Number.isInteger(expectedRevision) || expectedRevision < 0) {
        return { ok: false, reason: 'selection_invalid' }
      }
      const selection = `rhythm-shared-agent:v1:${id}@${expectedRevision}`
      if (!INTERACTIVE_SELECTION_RE.test(selection)) {
        return { ok: false, reason: 'selection_invalid' }
      }
      host.newChat({ profile: 'default', policySelection: selection })
      return { ok: true }
    }
  }
}
