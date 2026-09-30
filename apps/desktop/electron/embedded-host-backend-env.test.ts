import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { PassThrough } from 'node:stream'

import { afterAll, afterEach, test, vi } from 'vitest'

const fixtures = vi.hoisted(() => ({
  handlers: new Map<string, unknown>(),
  initialize: vi.fn(),
  ipcMain: {
    handle: vi.fn((channel: string, handler: unknown) => fixtures.handlers.set(channel, handler)),
    removeHandler: vi.fn((channel: string) => fixtures.handlers.delete(channel)),
    on: vi.fn(),
    removeListener: vi.fn()
  },
  spawn: vi.fn()
}))

vi.mock('electron', () => ({
  BrowserWindow: class {},
  ipcMain: fixtures.ipcMain,
  session: { fromPartition: vi.fn(() => ({})) },
  shell: { openPath: vi.fn(), showItemInFolder: vi.fn(), trashItem: vi.fn() },
  systemPreferences: { askForMediaAccess: vi.fn(), getMediaAccessStatus: vi.fn(() => 'denied') }
}))

vi.mock('node:child_process', () => ({ spawn: fixtures.spawn }))
vi.mock('./desktop-native-runtime', () => ({ initializeDesktopNativeRuntime: fixtures.initialize }))
vi.mock('./backend-ready', () => ({ waitForDashboardPortAnnouncement: vi.fn(async () => 43123) }))
vi.mock('./gateway-ws-probe', () => ({ probeGatewayWebSocket: vi.fn(async () => ({ ok: true })) }))

import { createEmbeddedHermesHost, registerEmbeddedBackendRuntime } from './embedded-host'

type HostOptions = Partial<Parameters<typeof createEmbeddedHermesHost>[0]>

const backendEnvContext = {
  serverOrigin: 'https://rhythm.example.test',
  rhythmUserId: 'synthetic-user-1569',
  authGeneration: 'opaque-generation-1569'
}
const fixtureHome = fs.mkdtempSync(path.join(os.tmpdir(), 'hermes-1569-owned-'))
const fixtureUserData = fs.mkdtempSync(path.join(os.tmpdir(), 'hermes-1569-user-data-'))
afterAll(() => {
  fs.rmSync(fixtureHome, { recursive: true, force: true })
  fs.rmSync(fixtureUserData, { recursive: true, force: true })
})

const mutatedEnvironment = [
  'PATH',
  'HOME',
  'TMPDIR',
  'TMP',
  'TEMP',
  'LANG',
  'LC_ALL',
  'DYLD_INSERT_LIBRARIES',
  'LD_PRELOAD',
  'NODE_OPTIONS',
  'PYTHONPATH',
  'HTTP_PROXY',
  'HUMAN_APPROVAL_X',
  'RHYTHM_RELAY_BEARER',
  'RHYTHM_TEST_PARENT_SECRET'
]
const savedEnvironment = new Map(mutatedEnvironment.map(key => [key, process.env[key]]))

afterEach(() => {
  for (const key of mutatedEnvironment) {
    const saved = savedEnvironment.get(key)
    if (saved === undefined) delete process.env[key]
    else process.env[key] = saved
  }
  fixtures.handlers.clear()
  fixtures.initialize.mockReset()
  fixtures.spawn.mockReset()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

function fakeChild() {
  const child = new EventEmitter() as EventEmitter & {
    exitCode: number | null
    signalCode: NodeJS.Signals | null
    kill: ReturnType<typeof vi.fn>
    stdout: PassThrough
    stderr: PassThrough
  }
  child.exitCode = null
  child.signalCode = null
  child.stdout = new PassThrough()
  child.stderr = new PassThrough()
  child.kill = vi.fn(() => {
    child.exitCode = 0
    child.emit('exit', 0, null)
    return true
  })
  return child
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

async function startOwnedBackend(options: HostOptions, profile = 'default', onSpawn?: () => void) {
  const child = fakeChild()
  fixtures.spawn.mockImplementationOnce(() => {
    onSpawn?.()
    return child
  })
  fixtures.initialize.mockReturnValue({ dispose: vi.fn(async () => undefined) })
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok: true, json: async () => ({ version: 'fixture' }) }))
  )
  const host = await createEmbeddedHermesHost({
    assetRoot: '/tmp/hermes-artifact',
    hermesHome: fs.realpathSync(fixtureHome),
    hostWindow: {},
    userDataPath: fixtureUserData,
    webContents: contents(),
    backendEnvContext,
    ...options
  })
  const initialized = fixtures.initialize.mock.calls.at(-1)?.[0] as {
    backend: { ensure: (profile?: string) => Promise<unknown> }
  }
  await initialized.backend.ensure(profile)
  return {
    child,
    host,
    spawnOptions: fixtures.spawn.mock.calls.at(-1)?.[2] as { env: NodeJS.ProcessEnv }
  }
}

