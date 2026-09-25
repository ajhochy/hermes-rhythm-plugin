import assert from 'node:assert/strict'
import type { ChildProcess } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { afterEach, test, vi } from 'vitest'

const fixture = vi.hoisted(() => ({
  handlers: new Map<string, unknown>(),
  initialize: vi.fn(),
  ready: vi.fn(async (_child?: ChildProcess) => 43123),
  websocket: vi.fn(async (): Promise<{ ok: boolean; reason?: string }> => ({ ok: true })),
  children: [] as Array<{ child: ChildProcess; kill: (signal?: NodeJS.Signals) => boolean }>
}))

vi.mock('node:child_process', async importOriginal => {
  const actual = await importOriginal<typeof import('node:child_process')>()
  return {
    ...actual,
    spawn: (...args: unknown[]) => {
      const child = (actual.spawn as (...items: unknown[]) => ChildProcess)(...args)
      fixture.children.push({ child, kill: child.kill.bind(child) })
      return child
    }
  }
})

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
vi.mock('./desktop-native-runtime', () => ({ initializeDesktopNativeRuntime: fixture.initialize }))
vi.mock('./backend-ready', () => ({ waitForDashboardPortAnnouncement: fixture.ready }))
vi.mock('./gateway-ws-probe', () => ({ probeGatewayWebSocket: fixture.websocket }))

import { createEmbeddedHermesHost, registerEmbeddedBackendRuntime } from './embedded-host'

type SpawnReceipt = {
  attemptId: string
  phase: 'starting' | 'accepted' | 'retired'
  profile: 'default'
  acceptedEnvNames: readonly string[]
}
type HostOptions = Parameters<typeof createEmbeddedHermesHost>[0] & {
  onOwnedBackendAttempt?: (receipt: SpawnReceipt) => void
}

const context = {
  serverOrigin: 'https://rhythm.example.test',
  rhythmUserId: 'synthetic-user',
  authGeneration: 'opaque-synthetic-generation'
}
const roots: string[] = []

afterEach(async () => {
  fixture.handlers.clear()
  fixture.initialize.mockReset()
  fixture.ready.mockReset().mockResolvedValue(43123)
  fixture.websocket.mockReset().mockResolvedValue({ ok: true })
  vi.unstubAllGlobals()
  for (const record of fixture.children.splice(0)) {
    if (record.child.exitCode === null && record.child.signalCode === null) {
      try { record.kill('SIGTERM') } catch { /* already exited */ }
      await Promise.race([
        new Promise(resolve => record.child.once('exit', resolve)),
        new Promise(resolve => setTimeout(resolve, 250))
      ])
    }
  }
  for (const root of roots.splice(0)) {
    fs.rmSync(root, { recursive: true, force: true })
  }
})

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}

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

function makeFixture() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'hermes-spawn-receipt-'))
  roots.push(root)
  const home = path.join(root, 'home')
  const userDataPath = path.join(root, 'user-data')
  const bin = path.join(home, '.venv', 'bin')
  const namesFile = path.join(root, 'child-env-names.txt')
  const pidFile = path.join(root, 'child.pid')
  fs.mkdirSync(bin, { recursive: true })
  fs.mkdirSync(userDataPath)
  const hermes = path.join(bin, 'hermes')
  // This real, owned child records only variable names and waits for host stop.
  fs.writeFileSync(hermes, `#!/bin/sh\necho $$ > '${pidFile}'\n: > '${namesFile}'\nfor name in OPENAI_API_KEY OPENROUTER_API_KEY ANTHROPIC_API_KEY GOOGLE_API_KEY; do\n  if printenv "$name" >/dev/null 2>&1; then echo "$name" >> '${namesFile}'; fi\ndone\nexec sleep 30\n`)
  fs.chmodSync(hermes, 0o755)
  return { home, namesFile, pidFile, userDataPath }
}

