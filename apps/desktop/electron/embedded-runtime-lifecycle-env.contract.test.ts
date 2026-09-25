import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { test, vi } from 'vitest'

const fixture = vi.hoisted(() => ({
  blockRuntimeSpawns: false,
  handlers: new Map<string, (event: unknown, ...args: any[]) => unknown>(),
  noop: () => undefined,
  runtimeSpawnAttempts: 0
}))

vi.mock('node:child_process', async importOriginal => {
  const actual = await importOriginal<typeof import('node:child_process')>()

  return {
    ...actual,
    spawn: (...args: Parameters<typeof actual.spawn>) => {
      if (fixture.blockRuntimeSpawns) {
        fixture.runtimeSpawnAttempts += 1
        throw new Error('embedded runtime lifecycle fixture blocked a child spawn')
      }

      return actual.spawn(...args)
    }
  }
})

vi.mock('electron', () => {
  const api = { on: fixture.noop, once: fixture.noop }

  return {
    BrowserWindow: class {},
    Menu: api,
    Notification: class {},
    app: {
      commandLine: { appendSwitch: fixture.noop, getSwitchValue: () => '' },
      getAppPath: () => '/tmp/synthetic-hermes-artifact',
      getPath: (name: string) => (name === 'temp' ? os.tmpdir() : '/tmp/synthetic-rhythm-data'),
      getVersion: () => '0.0.0-test',
      isPackaged: false,
      on: fixture.noop,
      once: fixture.noop,
      quit: fixture.noop,
      requestSingleInstanceLock: () => true,
      setPath: fixture.noop,
      whenReady: () => new Promise<void>(() => undefined)
    },
    clipboard: api,
    dialog: { ...api, showOpenDialog: async () => ({ canceled: true, filePaths: [] }) },
    globalShortcut: api,
    ipcMain: {
      handle: (channel: string, handler: (event: unknown, ...args: any[]) => unknown) =>
        fixture.handlers.set(channel, handler),
      on: fixture.noop
    },
    nativeTheme: api,
    net: { fetch: fixture.noop },
    powerMonitor: api,
    powerSaveBlocker: api,
    protocol: api,
    safeStorage: api,
    screen: api,
    session: { defaultSession: api, fromPartition: () => api },
    shell: api,
    systemPreferences: api,
    webContents: { getAllWebContents: () => [], getFocusedWebContents: () => null }
  }
})

import { runBootstrap } from './bootstrap-runner'
import { initializeDesktopNativeRuntime } from './desktop-native-runtime'

const HOSTILE_KEYS = [
  'OPENAI_API_KEY',
  'ANTHROPIC_API_KEY',
  'HTTPS_PROXY',
  'NODE_OPTIONS',
  'NODE_PATH',
  'PYTHONPATH',
  'HERMES_DASHBOARD_SESSION_TOKEN'
] as const

async function withHostileAmbient<T>(body: () => T | Promise<T>): Promise<T> {
  const previous = Object.fromEntries(HOSTILE_KEYS.map(key => [key, process.env[key]]))

  try {
    for (const key of HOSTILE_KEYS) process.env[key] = `synthetic-${key.toLowerCase()}`

    return await body()
  } finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key]
      else process.env[key] = value
    }
  }
}

