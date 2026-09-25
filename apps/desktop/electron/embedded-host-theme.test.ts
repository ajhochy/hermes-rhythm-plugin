import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { afterEach, test, vi } from 'vitest'

// RED first (#1543-b): the fork's shared Electron `nativeTheme` singleton and
// its persisted config file are process-global. Embedded Hermes (rendered
// inside Rhythm's WebContentsView) must never mutate either — that would
// repaint Rhythm's own window chrome, or scribble a Hermes-only file into the
// host's userData tree. Standalone Hermes keeps owning both, unchanged.

const fixtures = vi.hoisted(() => {
  const noop = vi.fn()
  const api = { on: noop, once: noop }

  return {
    listeners: new Map<string, (event: unknown, ...args: unknown[]) => void>(),
    nativeThemeApi: { themeSource: 'system' },
    noop,
    api
  }
})

vi.mock('electron', () => ({
  BrowserWindow: class {},
  Menu: fixtures.api,
  Notification: class {},
  app: {
    close: fixtures.noop,
    commandLine: { appendSwitch: fixtures.noop, getSwitchValue: () => '' },
    disableHardwareAcceleration: fixtures.noop,
    exit: fixtures.noop,
    getAppPath: () => '/tmp/hermes-artifact',
    getLocale: () => 'en-US',
    getPath: () => '/tmp/hermes-standalone-user-data',
    getVersion: () => '0.0.0-test',
    isPackaged: false,
    isReady: () => true,
    on: fixtures.noop,
    once: fixtures.noop,
    quit: fixtures.noop,
    relaunch: fixtures.noop,
    requestSingleInstanceLock: () => true,
    setAboutPanelOptions: fixtures.noop,
    setAppUserModelId: fixtures.noop,
    setAsDefaultProtocolClient: fixtures.noop,
    setName: fixtures.noop,
    setPath: fixtures.noop,
    showAboutPanel: fixtures.noop,
    whenReady: () => new Promise<void>(() => undefined)
  },
  clipboard: fixtures.api,
  dialog: { ...fixtures.api, showOpenDialog: vi.fn(async () => ({ canceled: true, filePaths: [] })) },
  globalShortcut: fixtures.api,
  ipcMain: {
    handle: fixtures.noop,
    on: (channel: string, listener: (event: unknown, ...args: unknown[]) => void) => {
      fixtures.listeners.set(channel, listener)
    },
    removeListener: fixtures.noop
  },
  nativeTheme: fixtures.nativeThemeApi,
  net: { fetch: fixtures.noop },
  powerMonitor: fixtures.api,
  powerSaveBlocker: fixtures.api,
  protocol: fixtures.api,
  safeStorage: fixtures.api,
  screen: fixtures.api,
  session: { defaultSession: fixtures.api, fromPartition: () => fixtures.api },
  shell: { openExternal: fixtures.noop, openPath: fixtures.noop, showItemInFolder: fixtures.noop, trashItem: fixtures.noop },
  systemPreferences: { askForMediaAccess: vi.fn(), getMediaAccessStatus: vi.fn(() => 'denied') },
  webContents: { getAllWebContents: () => [], getFocusedWebContents: () => null }
}))

vi.mock('./gateway-ws-probe', () => ({ probeGatewayWebSocket: vi.fn(async () => ({ ok: true })) }))

const { initializeDesktopNativeRuntime } = await import('./desktop-native-runtime')
const { EMBEDDED_HOST_API_VERSION, loadEmbeddedThemeFiles } = await import('./embedded-host')

const dummyAdapter = () => ({
  createOwnedPopout: vi.fn(),
  dispose: vi.fn(),
  getDialogWindow: () => null,
  getOwnedWebContents: () => [],
  getPartitionSession: vi.fn(),
  getRendererWebContents: () => null,
  listOwnedWindows: () => [],
  openExternal: vi.fn(),
  openInTerminal: vi.fn(),
  openInstance: vi.fn(),
  openSession: vi.fn()
})

const dummyBackend = () => ({ disposeOwned: vi.fn(), ensure: vi.fn(), gatewayWsUrl: vi.fn(), handleApi: vi.fn() })

afterEach(() => {
  fixtures.listeners.clear()
  fixtures.nativeThemeApi.themeSource = 'system'
})

test('embedded mode never mutates the shared nativeTheme singleton or writes native-theme.json into the host userData tree', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'hermes-embedded-native-theme-'))
  const hostUserData = path.join(root, 'rhythm-user-data')
  const scopedUserData = path.join(hostUserData, 'hermes-desktop')
  fs.mkdirSync(scopedUserData, { recursive: true })

  fixtures.nativeThemeApi.themeSource = 'untouched-sentinel'

  const runtime = initializeDesktopNativeRuntime({
    backend: dummyBackend(),
    mode: 'embedded',
    paths: { assetRoot: '/tmp/hermes-artifact', hermesHome: path.join(root, 'hermes-home'), userData: scopedUserData },
    windowAdapter: dummyAdapter() as never
  })

  // Merely creating the embedded runtime must not have pinned the host's
  // nativeTheme to whatever a persisted config (there is none here) implies.
  assert.equal(fixtures.nativeThemeApi.themeSource, 'untouched-sentinel')

  const listener = fixtures.listeners.get('hermes:native-theme')
  assert.ok(listener, 'the native-theme channel must still be registered (as a guarded no-op) in embedded mode')
  listener!({}, 'dark')

  assert.equal(fixtures.nativeThemeApi.themeSource, 'untouched-sentinel', 'embedded renderer must not repaint the host')
  assert.equal(
    fs.existsSync(path.join(hostUserData, 'native-theme.json')),
    false,
    'no native-theme.json anywhere under the host userData root'
  )
  assert.equal(
    fs.existsSync(path.join(scopedUserData, 'native-theme.json')),
    false,
    'no native-theme.json under the scoped Hermes userData subfolder either'
  )

  await runtime.dispose()
})

