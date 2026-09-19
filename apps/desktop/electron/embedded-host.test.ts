import assert from 'node:assert/strict'

import { test, vi } from 'vitest'

vi.mock('electron', () => ({
  app: { getPath: () => '/tmp' },
  ipcMain: { handle: vi.fn(), removeHandler: vi.fn() },
  shell: { openPath: vi.fn(), showItemInFolder: vi.fn(), trashItem: vi.fn() }
}))

import { createEmbeddedHermesHostForTest, createEmbeddedIpcRegistrar } from './embedded-host'

type Handler = (event: unknown, ...args: unknown[]) => unknown

function fakeIpc() {
  const handlers = new Map<string, Handler>()

  return {
    handlers,
    handle(channel: string, handler: Handler) {
      if (handlers.has(channel)) {
        throw new Error(`duplicate handler: ${channel}`)
      }

      handlers.set(channel, handler)
    },
    removeHandler(channel: string) {
      handlers.delete(channel)
    }
  }
}

function fakeContents(overrides: Record<string, unknown> = {}) {
  const mainFrame = { frameTreeNodeId: 1, url: 'file:///tmp/hermes-artifact/renderer/index.html?embedded=1' }
  const listeners = new Map<string, Set<(...args: any[]) => void>>()

  return {
    id: 101,
    mainFrame,
    getURL: () => 'file:///tmp/hermes-artifact/renderer/index.html?embedded=1',
    isDestroyed: () => false,
    send: vi.fn(),
    on(channel: string, listener: (...args: any[]) => void) {
      const set = listeners.get(channel) || new Set()
      set.add(listener)
      listeners.set(channel, set)
    },
    removeListener(channel: string, listener: (...args: any[]) => void) {
      listeners.get(channel)?.delete(listener)
    },
    emit(channel: string, ...args: any[]) {
      for (const listener of listeners.get(channel) || []) {
        listener(...args)
      }
    },
    ...overrides
  }
}

function trustedEvent(contents: ReturnType<typeof fakeContents>) {
  return { sender: contents, senderFrame: contents.mainFrame }
}

function deferred<T>() {
  let resolve!: (value: T) => void

  const promise = new Promise<T>(done => {
    resolve = done
  })

  return { promise, resolve }
}

test('issue-1542-desktop-c1: rejects privileged IPC from Rhythm, subframes, navigated, and disposed documents', async () => {
  // Regression caught: a global ipcMain handler lets the Rhythm shell or a plugin
  // iframe call Hermes native capabilities after the embedded view is mounted.
  const ipc = fakeIpc()
  const contents = fakeContents()

  const host = await createEmbeddedHermesHostForTest(
    {
      assetRoot: '/tmp/hermes-artifact',
      hostWindow: {},
      userDataPath: '/tmp/rhythm-user-data',
      webContents: contents
    },
    { ipc }
  )

  const metadata = ipc.handlers.get('hermes:embedded:metadata')!

  assert.equal((await metadata(trustedEvent(contents)) as { embedded: boolean }).embedded, true)
  assert.throws(() => metadata({ sender: fakeContents(), senderFrame: contents.mainFrame }), /untrusted embedded Hermes IPC sender/)
  assert.throws(() => metadata({ sender: contents, senderFrame: { frameTreeNodeId: 2 } }), /untrusted embedded Hermes IPC sender/)

  const originalUrl = contents.getURL
  const originalFrameUrl = (contents.mainFrame as { url: string }).url
  contents.getURL = () => 'https://rhythm.local/hermes'
  ;(contents.mainFrame as { url: string }).url = 'https://rhythm.local/hermes'
  assert.throws(() => metadata(trustedEvent(contents)), /untrusted embedded Hermes IPC sender/)
  contents.getURL = originalUrl
  ;(contents.mainFrame as { url: string }).url = originalFrameUrl

  // A reload to the same local file invalidates the old document before its URL
  // changes. The assertion catches a guard that only compares URL strings.
  contents.emit('did-start-navigation', {}, originalUrl(), false, true)
  assert.throws(() => metadata(trustedEvent(contents)), /untrusted embedded Hermes IPC sender/)

  // Electron commits the new document before did-finish-load. The sandboxed
  // preload performs its first boot IPC in that interval, so trust the exact
  // newly committed main frame without reopening the previous document.
  contents.emit('did-frame-navigate', {}, originalUrl(), 200, 'OK', true)
  assert.equal((await metadata(trustedEvent(contents)) as { embedded: boolean }).embedded, true)

  // HashRouter changes are in-place navigations on this same committed file
  // document. Electron emits no second did-frame-navigate for them, so they
  // must not revoke the renderer's native bridge during normal boot routing.
  contents.emit('did-start-navigation', {}, `${originalUrl()}#session/s-1`, true, true)
  assert.equal((await metadata(trustedEvent(contents)) as { embedded: boolean }).embedded, true)

  contents.isDestroyed = () => true
  assert.throws(() => metadata(trustedEvent(contents)), /untrusted embedded Hermes IPC sender/)

  await host.dispose()
  assert.equal(ipc.handlers.size, 0)
})