test('issue-1569-s3-c1: owned spawn uses a clean controlled environment and only filtered broker keys', async () => {
  // Catches regressions that spread process.env into Hermes or accept callback
  // values as arbitrary child variables instead of applying the host allowlist.
  const ambientBin = path.join(fixtureUserData, 'ambient-bin')
  fs.mkdirSync(ambientBin, { recursive: true })
  const ambientHermes = path.join(ambientBin, process.platform === 'win32' ? 'hermes.exe' : 'hermes')
  fs.writeFileSync(ambientHermes, 'synthetic executable')
  fs.chmodSync(ambientHermes, 0o755)
  process.env.PATH = ambientBin
  process.env.HOME = 'parent-home-sentinel'
  process.env.TMPDIR = 'parent-temp-sentinel'
  process.env.TMP = 'parent-temp-sentinel'
  process.env.TEMP = 'parent-temp-sentinel'
  process.env.LANG = 'parent-locale-sentinel'
  process.env.LC_ALL = 'parent-locale-sentinel'
  process.env.DYLD_INSERT_LIBRARIES = 'loader-sentinel'
  process.env.LD_PRELOAD = 'loader-sentinel'
  process.env.NODE_OPTIONS = '--require=loader-sentinel'
  process.env.PYTHONPATH = 'python-injection-sentinel'
  process.env.HTTP_PROXY = 'proxy-credential-sentinel'
  process.env.HUMAN_APPROVAL_X = 'approval-sentinel'
  process.env.RHYTHM_RELAY_BEARER = 'relay-sentinel'
  process.env.RHYTHM_TEST_PARENT_SECRET = 'ambient-secret-sentinel'
  const key = 'synthetic-openrouter-key-1569'
  const backendEnv = vi.fn(() => ({
    OPENROUTER_API_KEY: key,
    ANTHROPIC_API_KEY: 'synthetic-anthropic-key',
    OPENAI_API_KEY: 'synthetic-openai-key',
    GOOGLE_API_KEY: 'synthetic-google-key',
    RHYTHM_AGENT_URL: 'http://127.0.0.1:49321',
    PATH: 'callback-path-sentinel',
    HOME: 'callback-home-sentinel',
    HERMES_HOME: 'callback-hermes-home-sentinel',
    HERMES_DASHBOARD_SESSION_TOKEN: 'callback-session-token-sentinel',
    HERMES_DESKTOP: 'callback-desktop-sentinel',
    DYLD_INSERT_LIBRARIES: 'callback-loader-sentinel',
    NODE_OPTIONS: '--require=callback-loader-sentinel',
    HUMAN_APPROVAL_X: 'callback-approval-sentinel',
    RHYTHM_RELAY_BEARER: 'callback-relay-sentinel',
    HTTP_PROXY: 'callback-proxy-sentinel',
    RANDOM_SECRET: 'callback-arbitrary-secret-sentinel'
  }))

  const { host, spawnOptions } = await startOwnedBackend({ backendEnv })
  const env = spawnOptions.env

  assert.equal(backendEnv.mock.calls.length, 1)
  const request = (backendEnv.mock.calls as unknown[][])[0]?.[0]
  assert.deepEqual(request, {
    ...backendEnvContext,
    profile: 'default',
    hermesHome: fs.realpathSync(fixtureHome),
    source: 'opencode-auth-json'
  })
  assert.equal(env.OPENROUTER_API_KEY, key)
  assert.equal(env.ANTHROPIC_API_KEY, 'synthetic-anthropic-key')
  assert.equal(env.OPENAI_API_KEY, 'synthetic-openai-key')
  assert.equal(env.GOOGLE_API_KEY, 'synthetic-google-key')
  assert.equal(env.RHYTHM_AGENT_URL, undefined, 'memory search requires an authenticated ephemeral capability')
  assert.notEqual(env.PATH, ambientBin)
  assert.notEqual(fixtures.spawn.mock.calls.at(-1)?.[0], ambientHermes, 'binary resolution must ignore ambient PATH')
  assert.notEqual(env.PATH, 'callback-path-sentinel')
  assert.ok(env.PATH)
  assert.notEqual(env.HOME, 'parent-home-sentinel')
  assert.notEqual(env.HOME, 'callback-home-sentinel')
  assert.ok(env.HOME)
  assert.ok(env.TMPDIR || env.TMP || env.TEMP)
  assert.notEqual(env.TMPDIR, 'parent-temp-sentinel')
  assert.notEqual(env.LANG, 'parent-locale-sentinel')
  assert.ok(env.LANG || env.LC_ALL)
  assert.equal(env.HERMES_HOME, fs.realpathSync(fixtureHome))
  assert.ok(env.HERMES_DASHBOARD_SESSION_TOKEN)
  assert.notEqual(env.HERMES_DASHBOARD_SESSION_TOKEN, 'callback-session-token-sentinel')
  assert.equal(env.HERMES_DESKTOP, '1')
  for (const name of [
    'DYLD_INSERT_LIBRARIES',
    'LD_PRELOAD',
    'NODE_OPTIONS',
    'PYTHONPATH',
    'HTTP_PROXY',
    'HUMAN_APPROVAL_X',
    'RHYTHM_RELAY_BEARER',
    'RHYTHM_TEST_PARENT_SECRET',
    'RANDOM_SECRET'
  ])
    assert.equal(env[name], undefined, `${name} must not reach the child`)

  await host.dispose()
})

