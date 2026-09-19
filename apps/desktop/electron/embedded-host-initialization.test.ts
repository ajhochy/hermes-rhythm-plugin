import assert from 'node:assert/strict'

import { test, vi } from 'vitest'

const fixtures = vi.hoisted(() => {
  const handlers = new Map<string, unknown>()

  const ipcMain = {
    handle: vi.fn((channel: string, handler: unknown) => handlers.set(channel, handler)),
    removeHandler: vi.fn((channel: string) => handlers.delete(channel)),
    on: vi.fn(),
    removeListener: vi.fn()
  }

  return { handlers, initialize: vi.fn(), ipcMain }
})

vi.mock('electron', () => ({
  BrowserWindow: class {},
  ipcMain: fixtures.ipcMain,
  session: { fromPartition: vi.fn(() => ({})) },
  shell: { openPath: vi.fn(), showItemInFolder: vi.fn(), trashItem: vi.fn() },
  systemPreferences: { askForMediaAccess: vi.fn(), getMediaAccessStatus: vi.fn(() => 'denied') }
}))

vi.mock('./desktop-native-runtime', () => ({
  initializeDesktopNativeRuntime: fixtures.initialize
}))

import { createEmbeddedHermesHost, registerEmbeddedBackendRuntime } from './embedded-host'

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

test('failed shared-runtime initialization removes scoped handlers so a retry can mount cleanly', async () => {
  // Regression caught: a hidden-view startup failure left ipcMain handlers
  // registered, so the next Rhythm tab mount failed on duplicate channels.
  fixtures.initialize.mockImplementationOnce(() => {
    throw new Error('intentional initializer failure')
  })

  const options = {
    assetRoot: '/tmp/hermes-artifact',
    hermesHome: '/tmp/no-hermes-runtime',
    hostWindow: {},
    userDataPath: '/tmp/rhythm-user-data',
    webContents: contents()
  }

  await assert.rejects(createEmbeddedHermesHost(options), /intentional initializer failure/)
  assert.equal(fixtures.handlers.size, 0)

  fixtures.initialize.mockReturnValueOnce({ dispose: vi.fn() })
  const host = await createEmbeddedHermesHost({ ...options, webContents: contents() })
  assert.ok(fixtures.handlers.size > 0)
  await host.dispose()
  assert.equal(fixtures.handlers.size, 0)
})

test('production local-backend seam gives the shared runtime a structured-cloneable descriptor', async () => {
  // Regression caught by the real Rhythm probe: the host leaked its owned/stop
  // callback into hermes:connection, and Electron rejected the IPC reply with
  // "An object could not be cloned." Lifecycle ownership must stay host-local.
  fixtures.handlers.clear()
  fixtures.initialize.mockReset()
  fixtures.initialize.mockReturnValue({ dispose: vi.fn() })
  const hostWindow = {}

  const unregister = registerEmbeddedBackendRuntime(hostWindow, {
    connect: async () => ({
      endpoint: 'http://127.0.0.1:49790',
      logs: ['ready'],
      owned: true,
      profile: 'default',
      stop: async () => undefined,
      token: 'session-token',
      wsUrl: 'ws://127.0.0.1:49790/api/ws'
    })
  })

  const host = await createEmbeddedHermesHost({
    assetRoot: '/tmp/hermes-artifact',
    hostWindow,
    userDataPath: '/tmp/rhythm-user-data',
    webContents: contents()
  })

  assert.equal(
    fixtures.handlers.has('hermes:openExternal'),
    false,
    'the production host leaves openExternal to the shared scoped runtime'
  )
  const initialized = fixtures.initialize.mock.calls.at(-1)?.[0] as { localBackend: { connect: () => Promise<unknown> } }
  const descriptor = await initialized.localBackend.connect()

  assert.doesNotThrow(() => structuredClone(descriptor))
  assert.deepEqual(descriptor, {
    baseUrl: 'http://127.0.0.1:49790',
    logs: ['ready'],
    mode: 'local',
    profile: 'default',
    token: 'session-token',
    wsUrl: 'ws://127.0.0.1:49790/api/ws'
  })

  await host.dispose()
  unregister()
})