async function mount(options: Partial<HostOptions> = {}, nativeDispose = vi.fn(async () => undefined)) {
  const files = makeFixture()
  fixture.initialize.mockReturnValue({ dispose: nativeDispose })
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ version: 'fixture' }) })))
  const host = await createEmbeddedHermesHost({
    assetRoot: '/tmp/hermes-artifact',
    hermesHome: fs.realpathSync(files.home),
    hostWindow: {},
    userDataPath: files.userDataPath,
    webContents: contents(),
    backendEnvContext: context,
    ...options
  } as HostOptions)
  const initialized = fixture.initialize.mock.calls.at(-1)?.[0] as {
    backend: { ensure: (profile?: string) => Promise<unknown> }
  }
  return { ...files, host, ensure: initialized.backend.ensure }
}

async function waitForFile(file: string) {
  for (let count = 0; count < 200 && !fs.existsSync(file); count++) {
    await new Promise(resolve => setTimeout(resolve, 10))
  }
  assert.ok(fs.existsSync(file), 'synthetic owned child did not execute')
}

async function waitForText(file: string, expected: string) {
  for (let count = 0; count < 200; count++) {
    if (fs.existsSync(file) && fs.readFileSync(file, 'utf8').includes(expected)) {return}
    await new Promise(resolve => setTimeout(resolve, 10))
  }
  assert.fail(`synthetic child did not record expected variable name: ${expected}`)
}

test('issue-1569-s4-w5: actual owned child receipts report only filtered names after host acceptance', async () => {
  // A backendEnv resolution without a spawn used to look applied to Accounts.
  const gate = deferred<Record<string, string>>()
  const brokerEntered = deferred<void>()
  const receipts: SpawnReceipt[] = []
  const { host, ensure, namesFile } = await mount({
    backendEnv: () => { brokerEntered.resolve(); return gate.promise },
    onOwnedBackendAttempt: event => receipts.push(event)
  })
  const starting = ensure('default')
  try {
    await brokerEntered.promise
    assert.deepEqual(receipts.map(event => event.phase), ['starting'])
    assert.equal(fs.existsSync(namesFile), false)
    gate.resolve({ OPENAI_API_KEY: 'synthetic-accepted-key', OPENROUTER_API_KEY: 'invalid\nkey' })
    await starting
    await waitForText(namesFile, 'OPENAI_API_KEY')
    assert.deepEqual(fs.readFileSync(namesFile, 'utf8').trim().split('\n'), ['OPENAI_API_KEY'])
    assert.deepEqual(receipts.map(event => event.phase), ['starting', 'accepted'])
    assert.equal(receipts[1].attemptId, receipts[0].attemptId)
    assert.deepEqual(receipts[1].acceptedEnvNames, ['OPENAI_API_KEY'])
    assert.ok(!JSON.stringify(receipts).includes('synthetic-accepted-key'))
  } finally {
    gate.resolve({})
    await starting.catch(() => undefined)
    await host.dispose()
  }
  assert.deepEqual(receipts.map(event => event.phase), ['starting', 'accepted', 'retired'])
})

test('issue-1569-s4-w5: borrowed and nondefault connections emit no credential attempt', async () => {
  const receipts: SpawnReceipt[] = []
  const broker = vi.fn(() => ({ OPENAI_API_KEY: 'synthetic-key' }))
  const hostWindow = {}
  const unregister = registerEmbeddedBackendRuntime(hostWindow, {
    connect: async profile => ({ endpoint: 'http://127.0.0.1:43123', owned: false, profile })
  })
  const borrowed = await mount({ hostWindow, backendEnv: broker, onOwnedBackendAttempt: event => receipts.push(event) })
  await borrowed.ensure('default')
  await borrowed.host.dispose()
  unregister()
  const nondefault = await mount({ backendEnv: broker, onOwnedBackendAttempt: event => receipts.push(event) })
  await nondefault.ensure('work')
  await nondefault.host.dispose()
  assert.equal(broker.mock.calls.length, 0)
  assert.deepEqual(receipts, [])
})