test('issue-1569-s3-c2: throwing or slow broker fails closed at the two-second deadline', async () => {
  // Catches a broker outage either blocking Hermes indefinitely or leaking a
  // partial/untrusted delta into the child after failure.
  const observations: Array<{ called: number; env: NodeJS.ProcessEnv; logs: string[] }> = []
  for (const failureMode of ['throw', 'timeout']) {
    vi.useFakeTimers()
    const earlierSpawns = fixtures.spawn.mock.calls.length
    const logs: string[] = []
    const backendEnv = vi.fn(() => {
      if (failureMode === 'throw') throw new Error('private callback exception synthetic sentinel')
      return new Promise<Record<string, string>>(() => undefined)
    })
    const starting = startOwnedBackend(
      {
        backendEnv: backendEnv as HostOptions['backendEnv'],
        log: line => logs.push(line)
      }
    )
    if (failureMode === 'timeout') {
      await vi.advanceTimersByTimeAsync(1_999)
      assert.equal(fixtures.spawn.mock.calls.length, earlierSpawns, 'broker deadline has not elapsed')
      await vi.advanceTimersByTimeAsync(1)
    } else {
      await vi.advanceTimersByTimeAsync(2_000)
    }
    const { host, spawnOptions } = await starting
    observations.push({
      called: backendEnv.mock.calls.length,
      env: spawnOptions.env,
      logs
    })
    await host.dispose()
    vi.useRealTimers()
  }
  for (const observation of observations) {
    assert.equal(observation.called, 1, 'owned default spawn must consult the broker')
    assert.ok(observation.logs.every(line => !line.includes('private callback exception synthetic sentinel')))
    for (const name of [
      'OPENROUTER_API_KEY',
      'ANTHROPIC_API_KEY',
      'OPENAI_API_KEY',
      'GOOGLE_API_KEY',
      'RHYTHM_AGENT_URL'
    ]) {
      assert.equal(observation.env[name], undefined, `${name} must be absent after broker failure`)
    }
  }
})

