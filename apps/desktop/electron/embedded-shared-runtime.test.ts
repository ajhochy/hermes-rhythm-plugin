import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { test, vi } from 'vitest'

const fixtures = vi.hoisted(() => {
  const noop = vi.fn()

  const showOpenDialog = vi.fn<(parent: unknown, options: unknown) => Promise<{ canceled: boolean; filePaths: string[] }>>(
    async () => ({ canceled: false, filePaths: ['/tmp/context.md'] })
  )

  return {
    hostHandlers: new Map<string, (event: unknown, ...args: any[]) => unknown>(),
    fixtureBinary: '',
    spawned: [] as any[],
    failStopOnSpawn: false,
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

vi.mock('node:child_process', async importOriginal => {
  const actual = await importOriginal<typeof import('node:child_process')>()
  return {
    ...actual,
    spawn: (...args: unknown[]) => {
      if (args[0] !== fixtures.fixtureBinary) {
        throw new Error('fixture blocked non-owned executable')
      }
      const child = (actual.spawn as (...items: unknown[]) => any)(...args)
      fixtures.spawned.push(child)
      if (fixtures.failStopOnSpawn) {
        child.originalKill = child.kill.bind(child)
        child.kill = () => true
      }
      return child
    }
  }
})

vi.mock('./gateway-ws-probe', () => ({ probeGatewayWebSocket: vi.fn(async () => ({ ok: true })) }))

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
    ipcMain: {
      handle: (channel: string, handler: (event: unknown, ...args: any[]) => unknown) => fixtures.hostHandlers.set(channel, handler),
      removeHandler: (channel: string) => fixtures.hostHandlers.delete(channel),
      on: fixtures.noop,
      removeListener: fixtures.noop
    },
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
import { createEmbeddedHermesHost, createEmbeddedIpcRegistrar } from './embedded-host'

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

async function exerciseRealEmbeddedConnection(withBroker: boolean, behavior: 'normal' | 'pending-dispose' | 'reject-accepted' | 'failed-stop' | 'reject-accepted-stop-fails' = 'normal') {
  // Catches the production-only bypass where the extracted Desktop runtime
  // starts its own child and never calls the host backendEnv/receipt seam.
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'hermes-real-ipc-receipt-'))
  const home = path.join(root, 'hermes-home')
  const bin = path.join(home, '.venv', 'bin')
  const userDataPath = path.join(root, 'user-data')
  const namesFile = path.join(root, 'owned-child-names.txt')
  fs.mkdirSync(bin, { recursive: true })
  fs.mkdirSync(userDataPath)
  fixtures.fixtureBinary = path.join(bin, 'hermes')
  fs.writeFileSync(fixtures.fixtureBinary, `#!${process.execPath}\nconst fs = require('node:fs')\nconst http = require('node:http')\nif (process.argv.includes('--version') || process.argv.includes('--help')) { console.log('fixture'); process.exit(0) }\nfs.writeFileSync(${JSON.stringify(namesFile)}, [...(process.env.OPENAI_API_KEY ? [process.env.OPENAI_API_KEY === 'fixture-only-key' ? 'OPENAI_BROKER_GRANTED' : 'OPENAI_UNEXPECTED'] : []), ...['HERMES_HOME','HERMES_PARENT_PID','HERMES_DESKTOP','HERMES_DASHBOARD_SESSION_TOKEN','HERMES_WEB_DIST'].filter(name => process.env[name])].join(','))\nconst server = http.createServer((request, response) => {\n  response.setHeader('content-type', request.url === '/' ? 'text/html' : 'application/json')\n  response.end(request.url === '/' ? '<html></html>' : '{}')\n})\nserver.listen(0, '127.0.0.1', () => {\n  console.log('HERMES_BACKEND_READY port=' + server.address().port)\n  if (process.env.OPENAI_API_KEY) {\n    process.stdout.write('synthetic-secret=' + process.env.OPENAI_API_KEY.slice(0, 8))\n    setTimeout(() => process.stdout.write(process.env.OPENAI_API_KEY.slice(8) + '\\n'), 5)\n  }\n})\n`)
  fs.chmodSync(fixtures.fixtureBinary, 0o755)
  const mainFrame = { url: 'file:///tmp/hermes-artifact/renderer/index.html?embedded=1' }
  const contents = {
    getURL: () => mainFrame.url,
    isDestroyed: () => false,
    mainFrame,
    on: vi.fn(),
    removeListener: vi.fn(),
    send: vi.fn(),
    session: { protocol: { handle: vi.fn(), unhandle: vi.fn() } }
  }
  const phases: string[] = []
  let releaseBroker: (() => void) | undefined
  const broker = vi.fn(() => behavior === 'pending-dispose'
    ? new Promise<Record<string, string>>(resolve => {releaseBroker = () => resolve({ OPENAI_API_KEY: 'fixture-only-key' })})
    : { OPENAI_API_KEY: 'fixture-only-key' })
  const oldAmbient = process.env.OPENAI_API_KEY
  const oldHermesOverride = process.env.HERMES_DESKTOP_HERMES
  let host: Awaited<ReturnType<typeof createEmbeddedHermesHost>> | undefined
  let restoreStop: (() => void) | undefined
  let expectedStickyFailure = false
  try {
    if (behavior === 'reject-accepted-stop-fails') {
      fixtures.failStopOnSpawn = true
      const actualProcessKill = process.kill.bind(process)
      const spy = vi.spyOn(process, 'kill').mockImplementation((pid: number, signal?: NodeJS.Signals | number) =>
        fixtures.spawned.some(child => child.pid === -pid) ? true : actualProcessKill(pid, signal))
      restoreStop = () => {
        spy.mockRestore()
        for (const child of fixtures.spawned) child.originalKill?.('SIGKILL')
      }
    }
    process.env.OPENAI_API_KEY = 'synthetic-ambient-must-not-inherit'
    process.env.HERMES_DESKTOP_HERMES = fixtures.fixtureBinary
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ version: 'fixture' }) })))
    host = await createEmbeddedHermesHost({
      assetRoot: '/tmp/hermes-artifact',
      ...(withBroker ? {
        backendEnv: broker,
        backendEnvContext: { serverOrigin: 'https://rhythm.example.test', rhythmUserId: 'synthetic-user', authGeneration: 'synthetic-generation' }
      } : {}),
      hermesHome: home,
      hostWindow: {},
      onOwnedBackendAttempt: event => {
        phases.push(event.phase)
        if ((behavior === 'reject-accepted' || behavior === 'reject-accepted-stop-fails') && event.phase === 'accepted') {throw new Error('fixture observer refused acceptance')}
      },
      userDataPath,
      webContents: contents
    })
    const handler = fixtures.hostHandlers.get('hermes:connection')
    assert.ok(handler, 'real native runtime must register hermes:connection')
    if (behavior === 'pending-dispose') {
      const connection = handler({ sender: contents, senderFrame: mainFrame })
      for (let count = 0; count < 200 && broker.mock.calls.length === 0; count++) {
        await new Promise(resolve => setTimeout(resolve, 5))
      }
      assert.equal(broker.mock.calls.length, 1)
      let stopped = false
      const disposing = host.dispose().then(() => {stopped = true})
      await new Promise(resolve => setTimeout(resolve, 20))
      assert.equal(stopped, false, 'native host disposal must await the pending broker')
      releaseBroker?.()
      await assert.rejects(Promise.resolve(connection), /disposed|no longer active/i)
      await disposing
      assert.deepEqual(phases, ['starting', 'retired'])
      assert.equal(fs.existsSync(namesFile), false, 'late broker resolution must not spawn a child')
      return
    }
    if (behavior === 'reject-accepted') {
      await assert.rejects(Promise.resolve(handler({ sender: contents, senderFrame: mainFrame })), /fixture observer refused acceptance/)
      assert.deepEqual(phases.slice(0, 2), ['starting', 'accepted'])
      assert.ok(phases.includes('retired'))
      assert.ok(fixtures.spawned.length > 0)
      const child = fixtures.spawned.at(-1)
      assert.ok(child.exitCode !== null || child.signalCode !== null, 'native failure cleanup must stop the exact spawned child')
      await host.dispose()
      return
    }
    if (behavior === 'reject-accepted-stop-fails') {
      await assert.rejects(Promise.resolve(handler({ sender: contents, senderFrame: mainFrame })), /could not be stopped|remained alive/)
      assert.ok(fixtures.spawned.at(-1)?.exitCode === null)
      const spawnedBeforeRetry = fixtures.spawned.length
      await assert.rejects(Promise.resolve(handler({ sender: contents, senderFrame: mainFrame })), /could not be stopped|remained alive/)
      assert.equal(fixtures.spawned.length, spawnedBeforeRetry, 'failed cleanup must block another owned spawn')
      await assert.rejects(host.dispose(), /could not be stopped|remained alive/)
      expectedStickyFailure = true
      return
    }
    await Promise.race([
      handler({ sender: contents, senderFrame: mainFrame }),
      new Promise((_, reject) => setTimeout(async () => {
        const progress = await fixtures.hostHandlers.get('hermes:boot-progress:get')?.({ sender: contents, senderFrame: mainFrame })
        const logs = await fixtures.hostHandlers.get('hermes:logs:recent')?.({ sender: contents, senderFrame: mainFrame })
        reject(new Error(`fixture connection stalled: ${JSON.stringify({ progress, logs })}`))
      }, 2500))
    ])
    assert.equal(broker.mock.calls.length, withBroker ? 1 : 0)
    assert.deepEqual(phases.slice(0, 2), ['starting', 'accepted'])
    for (let count = 0; count < 200 && (!fs.existsSync(namesFile) || (withBroker && !fs.readFileSync(namesFile, 'utf8').includes('OPENAI_BROKER_GRANTED'))); count++) {
      await new Promise(resolve => setTimeout(resolve, 10))
    }
    assert.deepEqual(fs.readFileSync(namesFile, 'utf8').trim().split(',').filter(Boolean), [
      ...(withBroker ? ['OPENAI_BROKER_GRANTED'] : []),
      'HERMES_HOME', 'HERMES_PARENT_PID', 'HERMES_DESKTOP', 'HERMES_DASHBOARD_SESSION_TOKEN', 'HERMES_WEB_DIST'
    ])
    if (behavior === 'failed-stop') {
      const child = fixtures.spawned.at(-1)
      assert.ok(child?.pid)
      const actualChildKill = child.kill.bind(child)
      const actualProcessKill = process.kill.bind(process)
      child.kill = () => true
      const spy = vi.spyOn(process, 'kill').mockImplementation((pid: number, signal?: NodeJS.Signals | number) =>
        pid === -child.pid ? true : actualProcessKill(pid, signal))
      restoreStop = () => {spy.mockRestore(); child.kill = actualChildKill; actualChildKill('SIGKILL')}
      await assert.rejects(host.dispose(), /remained alive after forced termination/)
      assert.equal(child.exitCode, null, 'failed stop must be surfaced while the owned child remains alive')
      await assert.rejects(host.dispose(), /remained alive after forced termination/, 'repeat disposal must retain the failed-stop result')
      expectedStickyFailure = true
      return
    }
    if (withBroker) {
      let logged = ''
      for (let count = 0; count < 100; count++) {
        const snapshot = await fixtures.hostHandlers.get('hermes:logs:recent')?.({ sender: contents, senderFrame: mainFrame }) as { lines?: string[] } | undefined
        logged = snapshot?.lines?.join('\n') || ''
        if (logged.includes('synthetic-secret=')) {break}
        await new Promise(resolve => setTimeout(resolve, 5))
      }
      assert.match(logged, /synthetic-secret=\[redacted\]/)
      assert.equal(logged.includes('fixture-only-key'), false, 'split child output must not leak the granted value')
      fs.mkdirSync(path.join(home, 'profiles', 'secondary'), { recursive: true })
      await handler({ sender: contents, senderFrame: mainFrame }, 'secondary')
      assert.equal(broker.mock.calls.length, 1, 'nondefault pool must not request a default grant')
      assert.deepEqual(phases.slice(0, 2), ['starting', 'accepted'])
      assert.deepEqual(fs.readFileSync(namesFile, 'utf8').trim().split(',').filter(Boolean), [
        'HERMES_HOME', 'HERMES_PARENT_PID', 'HERMES_DESKTOP', 'HERMES_DASHBOARD_SESSION_TOKEN', 'HERMES_WEB_DIST'
      ])
    }
  } finally {
    restoreStop?.()
    try {await host?.dispose()} catch (error) {if (!expectedStickyFailure) {throw error}}
    if (oldAmbient === undefined) delete process.env.OPENAI_API_KEY
    else process.env.OPENAI_API_KEY = oldAmbient
    if (oldHermesOverride === undefined) delete process.env.HERMES_DESKTOP_HERMES
    else process.env.HERMES_DESKTOP_HERMES = oldHermesOverride
    vi.unstubAllGlobals()
    fixtures.fixtureBinary = ''
    fixtures.failStopOnSpawn = false
    fixtures.spawned.length = 0
    fixtures.hostHandlers.clear()
    fs.rmSync(root, { recursive: true, force: true })
  }
}

test('issue-1569-s4-w5: real embedded hermes:connection uses the owned host receipt path', async () => {
  await exerciseRealEmbeddedConnection(true)
})

test('issue-1569-s4-w5: no-broker owned connection excludes synthetic ambient credential', async () => {
  await exerciseRealEmbeddedConnection(false)
})

test('issue-1569-s4-w7: real IPC disposal drains pending broker without a late child', async () => {
  await exerciseRealEmbeddedConnection(true, 'pending-dispose')
})

test('issue-1569-s4-w5: real IPC acceptance observer refusal stops the owned child', async () => {
  await exerciseRealEmbeddedConnection(true, 'reject-accepted')
})

test('issue-1569-s4-w6: real IPC failed stop remains an observable disposal failure', async () => {
  await exerciseRealEmbeddedConnection(true, 'failed-stop')
}, 20_000)

test('issue-1569-s4-w6: failed native adoption stop cannot clear owned failure before dispose', async () => {
  await exerciseRealEmbeddedConnection(true, 'reject-accepted-stop-fails')
}, 20_000)