test('issue-1569-s4-w5: a real child spawn error never reports accepted credentials', async () => {
  const receipts: SpawnReceipt[] = []
  const { host, ensure, home } = await mount({
    backendEnv: () => ({ OPENAI_API_KEY: 'synthetic-key' }),
    onOwnedBackendAttempt: event => receipts.push(event)
  })
  const executable = path.join(home, '.venv', 'bin', 'hermes')
  fs.writeFileSync(executable, '#!/definitely-missing-fixture-interpreter\n')
  fs.chmodSync(executable, 0o755)
  fixture.ready.mockImplementationOnce(child => new Promise<number>((_resolve, reject) => {
    child.once('error', reject)
  }))
  await assert.rejects(ensure('default'))
  assert.deepEqual(receipts.map(event => event.phase), ['starting', 'retired'])
  assert.equal(receipts.some(event => event.phase === 'accepted'), false)
  await host.dispose()
})

test('issue-1569-s4-w5: broker timeout and late resolution never apply a key', async () => {
  // A late promise must not turn an already-started uncredentialed child into
  // an applied grant in the main-process lifecycle ledger.
  const gate = deferred<Record<string, string>>()
  const receipts: SpawnReceipt[] = []
  const { host, ensure, namesFile } = await mount({
    backendEnv: () => gate.promise,
    onOwnedBackendAttempt: event => receipts.push(event)
  })
  await ensure('default') // bounded production broker deadline is two seconds
  await waitForFile(namesFile)
  assert.equal(fs.readFileSync(namesFile, 'utf8'), '')
  const accepted = receipts.filter(event => event.phase === 'accepted')
  assert.ok(accepted.every(event => event.acceptedEnvNames.length === 0))
  gate.resolve({ OPENAI_API_KEY: 'too-late-synthetic-key' })
  await Promise.resolve()
  assert.ok(receipts.filter(event => event.phase === 'accepted').every(event => event.acceptedEnvNames.length === 0))
  assert.equal(fs.readFileSync(namesFile, 'utf8'), '')
  await host.dispose()
})

test('issue-1569-s4-w5: a throwing starting observer prevents broker request and spawn', async () => {
  const broker = vi.fn(() => ({ OPENAI_API_KEY: 'synthetic-key' }))
  const priorChildren = fixture.children.length
  const { host, ensure } = await mount({
    backendEnv: broker,
    onOwnedBackendAttempt: event => {
      if (event.phase === 'starting') throw new Error('synthetic observer unavailable')
    }
  })
  try {
    await assert.rejects(ensure('default'))
    assert.equal(broker.mock.calls.length, 0)
    assert.equal(fixture.children.length, priorChildren)
  } finally {
    await host.dispose()
  }
})

test('issue-1569-s4-w5: a throwing accepted observer stops child before publishing connection', async () => {
  const receipts: SpawnReceipt[] = []
  const { host, ensure } = await mount({
    backendEnv: () => ({ OPENAI_API_KEY: 'synthetic-key' }),
    onOwnedBackendAttempt: event => {
      receipts.push(event)
      if (event.phase === 'accepted') throw new Error('synthetic ledger refusal')
    }
  })
  try {
    await assert.rejects(ensure('default'))
    const child = fixture.children.at(-1)?.child
    assert.ok(child, 'actual child must have been spawned before acceptance')
    assert.ok(child.exitCode !== null || child.signalCode !== null, 'refused child must be stopped')
    assert.equal(receipts.filter(event => event.phase === 'accepted').length, 1)
    assert.equal(receipts.filter(event => event.phase === 'retired').length, 1)
  } finally {
    await host.dispose()
  }
})