test('a Hermes-owned popout gains the same scoped bridge while unrelated views remain rejected', async () => {
  const ipc = fakeIpc()
  const contents = fakeContents()
  const popout = fakeContents({ id: 102 })
  const registrar = createEmbeddedIpcRegistrar(ipc, contents, '/tmp/hermes-artifact')
  registrar.handle('hermes:test:popout', () => ({ ok: true }))

  registrar.addWebContents(popout)
  assert.deepEqual(await ipc.handlers.get('hermes:test:popout')!(trustedEvent(popout)), { ok: true })
  assert.throws(
    () => ipc.handlers.get('hermes:test:popout')!({ sender: fakeContents(), senderFrame: popout.mainFrame }),
    /untrusted embedded Hermes IPC sender/
  )

  popout.emit('did-start-navigation', {}, 'file:///tmp/hermes-artifact/renderer/index.html', false, true)
  assert.throws(() => ipc.handlers.get('hermes:test:popout')!(trustedEvent(popout)), /untrusted embedded Hermes IPC sender/)
  popout.emit('did-finish-load')
  assert.deepEqual(await ipc.handlers.get('hermes:test:popout')!(trustedEvent(popout)), { ok: true })
  registrar.dispose()
})

test('issue-1542-desktop-c5: keeps a compatible borrowed backend alive and stops only a backend started by this host', async () => {
  // Regression caught: disposing an embedded Hermes tab kills the user's already
  // authenticated standalone service, interrupting its independent sessions.
  const borrowedStop = vi.fn()
  const borrowedIpc = fakeIpc()
  const borrowedContents = fakeContents()

  const borrowed = await createEmbeddedHermesHostForTest(
    {
      assetRoot: '/tmp/hermes-artifact',
      hostWindow: {},
      userDataPath: '/tmp/rhythm-user-data',
      webContents: borrowedContents
    },
    {
      ipc: borrowedIpc,
      runtime: { connect: async () => ({ endpoint: 'http://127.0.0.1:43111', owned: false, stop: borrowedStop }) }
    }
  )

  const originSnapshots: string[][] = []
  const stopOriginUpdates = borrowed.onAllowedOrigins(origins => originSnapshots.push(origins))
  await borrowedIpc.handlers.get('hermes:connection')!(trustedEvent(borrowedContents))
  assert.deepEqual(await borrowed.getAllowedOrigins(), ['http://127.0.0.1:43111', 'ws://127.0.0.1:43111'])
  assert.deepEqual(originSnapshots, [[], ['http://127.0.0.1:43111', 'ws://127.0.0.1:43111']])
  stopOriginUpdates()
  await borrowed.dispose()
  assert.equal(borrowedStop.mock.calls.length, 0)

  const ownedStop = vi.fn()
  const ownedIpc = fakeIpc()
  const ownedContents = fakeContents()

  const owned = await createEmbeddedHermesHostForTest(
    {
      assetRoot: '/tmp/hermes-artifact',
      hostWindow: {},
      userDataPath: '/tmp/rhythm-user-data',
      webContents: ownedContents
    },
    {
      ipc: ownedIpc,
      runtime: { connect: async () => ({ endpoint: 'http://127.0.0.1:43112', owned: true, stop: ownedStop }) }
    }
  )

  // The host owns the runtime only after the renderer actually asks for it.
  await ownedIpc.handlers.get('hermes:connection')!(trustedEvent(ownedContents))
  await owned.dispose()
  assert.equal(ownedStop.mock.calls.length, 1)
})

