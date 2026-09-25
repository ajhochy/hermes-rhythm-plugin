import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { PassThrough } from 'node:stream'

import { afterEach, test, vi } from 'vitest'

const fixture = vi.hoisted(() => ({
  handlers: new Map<string, unknown>(),
  initialize: vi.fn(),
  spawn: vi.fn()
}))

vi.mock('electron', () => ({
  BrowserWindow: class {},
  ipcMain: {
    handle: vi.fn((channel: string, handler: unknown) => fixture.handlers.set(channel, handler)),
    removeHandler: vi.fn((channel: string) => fixture.handlers.delete(channel)),
    on: vi.fn(),
    removeListener: vi.fn()
  },
  session: { fromPartition: vi.fn(() => ({})) },
  shell: { openPath: vi.fn(), showItemInFolder: vi.fn(), trashItem: vi.fn() },
  systemPreferences: { askForMediaAccess: vi.fn(), getMediaAccessStatus: vi.fn(() => 'denied') }
}))
vi.mock('node:child_process', () => ({ spawn: fixture.spawn }))
vi.mock('./desktop-native-runtime', () => ({ initializeDesktopNativeRuntime: fixture.initialize }))
vi.mock('./backend-ready', () => ({ waitForDashboardPortAnnouncement: vi.fn(async () => 43123) }))
vi.mock('./gateway-ws-probe', () => ({ probeGatewayWebSocket: vi.fn(async () => ({ ok: true })) }))

import { createEmbeddedHermesHost } from './embedded-host'

const roots: string[] = []

afterEach(() => {
  fixture.handlers.clear()
  fixture.initialize.mockReset()
  fixture.spawn.mockReset()
  vi.unstubAllGlobals()
  for (const root of roots.splice(0)) fs.rmSync(root, { recursive: true, force: true })
})

function contents() {
  const mainFrame = { url: 'file:///tmp/hermes-artifact/renderer/index.html?embedded=1' }
  return {
    getURL: () => mainFrame.url,
    isDestroyed: () => false,
    mainFrame,
    on: vi.fn(),
    removeListener: vi.fn(),
    send: vi.fn()
  }
}

function child() {
  const value = new EventEmitter() as EventEmitter & {
    exitCode: number | null
    signalCode: NodeJS.Signals | null
    kill: ReturnType<typeof vi.fn>
    stdout: PassThrough
    stderr: PassThrough
  }
  value.exitCode = null
  value.signalCode = null
  value.stdout = new PassThrough()
  value.stderr = new PassThrough()
  value.kill = vi.fn(() => {
    value.exitCode = 0
    value.emit('exit', 0, null)
    return true
  })
  return value
}

