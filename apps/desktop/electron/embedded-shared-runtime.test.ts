import assert from 'node:assert/strict'

import { test, vi } from 'vitest'

const fixtures = vi.hoisted(() => {
  const noop = vi.fn()

  const showOpenDialog = vi.fn<(parent: unknown, options: unknown) => Promise<{ canceled: boolean; filePaths: string[] }>>(
    async () => ({ canceled: false, filePaths: ['/tmp/context.md'] })
  )

  return {
    hostApp: {
      commandLine: { appendSwitch: noop, getSwitchValue: () => '' },
      getAppPath: () => '/tmp/hermes-artifact',
      getPath: () => '/tmp/rhythm-user-data',
      isPackaged: false,
      on: noop,
      once: noop,
      requestSingleInstanceLock: () => true,
      setPath: noop,
      whenReady: () => new Promise<void>(() => undefined)
    },
    noop,
    showOpenDialog
  }
})

vi.mock('electron', () => {
  const api = { on: fixtures.noop, once: fixtures.noop }

  return {
    BrowserWindow: class {},
    Menu: api,
    Notification: class {},
    app: fixtures.hostApp,
    clipboard: api,
    dialog: { ...api, showOpenDialog: fixtures.showOpenDialog },
    globalShortcut: api,
    ipcMain: { handle: fixtures.noop, on: fixtures.noop },
    nativeTheme: api,
    net: { fetch: fixtures.noop },
    powerMonitor: api,
    powerSaveBlocker: api,
    protocol: api,
    safeStorage: api,
    screen: api,
    session: { defaultSession: api, fromPartition: () => api },
    shell: { openExternal: fixtures.noop, openPath: fixtures.noop, showItemInFolder: fixtures.noop, trashItem: fixtures.noop },
    systemPreferences: { askForMediaAccess: vi.fn(), getMediaAccessStatus: vi.fn(() => 'denied') },
    webContents: { getAllWebContents: () => [], getFocusedWebContents: () => null }
  }
})

import { initializeDesktopNativeRuntime } from './desktop-native-runtime'
import { createEmbeddedIpcRegistrar } from './embedded-host'

const { hostApp } = fixtures

function rawIpc() {
  const handlers = new Map<string, (event: unknown, ...args: any[]) => unknown>()
  const listeners = new Map<string, (event: unknown, ...args: any[]) => void>()

  return {
    handlers,
    listeners,
    handle: (channel: string, handler: (event: unknown, ...args: any[]) => unknown) => handlers.set(channel, handler),
    on: (channel: string, listener: (event: unknown, ...args: any[]) => void) => listeners.set(channel, listener),
    removeHandler: (channel: string) => handlers.delete(channel),
    removeListener: (channel: string) => listeners.delete(channel)
  }
}

test('shared native runtime registers ordinary Desktop services only through the embedded view registrar', async () => {
  // This is the integration boundary: the real extracted runtime must retain
  // the existing fs service, while the host registrar excludes Rhythm's shell.
  const ipc = rawIpc()
  const mainFrame = { url: 'file:///tmp/hermes-artifact/renderer/index.html?embedded=1' }

  const contents = {
    getURL: () => mainFrame.url,
    isDestroyed: () => false,
    mainFrame,
    send: vi.fn(),
    session: { protocol: { handle: vi.fn(), unhandle: vi.fn() } }
  }

  const registrar = createEmbeddedIpcRegistrar(ipc, contents, '/tmp/hermes-artifact')
  const dialogParent = { isDestroyed: () => false, kind: 'rhythm-dialog-parent' }

  const adapter = {
    createOwnedPopout: vi.fn(),
    dispose: vi.fn(),
    getDialogWindow: () => dialogParent,
    getOwnedWebContents: () => [],
    getPartitionSession: vi.fn(),
    getRendererWebContents: () => contents,
    listOwnedWindows: () => [],
    openExternal: vi.fn(),
    openInTerminal: vi.fn(),
    openInstance: vi.fn(),
    openSession: vi.fn()
  }

  const runtime = initializeDesktopNativeRuntime({
    app: hostApp as never,
    backend: { disposeOwned: vi.fn(), ensure: vi.fn(), gatewayWsUrl: vi.fn(), handleApi: vi.fn() },
    ipc: registrar as never,
    mode: 'embedded',
    paths: { assetRoot: '/tmp/hermes-artifact', hermesHome: '/tmp/hermes-home', userData: '/tmp/rhythm-user-data/hermes-desktop' },
    windowAdapter: adapter
  })

  const readDir = ipc.handlers.get('hermes:fs:readDir')
  assert.ok(readDir, 'the shared runtime must retain the real fs bridge')
  assert.throws(
    () => readDir!({ sender: { id: 'rhythm-shell' }, senderFrame: mainFrame }, '/tmp'),
    /untrusted embedded Hermes IPC sender/
  )

  const selectPaths = ipc.handlers.get('hermes:selectPaths')
  assert.ok(selectPaths, 'the shared runtime must retain the real native file picker')
  assert.deepEqual(
    await selectPaths!({ sender: contents, senderFrame: mainFrame }, { directories: true }),
    ['/tmp/context.md']
  )
  assert.equal(fixtures.showOpenDialog.mock.calls[0]?.[0], dialogParent)

  await runtime.dispose()
  await registrar.dispose()
})