test('issue-1542-desktop-c5: disposal during a shared backend start tears down the late owned child', async () => {
  // Regression caught: tab close races backend readiness, leaving an owned
  // Hermes process alive after its WebContents and IPC handlers are gone.
  const starting = deferred<{ endpoint: string; owned: boolean; stop: () => void }>()
  const connect = vi.fn(() => starting.promise)
  const stop = vi.fn()
  const ipc = fakeIpc()
  const contents = fakeContents()

  const host = await createEmbeddedHermesHostForTest(
    { assetRoot: '/tmp/hermes-artifact', hostWindow: {}, userDataPath: '/tmp/rhythm-user-data', webContents: contents },
    { ipc, runtime: { connect } }
  )

  const handler = ipc.handlers.get('hermes:connection')!

  const first = handler(trustedEvent(contents)) as Promise<unknown>
  const second = handler(trustedEvent(contents)) as Promise<unknown>
  assert.equal(connect.mock.calls.length, 1)

  await host.dispose()
  starting.resolve({ endpoint: 'http://127.0.0.1:43113', owned: true, stop })
  await assert.rejects(first, /disposed while the backend was starting/)
  await assert.rejects(second, /disposed while the backend was starting/)
  assert.equal(stop.mock.calls.length, 1)
})

test('shared runtime origin snapshot does not start a generic local backend before routing decides remote or SSH', async () => {
  const connect = vi.fn(async () => ({ endpoint: 'http://127.0.0.1:43116', owned: true }))

  const host = await createEmbeddedHermesHostForTest(
    { assetRoot: '/tmp/hermes-artifact', hostWindow: {}, userDataPath: '/tmp/rhythm-user-data', webContents: fakeContents() },
    { ipc: fakeIpc(), registerCoreBridge: false, runtime: { connect } }
  )

  assert.deepEqual(await host.getAllowedOrigins(), [])
  assert.equal(connect.mock.calls.length, 0)
})

test('embedded media permission asks only for the trusted main renderer document and defaults to deny', async () => {
  // Regression caught: Rhythm's session permission hook grants microphone access
  // to a plugin frame or arbitrary navigated document sharing the WebContents.
  const consent = vi.fn(async () => true)
  const ipc = fakeIpc()
  const contents = fakeContents()

  const host = await createEmbeddedHermesHostForTest(
    {
      assetRoot: '/tmp/hermes-artifact',
      hostWindow: {},
      mediaConsent: consent,
      userDataPath: '/tmp/rhythm-user-data',
      webContents: contents
    },
    { ipc, runtime: { connect: async () => ({ endpoint: 'http://127.0.0.1:43114', owned: false }) } }
  )

  // The renderer's explicit consent must happen before Chromium asks the
  // session permission hook. A hook alone is not user consent.
  assert.equal(
    await host.handlePermissionRequest({
      permission: 'media',
      requestingUrl: 'file:///tmp/hermes-artifact/renderer/index.html?embedded=1#session/s-1',
      mediaTypes: ['audio']
    }),
    false
  )
  assert.equal(await ipc.handlers.get('hermes:requestMicrophoneAccess')!(trustedEvent(contents)), true)
  assert.equal(consent.mock.calls.length, 1)
  assert.equal(
    await host.handlePermissionRequest({
      permission: 'media',
      requestingUrl: 'file:///tmp/hermes-artifact/renderer/index.html?embedded=1#session/s-1',
      mediaTypes: ['audio']
    }),
    true
  )
  assert.equal(
    await host.handlePermissionRequest({ isMainFrame: false, permission: 'media', requestingUrl: 'file:///tmp/hermes-artifact/renderer/index.html', mediaTypes: ['audio'] }),
    false
  )
  assert.equal(
    await host.handlePermissionRequest({ permission: 'media', requestingUrl: 'https://rhythm.local/', mediaTypes: ['audio'] }),
    false
  )
  assert.equal(
    await host.handlePermissionRequest({ permission: 'notifications', requestingUrl: 'file:///tmp/hermes-artifact/renderer/index.html', mediaTypes: ['audio'] }),
    false
  )
  assert.equal(
    await host.handlePermissionRequest({ permission: 'media', requestingUrl: 'file:///tmp/hermes-artifact/renderer/index.html', mediaTypes: ['audio', 'video'] }),
    false
  )
})

