// HD-2 (§5.4): the Hermes desktop shared-agents adapter must use only
// ctx.rest, build a launch selection matching the interactive grammar, carry
// no credential strings, and bound its save-status poll. Mirrors the existing
// rhythm-workspace-ui.test.tsx / rhythm-shell.test.ts convention: import the
// plugin source directly from plugins/rhythm/desktop/src, spy on the real
// @hermes/plugin-sdk host rather than mocking the whole module.
import { host as hermesHost } from '@hermes/plugin-sdk'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createHermesSharedAgentsPort } from '../../../../plugins/rhythm/desktop/src/shared-agents'

const INTERACTIVE_SELECTION_RE = /^rhythm-shared-agent:v1:[A-Za-z0-9][A-Za-z0-9._-]{0,127}@\d{1,15}$/

afterEach(() => vi.restoreAllMocks())

describe('createHermesSharedAgentsPort (HD-2)', () => {
  it('list/get call only ctx.rest, against the exact §5.3 dashboard routes', async () => {
    const rest = vi.fn(async (path: string) => {
      if (path === '/shared-agents') return { schema: 'rhythm.shared-agent-catalog.v1', scope: 'fixture', generatedAt: '2026-09-25T00:00:00Z', agents: [] }
      if (path === '/shared-agents/team-lead') return { schema: 'rhythm.shared-agent.v1', id: 'team-lead', revision: 3 }
      throw new Error(`unexpected rest call: ${path}`)
    })
    const port = createHermesSharedAgentsPort(rest as never)

    await port.list()
    await port.get('team-lead')

    expect(rest).toHaveBeenNthCalledWith(1, '/shared-agents')
    expect(rest).toHaveBeenNthCalledWith(2, '/shared-agents/team-lead')
    expect(rest).toHaveBeenCalledTimes(2)
  })

  it('save applies a presentation-only change immediately, with no save-status poll', async () => {
    const rest = vi.fn(async (path: string, opts?: { method?: string; body?: unknown }) => {
      expect(path).toBe('/shared-agents/team-lead/save')
      expect(opts).toEqual({ method: 'POST', body: { expectedRevision: 3, changes: { label: 'Renamed' } } })
      return { schema: 'rhythm.shared-agent.v1', id: 'team-lead', revision: 4 }
    })
    const port = createHermesSharedAgentsPort(rest as never)

    const saved = await port.save('team-lead', 3, { label: 'Renamed' })

    expect(saved.revision).toBe(4)
    expect(rest).toHaveBeenCalledTimes(1)
  })

  it('save maps a non-2xx ctx.rest failure to the RhythmGatewayError contract', async () => {
    const rest = vi.fn(async () => { throw Object.assign(new Error('conflict'), { statusCode: 409 }) })
    const port = createHermesSharedAgentsPort(rest as never)

    await expect(port.get('team-lead')).rejects.toMatchObject({ kind: 'conflict' })
    await expect(port.save('team-lead', 3, { label: 'x' })).rejects.toMatchObject({ kind: 'conflict' })
  })

  it('launch builds a selection matching the interactive grammar and calls host.newChat with only profile + policySelection', async () => {
    const newChat = vi.spyOn(hermesHost, 'newChat').mockImplementation(() => undefined)
    const port = createHermesSharedAgentsPort(vi.fn() as never)

    const result = await port.launch?.('team.lead-1', 12)

    expect(result).toEqual({ ok: true })
    expect(newChat).toHaveBeenCalledTimes(1)
    expect(newChat).toHaveBeenCalledWith({ profile: 'default', policySelection: 'rhythm-shared-agent:v1:team.lead-1@12' })
    const [{ policySelection }] = newChat.mock.calls[0] as [{ policySelection: string }]
    expect(policySelection).toMatch(INTERACTIVE_SELECTION_RE)
  })

  it('launch refuses an id/revision that would not match the grammar, without calling host.newChat', async () => {
    const newChat = vi.spyOn(hermesHost, 'newChat').mockImplementation(() => undefined)
    const port = createHermesSharedAgentsPort(vi.fn() as never)

    expect(await port.launch?.('has a space', 1)).toEqual({ ok: false, reason: 'selection_invalid' })
    expect(await port.launch?.('ok-id', -1)).toEqual({ ok: false, reason: 'selection_invalid' })
    expect(newChat).not.toHaveBeenCalled()
  })

  it('source carries no credential-shaped strings (outside of its own doc comment)', () => {
    const source = readFileSync(join(__dirname, '../../../../plugins/rhythm/desktop/src/shared-agents.tsx'), 'utf8')
    // Strip comments first: the file's own doc comment legitimately explains
    // that it never uses a bearer token.
    const code = source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '')

    for (const forbidden of ['bearer', 'authorization', 'password', 'secret', 'api_key', 'apikey']) {
      expect(code.toLowerCase()).not.toContain(forbidden)
    }
  })
})

describe('createHermesSharedAgentsPort save-status polling (HD-2, bounded)', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

  it('polls save-status roughly every second and eventually gives up rather than polling forever', async () => {
    let saveStatusCalls = 0
    const rest = vi.fn(async (path: string) => {
      if (path === '/shared-agents/team-lead/save') return { status: 'confirmation_required', confirmationId: 'confirm-1' }
      if (path === '/shared-agents/team-lead/save-status') {
        saveStatusCalls += 1
        return { status: 'pending' }
      }
      throw new Error(`unexpected rest call: ${path}`)
    })
    const port = createHermesSharedAgentsPort(rest as never)
    const onConfirmationRequired = vi.fn()

    const pending = port.save('team-lead', 3, { label: 'Renamed' }, { onConfirmationRequired })
    pending.catch(() => undefined) // asserted below via expect(...).rejects

    // Advance well past the 130s bound in ~1s ticks (the adapter's own poll cadence).
    for (let elapsedMs = 0; elapsedMs <= 132_000; elapsedMs += 1_000) {
      await vi.advanceTimersByTimeAsync(1_000)
    }

    await expect(pending).rejects.toMatchObject({ kind: 'server_error' })
    expect(onConfirmationRequired).toHaveBeenCalledTimes(1)
    // Bounded: ~130 polls, not an unbounded/runaway loop.
    expect(saveStatusCalls).toBeGreaterThan(100)
    expect(saveStatusCalls).toBeLessThan(200)
  })

  it('rejects rather than silently discarding the draft when the registrar rejects the change', async () => {
    const rest = vi.fn(async (path: string) => {
      if (path === '/shared-agents/team-lead/save') return { status: 'confirmation_required', confirmationId: 'confirm-1' }
      if (path === '/shared-agents/team-lead/save-status') return { status: 'rejected' }
      throw new Error(`unexpected rest call: ${path}`)
    })
    const port = createHermesSharedAgentsPort(rest as never)

    const pending = port.save('team-lead', 3, { label: 'Renamed' })
    pending.catch(() => undefined) // asserted below via expect(...).rejects
    await vi.advanceTimersByTimeAsync(1_000)

    await expect(pending).rejects.toMatchObject({ kind: 'forbidden' })
  })
})