test('issue-1569-s3-c3: borrowed and non-default runtimes never call the broker', async () => {
  // Catches credential injection into a process Rhythm did not start or into a
  // profile outside the frozen default-profile grant scope.
  fixtures.initialize.mockReturnValue({ dispose: vi.fn(async () => undefined) })
  const hostWindow = {}
  const backendEnv = vi.fn(() => ({ OPENROUTER_API_KEY: 'synthetic-key' }))
  const unregister = registerEmbeddedBackendRuntime(hostWindow, {
    connect: async profile => ({ endpoint: 'http://127.0.0.1:43124', owned: false, profile })
  })
  const host = await createEmbeddedHermesHost({
    assetRoot: '/tmp/hermes-artifact',
    backendEnv,
    backendEnvContext,
    hostWindow,
    userDataPath: fixtureUserData,
    webContents: contents()
  })
  const initialized = fixtures.initialize.mock.calls.at(-1)?.[0] as {
    backend: { ensure: (profile?: string) => Promise<unknown> }
  }
  await initialized.backend.ensure('default')
  assert.equal(backendEnv.mock.calls.length, 0)
  await host.dispose()
  unregister()

  const discoveredHome = fs.mkdtempSync(path.join(os.tmpdir(), 'hermes-1569-discovered-'))
  fs.writeFileSync(
    path.join(discoveredHome, 'embedded-runtime.json'),
    JSON.stringify({
      schemaVersion: 1,
      baseUrl: 'http://127.0.0.1:43125',
      profile: 'default',
      token: 'synthetic-borrowed-session-token',
      wsUrl: 'ws://127.0.0.1:43125/api/ws'
    })
  )
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok: true, json: async () => ({ version: 'fixture' }) }))
  )
  fixtures.initialize.mockReturnValue({ dispose: vi.fn(async () => undefined) })
  const discoveredHost = await createEmbeddedHermesHost({
    assetRoot: '/tmp/hermes-artifact',
    backendEnv,
    backendEnvContext,
    hermesHome: discoveredHome,
    hostWindow: {},
    userDataPath: fixtureUserData,
    webContents: contents()
  })
  const discoveredInit = fixtures.initialize.mock.calls.at(-1)?.[0] as {
    backend: { ensure: (profile?: string) => Promise<unknown> }
  }
  await discoveredInit.backend.ensure('default')
  assert.equal(backendEnv.mock.calls.length, 0)
  assert.equal(fixtures.spawn.mock.calls.length, 0)
  await discoveredHost.dispose()
  fs.rmSync(discoveredHome, { recursive: true, force: true })

  const nonDefault = await startOwnedBackend({ backendEnv }, 'work')
  assert.equal(backendEnv.mock.calls.length, 0)
  assert.equal(fixtures.spawn.mock.calls.at(-1)?.[1]?.[0], '--profile')
  await nonDefault.host.dispose()
})

test('issue-1569-s3-c4: injected values are redacted from child output in host logs', async () => {
  // Catches credential disclosure when Hermes logs a brokered key to either
  // output stream, including values returned by the real callback boundary.
  const value = 'synthetic-secret-to-redact-1569'
  const logs: string[] = []
  const { child, host } = await startOwnedBackend({
    backendEnv: () => ({ OPENROUTER_API_KEY: value }),
    log: line => logs.push(line)
  })
  child.stderr.write(`provider configured with ${value}\n`)
  await new Promise(resolve => setImmediate(resolve))
  assert.ok(logs.some(line => line.includes('[redacted]')))
  assert.ok(logs.every(line => !line.includes(value)))
  child.stdout.write(`split ${value.slice(0, 13)}`)
  child.stdout.write(`${value.slice(13)} after\n`)
  await new Promise(resolve => setImmediate(resolve))
  assert.ok(logs.every(line => !line.includes(value) && !line.includes(value.slice(0, 13))))
  await host.dispose()
})