test('production cleanup accepts a renderer that Rhythm already detached', async () => {
  // Rhythm owns the WebContentsView and closes it before native teardown so
  // the renderer cannot keep polling into a removed IPC bridge. Native cleanup
  // must still release its scoped resources without touching the dead child.
  fixtures.handlers.clear()
  fixtures.initialize.mockReset()
  const dispose = vi.fn(async () => undefined)
  fixtures.initialize.mockReturnValue({ dispose })
  const hostWindow = {}

  const unregister = registerEmbeddedBackendRuntime(hostWindow, {
    connect: async () => ({ endpoint: 'http://127.0.0.1:49791', owned: false })
  })

  const child = contents()
  child.isDestroyed = () => true

  const host = await createEmbeddedHermesHost({
    assetRoot: '/tmp/hermes-artifact',
    hostWindow,
    userDataPath: '/tmp/rhythm-user-data',
    webContents: child
  })

  await assert.doesNotReject(host.dispose())
  assert.equal(dispose.mock.calls.length, 1)
  unregister()
})

test('production leaves local bootstrap to the shared runtime when no compatible backend was borrowed', async () => {
  // A fresh embedded install must retain Desktop's existing runtime resolution
  // and first-run flow. Passing the host's fallback spawner as localBackend
  // skipped that path and created a second lifecycle implementation.
  fixtures.handlers.clear()
  fixtures.initialize.mockReset()
  fixtures.initialize.mockReturnValue({ dispose: vi.fn() })

  const host = await createEmbeddedHermesHost({
    assetRoot: '/tmp/hermes-artifact',
    hermesHome: '/tmp/no-compatible-hermes-runtime',
    hostWindow: {},
    userDataPath: '/tmp/rhythm-user-data',
    webContents: contents()
  })

  const initialized = fixtures.initialize.mock.calls.at(-1)?.[0] as { localBackend?: unknown }

  assert.equal(initialized.localBackend, undefined)
  await host.dispose()
})

test('shared descriptor lifecycle retains distinct routes and revokes removed origins', async () => {
  // Connection profiles are not unique route identity: two registry entries
  // can target the same profile. Rhythm's network allowlist must retain both
  // live routes, then revoke an old one when the runtime removes it.
  fixtures.handlers.clear()
  fixtures.initialize.mockReset()
  fixtures.initialize.mockReturnValue({ dispose: vi.fn() })

  const host = await createEmbeddedHermesHost({
    assetRoot: '/tmp/hermes-artifact',
    hermesHome: '/tmp/no-compatible-hermes-runtime',
    hostWindow: {},
    userDataPath: '/tmp/rhythm-user-data',
    webContents: contents()
  })

  const initialized = fixtures.initialize.mock.calls.at(-1)?.[0] as {
    onConnectionDescriptor: (event: unknown) => void
  }

  initialized.onConnectionDescriptor({
    connection: {
      baseUrl: 'https://first.example.test',
      connectionId: 'first',
      profile: 'default',
      wsUrl: 'wss://first.example.test/api/ws'
    },
    type: 'upsert'
  })
  initialized.onConnectionDescriptor({
    connection: {
      baseUrl: 'https://second.example.test',
      connectionId: 'second',
      profile: 'default',
      wsUrl: 'wss://second.example.test/api/ws'
    },
    type: 'upsert'
  })
  assert.deepEqual(await host.getAllowedOrigins(), [
    'https://first.example.test',
    'wss://first.example.test',
    'https://second.example.test',
    'wss://second.example.test'
  ])

  initialized.onConnectionDescriptor({ connectionId: 'first', profile: 'default', type: 'remove' })
  assert.deepEqual(await host.getAllowedOrigins(), ['https://second.example.test', 'wss://second.example.test'])

  initialized.onConnectionDescriptor({ type: 'reset' })
  assert.deepEqual(await host.getAllowedOrigins(), [])
  await host.dispose()
})