test('HP-7: embedded host delivers one-shot handoffs only to owned default attempts', async () => {
  // Regression caught: the bearer lands in env/probes/receipts or survives retirement.
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'hermes-hp7-'))
  roots.push(root)
  const home = path.join(root, 'home')
  const userDataPath = path.join(root, 'user-data')
  fs.mkdirSync(home)
  fs.mkdirSync(userDataPath)
  const bridgeToken = 'D'.repeat(43)
  const providerToken = 'provider-synthetic-token'
  const receipts: unknown[] = []
  const spawned = child()
  const backendEnv = vi.fn(() => ({
    HERMES_HOST_CAPABILITY_RHYTHM_BRIDGE: bridgeToken,
    HERMES_HOST_CAPABILITY_RHYTHM_BRIDGE_ORIGIN: 'http://127.0.0.1:7363',
    OPENAI_API_KEY: providerToken
  }))
  fixture.spawn.mockReturnValue(spawned)
  fixture.initialize.mockReturnValue({ dispose: vi.fn(async () => undefined) })
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ version: 'fixture' }) })))

  const host = await createEmbeddedHermesHost({
    assetRoot: '/tmp/hermes-artifact',
    backendEnv,
    backendEnvContext: {
      authGeneration: 'generation',
      rhythmUserId: 'synthetic-user',
      serverOrigin: 'https://rhythm.example.test'
    },
    hermesHome: fs.realpathSync(home),
    hostWindow: {},
    onOwnedBackendAttempt: event => receipts.push(event),
    userDataPath,
    webContents: contents()
  })

  const options = fixture.initialize.mock.calls.at(-1)?.[0] as {
    backend: { ensure: (profile?: string) => Promise<unknown> }
    ownedSpawn: {
      prepare: (profile: string, token: string) => Promise<{
        accept: () => void
        env: NodeJS.ProcessEnv
        redactValues: readonly string[]
        retire: (cause: 'failed' | 'exited' | 'disposed') => void
      }>
      probeEnv: () => NodeJS.ProcessEnv
    }
  }

  const first = await options.ownedSpawn.prepare('default', 'dashboard-session-token')
  const second = await options.ownedSpawn.prepare('default', 'dashboard-session-token-2')
  for (const attempt of [first, second]) {
    const handoff = attempt.env.HERMES_HOST_CAPABILITIES_FILE
    assert.equal(typeof handoff, 'string')
    assert.equal(attempt.env.HERMES_HOST_CAPABILITY_RHYTHM_BRIDGE, undefined)
    assert.equal(attempt.env.HERMES_HOST_CAPABILITY_RHYTHM_BRIDGE_ORIGIN, undefined)
    assert.equal(attempt.env.HERMES_HOST_REQUIRED_PLUGINS, 'rhythm')
    assert.ok(attempt.redactValues.includes(bridgeToken))
    assert.equal(fs.statSync(handoff!).mode & 0o777, 0o600)
    assert.deepEqual(JSON.parse(fs.readFileSync(handoff!, 'utf8')), {
      version: 1,
      capabilities: { rhythm_bridge: { token: bridgeToken, origin: 'http://127.0.0.1:7363' } }
    })
    attempt.retire('disposed')
    assert.equal(fs.existsSync(handoff!), false)
  }

  const probeEnv = options.ownedSpawn.probeEnv()
  assert.equal(probeEnv.HERMES_HOST_CAPABILITIES_FILE, undefined)
  assert.equal(probeEnv.HERMES_HOST_CAPABILITY_RHYTHM_BRIDGE, undefined)

  const brokerCalls = backendEnv.mock.calls.length
  const nonDefault = await options.ownedSpawn.prepare('work', 'nondefault-session-token')
  assert.equal(nonDefault.env.HERMES_HOST_CAPABILITIES_FILE, undefined)
  assert.equal(backendEnv.mock.calls.length, brokerCalls)
  nonDefault.retire('disposed')

  backendEnv.mockReturnValue({
    HERMES_HOST_CAPABILITY_RHYTHM_BRIDGE: 'too-short',
    HERMES_HOST_CAPABILITY_RHYTHM_BRIDGE_ORIGIN: 'https://127.0.0.1:7363',
    OPENAI_API_KEY: providerToken
  })
  const invalid = await options.ownedSpawn.prepare('default', 'invalid-capability-session-token')
  assert.equal(invalid.env.HERMES_HOST_CAPABILITIES_FILE, undefined)
  assert.equal(invalid.redactValues.includes('too-short'), false)
  invalid.retire('disposed')
  backendEnv.mockReturnValue({
    HERMES_HOST_CAPABILITY_RHYTHM_BRIDGE: bridgeToken,
    HERMES_HOST_CAPABILITY_RHYTHM_BRIDGE_ORIGIN: 'http://127.0.0.1:7363',
    OPENAI_API_KEY: providerToken
  })

  const stale = path.join(userDataPath, 'hermes-temp', 'host-capabilities-stale.json')
  fs.writeFileSync(stale, 'stale')
  await options.backend.ensure('default')
  const childEnv = fixture.spawn.mock.calls.at(-1)?.[2]?.env as NodeJS.ProcessEnv
  const spawnedHandoff = childEnv.HERMES_HOST_CAPABILITIES_FILE
  assert.equal(childEnv.HERMES_HOST_CAPABILITY_RHYTHM_BRIDGE, undefined)
  assert.equal(childEnv.HERMES_HOST_REQUIRED_PLUGINS, 'rhythm')
  assert.equal(fs.existsSync(stale), false)
  assert.ok(spawnedHandoff && fs.existsSync(spawnedHandoff))
  assert.ok(!JSON.stringify(receipts).includes(bridgeToken))

  await host.dispose()
  assert.equal(fs.existsSync(spawnedHandoff!), false)
})
