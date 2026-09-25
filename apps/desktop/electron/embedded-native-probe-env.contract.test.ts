import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { test, vi } from 'vitest'

const fixture = vi.hoisted(() => ({
  executable: '',
  handlers: new Map<string, (event: unknown, ...args: any[]) => unknown>(),
  noop: () => undefined
}))

vi.mock('node:child_process', async importOriginal => {
  const actual = await importOriginal<typeof import('node:child_process')>()
  return {
    ...actual,
    spawn: (...args: unknown[]) => {
      if (args[0] === fixture.executable) {throw new Error('fixture stops before long-lived backend spawn')}
      throw new Error('fixture blocked unexpected backend executable')
    }
  }
})

vi.mock('electron', () => {
  const api = { on: fixture.noop, once: fixture.noop }
  return {
    BrowserWindow: class {}, Menu: api, Notification: class {},
    app: {
      commandLine: { appendSwitch: fixture.noop, getSwitchValue: () => '' },
      getAppPath: () => '/tmp/synthetic-hermes-artifact',
      getPath: () => '/tmp/synthetic-rhythm-data',
      isPackaged: false, on: fixture.noop, once: fixture.noop,
      requestSingleInstanceLock: () => true, setPath: fixture.noop,
      whenReady: () => new Promise<void>(() => undefined)
    },
    clipboard: api, dialog: { ...api, showOpenDialog: async () => ({ canceled: true, filePaths: [] }) },
    globalShortcut: api,
    ipcMain: { handle: (channel: string, handler: (event: unknown, ...args: any[]) => unknown) => fixture.handlers.set(channel, handler), on: fixture.noop },
    nativeTheme: api, net: { fetch: fixture.noop }, powerMonitor: api,
    powerSaveBlocker: api, protocol: api, safeStorage: api, screen: api,
    session: { defaultSession: api, fromPartition: () => api }, shell: api,
    systemPreferences: api,
    webContents: { getAllWebContents: () => [], getFocusedWebContents: () => null }
  }
})

import { initializeDesktopNativeRuntime } from './desktop-native-runtime'

test('embedded native resolver version and serve-support helpers receive no ambient credential, proxy, or loader env', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'hermes-native-probe-contract-'))
  const bin = path.join(root, 'bin')
  const home = path.join(root, 'hermes-home')
  const versionNames = path.join(root, 'version-names')
  const serveNames = path.join(root, 'serve-names')
  fs.mkdirSync(bin)
  fs.mkdirSync(home)
  fixture.executable = path.join(bin, 'hermes')
  const capture = (target: string) => `: > '${target}'\n[ -n "$OPENAI_API_KEY" ] && echo OPENAI_API_KEY >> '${target}'\n[ -n "$ANTHROPIC_API_KEY" ] && echo ANTHROPIC_API_KEY >> '${target}'\n[ -n "$HTTPS_PROXY" ] && echo HTTPS_PROXY >> '${target}'\n[ -n "$NODE_OPTIONS" ] && echo NODE_OPTIONS >> '${target}'\n[ -n "$NODE_PATH" ] && echo NODE_PATH >> '${target}'\n[ -n "$HERMES_DASHBOARD_SESSION_TOKEN" ] && echo HERMES_DASHBOARD_SESSION_TOKEN >> '${target}'\n`
  fs.writeFileSync(fixture.executable, `#!/bin/sh\nif [ "$1" = '--version' ]; then\n${capture(versionNames)}exit 0\nfi\n${capture(serveNames)}exit 0\n`)
  fs.chmodSync(fixture.executable, 0o755)
  const keys = ['PATH', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'HTTPS_PROXY', 'NODE_OPTIONS', 'NODE_PATH', 'HERMES_DASHBOARD_SESSION_TOKEN', 'HERMES_DESKTOP_HERMES'] as const
  const before = Object.fromEntries(keys.map(key => [key, process.env[key]]))
  let probeCalls = 0
  let runtime: ReturnType<typeof initializeDesktopNativeRuntime> | undefined
  try {
    process.env.PATH = `${bin}:/usr/bin:/bin`
    process.env.OPENAI_API_KEY = 'synthetic-credential-never-forward'
    process.env.ANTHROPIC_API_KEY = 'synthetic-credential-never-forward'
    process.env.HTTPS_PROXY = 'http://synthetic-proxy.invalid:9999'
    process.env.NODE_OPTIONS = '--synthetic-loader-option'
    process.env.NODE_PATH = '/synthetic-loader'
    process.env.HERMES_DASHBOARD_SESSION_TOKEN = 'synthetic-dashboard-token-never-forward'
    delete process.env.HERMES_DESKTOP_HERMES
    const contents = { getURL: () => 'file:///tmp/synthetic-hermes-artifact/renderer/index.html', isDestroyed: () => false, send: fixture.noop }
    runtime = initializeDesktopNativeRuntime({
      mode: 'embedded', paths: { assetRoot: '/tmp/synthetic-hermes-artifact', hermesHome: home, userData: path.join(root, 'user-data') },
      backend: { ensure: async () => null, gatewayWsUrl: async () => null, handleApi: async () => null, disposeOwned: fixture.noop },
      ownedSpawn: {
        probeEnv: () => {
          probeCalls += 1
          return { PATH: `${bin}:/usr/bin:/bin`, HOME: root, HERMES_HOME: home }
        },
        prepare: async () => { throw new Error('fixture stops before long-lived backend spawn') }
      },
      windowAdapter: {
        getRendererWebContents: () => contents, getDialogWindow: () => null,
        getPartitionSession: () => null, getOwnedWebContents: () => [], listOwnedWindows: () => [],
        openSession: fixture.noop, openInstance: fixture.noop, openInTerminal: fixture.noop,
        openExternal: fixture.noop, createOwnedPopout: fixture.noop, dispose: fixture.noop
      }
    })
    const connect = fixture.handlers.get('hermes:connection')
    assert.ok(connect)
    await assert.rejects(Promise.resolve(connect({})), /fixture stops before long-lived backend spawn/)
    assert.ok(fs.existsSync(versionNames), 'the actual resolver must run the synthetic --version helper')
    assert.ok(fs.existsSync(serveNames), 'the actual resolver must run the synthetic serve --help helper')
    assert.equal(fs.readFileSync(versionNames, 'utf8'), '')
    assert.equal(fs.readFileSync(serveNames, 'utf8'), '')
    assert.equal(probeCalls, 3, 'each resolver helper must use one host-supplied environment snapshot')
  } finally {
    await runtime?.dispose()
    fixture.handlers.clear()
    fixture.executable = ''
    for (const [key, value] of Object.entries(before)) {
      if (value === undefined) delete process.env[key]
      else process.env[key] = value
    }
    fs.rmSync(root, { recursive: true, force: true })
  }
}, 10_000)