test('embedded first-run bootstrap subprocesses derive from the host clean base without ambient credentials or loaders', async () => {
  // Regression caught: bootstrap-runner spread process.env into both manifest
  // and stage children even when the embedded host supplied an isolated base.
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'hermes-embedded-bootstrap-env-'))
  const sourceRoot = path.join(root, 'source')
  const scripts = path.join(sourceRoot, 'scripts')
  const bin = path.join(root, 'bin')
  const observed = path.join(root, 'observed-names')
  const gitObserved = path.join(root, 'git-observed-names')
  const home = path.join(root, 'home')
  const activeRoot = path.join(root, 'active')
  fs.mkdirSync(scripts, { recursive: true })
  fs.mkdirSync(bin)
  fs.mkdirSync(home)
  fs.mkdirSync(activeRoot)
  const installer = path.join(scripts, 'install.sh')
  const capture = `
[ -n "$OPENAI_API_KEY" ] && echo OPENAI_API_KEY >> '${observed}'
[ -n "$ANTHROPIC_API_KEY" ] && echo ANTHROPIC_API_KEY >> '${observed}'
[ -n "$HTTPS_PROXY" ] && echo HTTPS_PROXY >> '${observed}'
[ -n "$NODE_OPTIONS" ] && echo NODE_OPTIONS >> '${observed}'
[ -n "$NODE_PATH" ] && echo NODE_PATH >> '${observed}'
[ -n "$HERMES_DASHBOARD_SESSION_TOKEN" ] && echo HERMES_DASHBOARD_SESSION_TOKEN >> '${observed}'
[ "$PATH" = '${bin}:/usr/bin:/bin' ] && echo CLEAN_PATH >> '${observed}'
[ "$PYTHONPATH" = '/synthetic/clean-pythonpath' ] && echo CLEAN_PYTHONPATH >> '${observed}'
[ "$PYTHONUTF8" = '1' ] && echo PYTHONUTF8 >> '${observed}'
[ "$HERMES_HOME" = '${home}' ] && echo HERMES_HOME >> '${observed}'
`
  fs.writeFileSync(
    installer,
    `#!/bin/sh
${capture}
case " $* " in
  *" --manifest "*) echo '{"stages":[{"name":"install"}]}' ;;
  *) echo '{"ok":true,"stage":"install"}' ;;
esac
`
  )
  fs.chmodSync(installer, 0o755)
  const git = path.join(bin, 'git')
  fs.writeFileSync(
    git,
    `#!/bin/sh
: > '${gitObserved}'
[ -n "$OPENAI_API_KEY" ] && echo OPENAI_API_KEY >> '${gitObserved}'
[ -n "$ANTHROPIC_API_KEY" ] && echo ANTHROPIC_API_KEY >> '${gitObserved}'
[ -n "$HTTPS_PROXY" ] && echo HTTPS_PROXY >> '${gitObserved}'
[ -n "$NODE_OPTIONS" ] && echo NODE_OPTIONS >> '${gitObserved}'
[ -n "$NODE_PATH" ] && echo NODE_PATH >> '${gitObserved}'
[ -n "$HERMES_DASHBOARD_SESSION_TOKEN" ] && echo HERMES_DASHBOARD_SESSION_TOKEN >> '${gitObserved}'
[ "$PATH" = '${bin}:/usr/bin:/bin' ] && echo CLEAN_PATH >> '${gitObserved}'
[ "$PYTHONPATH" = '/synthetic/clean-pythonpath' ] && echo CLEAN_PYTHONPATH >> '${gitObserved}'
[ "$PYTHONUTF8" = '1' ] && echo PYTHONUTF8 >> '${gitObserved}'
[ "$HERMES_HOME" = '${home}' ] && echo HERMES_HOME >> '${gitObserved}'
echo '${'b'.repeat(40)}'
`
  )
  fs.chmodSync(git, 0o755)

  try {
    const result = await withHostileAmbient(() =>
      runBootstrap({
        installStamp: { branch: 'main', commit: '0'.repeat(40) },
        activeRoot,
        sourceRepoRoot: sourceRoot,
        hermesHome: home,
        logRoot: path.join(home, 'logs'),
        baseEnv: {
          HOME: root,
          HERMES_HOME: home,
          PATH: `${bin}:/usr/bin:/bin`,
          PYTHONPATH: '/synthetic/clean-pythonpath',
          PYTHONUTF8: '1'
        },
        writeMarker: value => value
      })
    )

    assert.equal(result.ok, true)
    assert.equal(result.marker?.pinnedCommit, 'b'.repeat(40))
    assert.deepEqual(fs.readFileSync(observed, 'utf8').trim().split('\n'), [
      'CLEAN_PATH',
      'CLEAN_PYTHONPATH',
      'PYTHONUTF8',
      'HERMES_HOME',
      'CLEAN_PATH',
      'CLEAN_PYTHONPATH',
      'PYTHONUTF8',
      'HERMES_HOME'
    ])
    assert.deepEqual(fs.readFileSync(gitObserved, 'utf8').trim().split('\n'), [
      'CLEAN_PATH',
      'CLEAN_PYTHONPATH',
      'PYTHONUTF8',
      'HERMES_HOME'
    ])
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})

test('embedded update and uninstall IPC remain unavailable before any child spawn', async () => {
  // Rhythm owns the embedded runtime. A regression that re-enables Desktop's
  // updater/uninstaller reaches the child-process boundary and fails here.
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'hermes-embedded-lifecycle-refusal-'))
  const home = path.join(root, 'home')
  fs.mkdirSync(home)
  const contents = {
    getURL: () => 'file:///tmp/synthetic-hermes-artifact/renderer/index.html',
    isDestroyed: () => false,
    send: fixture.noop
  }
  fixture.blockRuntimeSpawns = true
  fixture.runtimeSpawnAttempts = 0
  let runtime: ReturnType<typeof initializeDesktopNativeRuntime> | undefined

  try {
    runtime = initializeDesktopNativeRuntime({
      mode: 'embedded',
      paths: { assetRoot: '/tmp/synthetic-hermes-artifact', hermesHome: home, userData: path.join(root, 'user-data') },
      backend: {
        ensure: async () => null,
        gatewayWsUrl: async () => null,
        handleApi: async () => null,
        disposeOwned: fixture.noop
      },
      ownedSpawn: {
        probeEnv: () => ({ HOME: root, HERMES_HOME: home, PATH: '/usr/bin:/bin', PYTHONUTF8: '1' }),
        prepare: async () => {
          throw new Error('fixture stops before long-lived backend spawn')
        }
      },
      windowAdapter: {
        getRendererWebContents: () => contents,
        getDialogWindow: () => null,
        getPartitionSession: () => null,
        getOwnedWebContents: () => [],
        listOwnedWindows: () => [],
        openSession: fixture.noop,
        openInstance: fixture.noop,
        openInTerminal: fixture.noop,
        openExternal: fixture.noop,
        createOwnedPopout: fixture.noop,
        dispose: fixture.noop
      }
    })

    assert.equal(fixture.handlers.has('hermes:updates:apply'), false)
    assert.equal(fixture.handlers.has('hermes:connections:update-all'), false)
    assert.equal(fixture.handlers.has('hermes:uninstall:summary'), false)
    assert.equal(fixture.handlers.has('hermes:uninstall:run'), false)
    assert.equal(fixture.runtimeSpawnAttempts, 0)
  } finally {
    fixture.blockRuntimeSpawns = false
    fixture.handlers.clear()
    await runtime?.dispose()
    fs.rmSync(root, { recursive: true, force: true })
  }
})