test('embedded guest webviews retain remote browser access without inheriting the Hermes preload', async () => {
  // Regression caught: allowing the Desktop Browser's remote guest to inherit
  // the view preload turns an arbitrary web origin into a Hermes IPC caller.
  const host = await createEmbeddedHermesHostForTest(
    {
      assetRoot: '/tmp/hermes-artifact',
      hostWindow: {},
      userDataPath: '/tmp/rhythm-user-data',
      webContents: fakeContents()
    },
    { ipc: fakeIpc(), runtime: { connect: async () => ({ endpoint: 'http://127.0.0.1:43115', owned: false }) } }
  )

  const webPreferences: Record<string, unknown> = {
    contextIsolation: false,
    nodeIntegration: true,
    preload: '/tmp/hermes-artifact/electron/preload.cjs'
  }

  const params: Record<string, unknown> = { src: 'https://example.test/docs' }
  assert.equal(host.handleWillAttachWebview(webPreferences, params), true)
  assert.equal(params.partition, 'persist:hermes-embedded-101-preview')
  assert.deepEqual(webPreferences, {
    contextIsolation: true,
    nodeIntegration: false,
    preload: undefined,
    sandbox: true,
    webviewTag: false
  })

  // Desktop Browser creates its guest as about:blank, then calls into the
  // attached DOM guest to navigate. Rejecting this inert bootstrap leaves the
  // guest unattached and causes Electron's dom-ready load failure.
  const bootstrapPreferences: Record<string, unknown> = {
    contextIsolation: false,
    nodeIntegration: true,
    preload: '/tmp/hermes-artifact/electron/preload.cjs'
  }

  const bootstrapParams: Record<string, unknown> = { src: 'about:blank' }
  assert.equal(host.handleWillAttachWebview(bootstrapPreferences, bootstrapParams), true)
  assert.equal(bootstrapParams.partition, 'persist:hermes-embedded-101-preview')
  assert.deepEqual(bootstrapPreferences, {
    contextIsolation: true,
    nodeIntegration: false,
    preload: undefined,
    sandbox: true,
    webviewTag: false
  })
  assert.equal(host.handleGuestNavigation('http://127.0.0.1:56708'), true)
  assert.equal(host.handleGuestNavigation('https://example.test/docs'), true)
  assert.equal(host.handleGuestNavigation('about:blank'), false)
  assert.equal(host.handleWillAttachWebview({}, { src: 'file:///tmp/hermes-artifact/renderer/index.html' }), false)
  assert.equal(host.handleWillAttachWebview({}, { src: 'javascript:alert(1)' }), false)
  assert.equal(host.handleGuestNavigation('file:///tmp/hermes-artifact/renderer/index.html'), false)
  assert.equal(host.handleGuestNavigation('data:text/html,hello'), false)
  assert.equal(host.handleGuestNavigation('javascript:alert(1)'), false)
  assert.equal(host.handleWillAttachWebview({}, { partition: 'persist:rhythm', src: 'https://example.test/docs' }), false)
})