test('issue-1569-s3-c4: a UTF-8 credential split between child output chunks is redacted', async () => {
  const value = 'päss-synthetic-key'
  const logs: string[] = []
  const { child, host } = await startOwnedBackend({
    backendEnv: () => ({ OPENROUTER_API_KEY: value }),
    log: line => logs.push(line)
  })
  const output = Buffer.from(`credential ${value}`)
  const cut = output.indexOf(0xc3) + 1
  child.stdout.write(output.subarray(0, cut))
  child.stdout.end(output.subarray(cut))
  await new Promise(resolve => setImmediate(resolve))
  assert.ok(logs.some(line => line.includes('credential [redacted]')), 'final line without newline must be flushed')
  assert.ok(logs.every(line => !line.includes(value) && !line.includes('p��ss-synthetic-key')))
  await host.dispose()
})

test('issue-1569-s3-c4: overlapping granted values are fully redacted from child output', async () => {
  const logs: string[] = []
  const { child, host } = await startOwnedBackend({
    backendEnv: () => ({ OPENROUTER_API_KEY: 'abc', ANTHROPIC_API_KEY: 'abcdef' }),
    log: line => logs.push(line)
  })
  child.stderr.end('credential abcdef\n')
  await new Promise(resolve => setImmediate(resolve))
  assert.ok(logs.some(line => line.includes('credential [redacted]')))
  assert.ok(logs.every(line => !line.includes('abcdef') && !line.includes('[redacted]def')))
  await host.dispose()
})

test('issue-1569-s3-c4: token-shaped text inside a grant cannot prevent full redaction', async () => {
  const value = 'grant-prefix?token=inner-value&grant-suffix'
  const logs: string[] = []
  const { child, host } = await startOwnedBackend({
    backendEnv: () => ({ OPENROUTER_API_KEY: value }),
    log: line => logs.push(line)
  })
  child.stderr.end(`credential ${value}`)
  await new Promise(resolve => setImmediate(resolve))
  assert.ok(logs.some(line => line.includes('credential [redacted]')))
  assert.ok(logs.every(line => !line.includes('grant-prefix') && !line.includes('grant-suffix')))
  await host.dispose()
})

test('issue-1569-s3-c5: missing identity context prevents broker invocation', async () => {
  const backendEnv = vi.fn(() => ({ OPENROUTER_API_KEY: 'synthetic-key' }))
  const { host, spawnOptions } = await startOwnedBackend({ backendEnv, backendEnvContext: undefined })
  assert.equal(backendEnv.mock.calls.length, 0)
  assert.equal(spawnOptions.env.OPENROUTER_API_KEY, undefined)
  await host.dispose()
})

test('issue-1569-s3-c6: malformed values and a throwing result cannot partially inject grants', async () => {
  const malformed = await startOwnedBackend({
    backendEnv: () => ({
      OPENROUTER_API_KEY: 'bad\u0000value',
      ANTHROPIC_API_KEY: 'x'.repeat(4097),
      OPENAI_API_KEY: 'valid-synthetic-key'
    })
  })
  assert.equal(malformed.spawnOptions.env.OPENROUTER_API_KEY, undefined)
  assert.equal(malformed.spawnOptions.env.ANTHROPIC_API_KEY, undefined)
  assert.equal(malformed.spawnOptions.env.OPENAI_API_KEY, 'valid-synthetic-key')
  await malformed.host.dispose()

  const logs: string[] = []
  const throwing = await startOwnedBackend({
    backendEnv: () => Object.defineProperty({ OPENROUTER_API_KEY: 'partial-synthetic-key' }, 'OPENAI_API_KEY', {
      get() { throw new Error('private synthetic getter failure') }
    }),
    log: line => logs.push(line)
  })
  assert.equal(throwing.spawnOptions.env.OPENROUTER_API_KEY, undefined)
  assert.ok(logs.every(line => !line.includes('private synthetic getter failure')))
  await throwing.host.dispose()
})