// Standalone regression coverage: the fix only wraps the existing standalone
// lines in `if (!embedded)` — it does not change their logic — and a full
// standalone boot needs a much larger Electron mock (protocol schemes,
// BrowserWindow, Menu, Tray, ...) unrelated to this fix. That surface is
// exercised by the broader electron test project; this file stays focused on
// the embedded isolation behavior actually introduced here.

// #1570-b: Rhythm's current pin (hermes-desktop-config.mjs) declares
// HERMES_DESKTOP_SUPPORTED_HOST_API_VERSIONS = [1]. This module's exported
// surface has not changed since that pin, so this must stay 1 -- bumping it
// requires a corresponding Rhythm-side config change, not just a fork release.
test('EMBEDDED_HOST_API_VERSION matches what Rhythm currently declares supported', () => {
  assert.equal(EMBEDDED_HOST_API_VERSION, 1)
})

test('loadEmbeddedThemeFiles returns [] when the artifact ships no themes/ folder', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'hermes-embedded-theme-files-'))
  assert.deepEqual(loadEmbeddedThemeFiles(root), [])
})

test('loadEmbeddedThemeFiles parses every *.json theme and skips a corrupted one without throwing', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'hermes-embedded-theme-files-'))
  const themesDir = path.join(root, 'themes')
  fs.mkdirSync(themesDir, { recursive: true })
  fs.writeFileSync(path.join(themesDir, 'example.json'), JSON.stringify({ name: 'example', colors: { primary: '#112233' } }))
  fs.writeFileSync(path.join(themesDir, 'corrupt.json'), '{ not valid json')
  fs.writeFileSync(path.join(themesDir, 'ignored.txt'), 'not a theme')

  const logged: string[] = []
  const themes = loadEmbeddedThemeFiles(root, line => logged.push(line))

  assert.deepEqual(themes, [{ name: 'example', colors: { primary: '#112233' } }])
  assert.ok(logged.some(line => line.includes('corrupt.json')), 'the corrupted file is logged, not silently dropped')
})

// A full createEmbeddedHermesHost() run needs the elaborate spawned-backend
// fixture in embedded-shared-runtime.test.ts (real child process, connection
// probing, ...), which is unrelated to this one-line wiring change. Pin the
// wiring directly instead: the metadata handler must read `options.defaultSkin`
// and route through `loadEmbeddedThemeFiles(options.assetRoot, ...)`, both of
// which are independently tested above.
test('the hermes:embedded:metadata handler wires defaultSkin and loadEmbeddedThemeFiles', () => {
  const source = fs.readFileSync(path.resolve(__dirname, 'embedded-host.ts'), 'utf8')
  const handlerStart = source.indexOf("scopedIpc.handle('hermes:embedded:metadata'")
  assert.ok(handlerStart !== -1, 'the metadata handler must still be registered')
  const handlerSource = source.slice(handlerStart, source.indexOf('}))', handlerStart) + 3)

  assert.match(handlerSource, /defaultSkin:\s*options\.defaultSkin/)
  assert.match(handlerSource, /themes:\s*loadEmbeddedThemeFiles\(options\.assetRoot/)
})

// Grep-style guard (#1543-b): these four files are the generic theme seam --
// they must stay usable by ANY embedding host, not just Rhythm. embedded-host.ts
// and the builder are pre-existing Rhythm-facing modules (their comments and
// option names like `rhythmUserId`/`host: 'rhythm'` predate this slice and are
// out of scope here), so this guard targets the NEW theme code specifically;
// context.tsx and user-themes.ts have zero pre-existing 'rhythm' references and
// are held to the stricter whole-file bar.
test('the generic theme seam has no hardcoded skin-name literal', () => {
  const desktopRoot = path.resolve(__dirname, '..')
  const contextTsx = fs.readFileSync(path.join(desktopRoot, 'src/themes/context.tsx'), 'utf8')
  const userThemesTs = fs.readFileSync(path.join(desktopRoot, 'src/themes/user-themes.ts'), 'utf8')
  assert.doesNotMatch(contextTsx, /rhythm/i)
  assert.doesNotMatch(userThemesTs, /rhythm/i)

  const embeddedHostTs = fs.readFileSync(path.join(desktopRoot, 'electron/embedded-host.ts'), 'utf8')
  const themeSeamSection = embeddedHostTs.slice(
    embeddedHostTs.indexOf('const THEMES_SUBDIR'),
    embeddedHostTs.indexOf('export function loadEmbeddedThemeFiles') + 2000
  )
  assert.doesNotMatch(themeSeamSection, /rhythm/i)

  const builderMjs = fs.readFileSync(path.join(desktopRoot, 'scripts/build-embedded-artifact.mjs'), 'utf8')
  const builderThemeSection = builderMjs.slice(
    builderMjs.indexOf('Generic theme JSON'),
    builderMjs.indexOf('rmSync(output')
  )
  assert.doesNotMatch(builderThemeSection, /rhythm/i)
})