test('issue-1569-s4-w6: failed attempt, retry, and ordinary exit retire distinct attempts', async () => {
  // A cached successful connection after child exit must never retain applied state.
  const receipts: SpawnReceipt[] = []
  fixture.websocket.mockResolvedValueOnce({ ok: false, reason: 'fixture probe failure' }).mockResolvedValue({ ok: true })
  const { host, ensure, namesFile, pidFile } = await mount({
    backendEnv: () => ({ OPENAI_API_KEY: 'synthetic-key' }),
    onOwnedBackendAttempt: event => receipts.push(event)
  })
  await assert.rejects(ensure('default'), /WebSocket/)
  assert.deepEqual(receipts.map(event => event.phase), ['starting', 'retired'])
  await ensure('default')
  assert.equal(fixture.children.length, 2, 'retry must create a second owned child')
  await waitForFile(namesFile)
  const accepted = receipts.filter(event => event.phase === 'accepted')
  assert.equal(accepted.length, 1)
  assert.notEqual(accepted[0].attemptId, receipts[0].attemptId)
  await waitForFile(pidFile)
  const child = fixture.children.at(-1)
  assert.ok(child, 'owned child was not tracked')
  child.kill('SIGTERM')
  await new Promise(resolve => setTimeout(resolve, 30))
  assert.equal(receipts.filter(event => event.attemptId === accepted[0].attemptId && event.phase === 'retired').length, 1)
  const childrenBeforeRetry = fixture.children.length
  await ensure('default')
  assert.equal(fixture.children.length, childrenBeforeRetry + 1, 'a dead owned child must not be reused')
  const later = receipts.filter(event => event.phase === 'accepted').at(-1)
  assert.ok(later)
  assert.notEqual(later.attemptId, accepted[0].attemptId)
  await host.dispose()
})

test('issue-1569-s4-w7: disposal waits for pending broker and prevents late accepted receipt', async () => {
  // A fast dispose could admit a new identity before the old broker resolved and spawned.
  const gate = deferred<Record<string, string>>()
  const brokerEntered = deferred<void>()
  const receipts: SpawnReceipt[] = []
  const { host, ensure, namesFile } = await mount({
    backendEnv: () => { brokerEntered.resolve(); return gate.promise },
    onOwnedBackendAttempt: event => receipts.push(event)
  })
  const pending = ensure('default')
  pending.catch(() => undefined)
  try {
    await brokerEntered.promise
    let settled = false
    const disposing = host.dispose().then(() => { settled = true })
    await new Promise(resolve => setTimeout(resolve, 20))
    assert.equal(settled, false, 'dispose must wait for an in-flight owned attempt')
    gate.resolve({ OPENAI_API_KEY: 'late-synthetic-key' })
    await disposing
    await assert.rejects(pending, /disposed/)
    assert.equal(receipts.some(event => event.phase === 'accepted'), false)
    assert.equal(receipts.filter(event => event.phase === 'retired').length, 1)
    if (fs.existsSync(namesFile)) assert.ok(!fs.readFileSync(namesFile, 'utf8').includes('late-synthetic-key'))
  } finally {
    gate.resolve({})
    await pending.catch(() => undefined)
    await host.dispose()
  }
})

test('issue-1569-s4-w7: failed owned-child stop propagates instead of claiming retirement', async () => {
  const receipts: SpawnReceipt[] = []
  const { host, ensure } = await mount({
    backendEnv: () => ({ OPENAI_API_KEY: 'synthetic-key' }),
    onOwnedBackendAttempt: event => receipts.push(event)
  })
  await ensure('default')
  const child = fixture.children.at(-1)?.child
  assert.ok(child)
  child.kill = () => { throw new Error('synthetic stop failure') }
  await assert.rejects(host.dispose(), /stop|failure|unavailable/i)
  assert.equal(receipts.filter(event => event.phase === 'retired').length, 0)
})

test('issue-1569-s4-w7: native runtime teardown failure still stops the owned credential child', async () => {
  const receipts: SpawnReceipt[] = []
  const nativeDispose = vi.fn(async () => { throw new Error('synthetic native teardown failure') })
  const { host, ensure } = await mount({
    backendEnv: () => ({ OPENAI_API_KEY: 'synthetic-key' }),
    onOwnedBackendAttempt: event => receipts.push(event)
  }, nativeDispose)
  await ensure('default')
  await assert.rejects(host.dispose(), /synthetic native teardown failure/)
  const child = fixture.children.at(-1)?.child
  assert.ok(child)
  assert.ok(child.exitCode !== null || child.signalCode !== null, 'owned child must stop despite native teardown error')
  assert.equal(receipts.filter(event => event.phase === 'retired').length, 1)
})
