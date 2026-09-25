import { type ChildProcess, spawn } from 'node:child_process'
// Native runtime for the Desktop renderer when Rhythm owns the Electron app.
//
// This deliberately does not import main.ts: main.ts acquires the single-instance
// lock, owns the app menu/updater, and installs global IPC handlers.  An embedded
// view shares Rhythm's Electron process, so every native capability below is
// registered against the one view and torn down with that view instead.
import crypto from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { StringDecoder } from 'node:string_decoder'
import { pathToFileURL } from 'node:url'

import { ipcMain, systemPreferences } from 'electron'

import { waitForDashboardPortAnnouncement } from './backend-ready'
import type { DesktopRuntimeWindowAdapter } from './desktop-native-runtime'
import { probeGatewayWebSocket } from './gateway-ws-probe'

export interface EmbeddedWebContents {
  id?: number
  mainFrame?: unknown
  getURL: () => string
  isDestroyed: () => boolean
  send?: (channel: string, payload: unknown) => void
  on?: (channel: string, listener: (...args: any[]) => void) => void
  removeListener?: (channel: string, listener: (...args: any[]) => void) => void
  /** The isolated Electron session belonging to this WebContentsView. */
  session?: unknown
}

export interface EmbeddedHermesHostOptions {
  hostWindow: unknown
  webContents: EmbeddedWebContents
  assetRoot: string
  userDataPath: string
  hermesHome?: string
  log?: (line: string) => void
  /** Trusted main-process identity, never supplied by the renderer. */
  backendEnvContext?: { serverOrigin: string; rhythmUserId: string; authGeneration: string }
  /** Ephemeral grant values for a Rhythm-owned default-profile backend only. */
  backendEnv?: (request: {
    serverOrigin: string
    rhythmUserId: string
    profile: 'default'
    hermesHome: string
    source: 'opencode-auth-json' | 'memory-search'
    authGeneration: string
  }) => Promise<Record<string, string>> | Record<string, string>
  /** Main-only observation of one owned default-profile spawn attempt. */
  onOwnedBackendAttempt?: (event: OwnedBackendAttemptEvent) => void
  /** A Rhythm-owned, user-visible microphone/camera consent prompt. */
  mediaConsent?: (request: EmbeddedPermissionRequest) => Promise<boolean> | boolean
  /** Rhythm's narrowly supplied external-browser action (usually shell.openExternal). */
  openExternal?: (url: string) => Promise<void> | void
}

export type BrokeredKeyName = 'OPENROUTER_API_KEY' | 'ANTHROPIC_API_KEY' | 'OPENAI_API_KEY' | 'GOOGLE_API_KEY'

export type OwnedBackendAttemptEvent =
  | { attemptId: string; phase: 'starting'; profile: 'default'; acceptedEnvNames: readonly [] }
  | { attemptId: string; phase: 'accepted'; profile: 'default'; acceptedEnvNames: readonly BrokeredKeyName[] }
  | { attemptId: string; phase: 'retired'; profile: 'default'; acceptedEnvNames: readonly []; cause: 'failed' | 'exited' | 'disposed' }

export interface EmbeddedPermissionRequest {
  permission: string
  /** Electron's `details.requestingUrl`; query and fragment are permitted. */
  requestingUrl?: string
  /** Transitional alias for callers using the initial contract wording. */
  requestingOrigin?: string
  /** Optional extra assertion supplied by a caller that exposes frame details. */
  isMainFrame?: boolean
  /** Only the microphone's exact audio request is eligible. */
  mediaTypes?: unknown
}

export interface EmbeddedGuestWebPreferences {
  contextIsolation?: unknown
  nodeIntegration?: unknown
  preload?: unknown
  sandbox?: unknown
  webviewTag?: unknown
  [key: string]: unknown
}

export interface EmbeddedGuestParams {
  partition?: unknown
  src?: unknown
}

export interface EmbeddedBackendConnection {
  baseUrl?: string
  connectionId?: string
  endpoint: string
  logs?: string[]
  mode?: 'local' | 'remote'
  owned: boolean
  profile?: string
  stop?: () => Promise<void> | void
  token?: string
  wsUrl?: string
}

export interface EmbeddedRuntime {
  connect: (profile?: string) => Promise<EmbeddedBackendConnection>
}

export interface EmbeddedHermesHost {
  dispose: () => Promise<void>
  /** Exact backend origins validated by this host; never derived from renderer input. */
  getAllowedOrigins: () => Promise<string[]>
  onAllowedOrigins: (callback: (origins: string[]) => void) => () => void
  /** Explicitly grants only a main-frame audio request after host UI consent. */
  handlePermissionRequest: (request: EmbeddedPermissionRequest) => Promise<boolean>
  /** Sanitizes a Desktop Browser guest before Electron attaches it to this view. */
  handleWillAttachWebview: (webPreferences: EmbeddedGuestWebPreferences, params: EmbeddedGuestParams) => boolean
  /** Allows only remote HTTP(S) navigation after the inert guest bootstrap. */
  handleGuestNavigation: (url: string) => boolean
  /** Opens a guest popup through Rhythm's bounded external-browser policy. */
  handleGuestWindowOpen: (url: string) => Promise<boolean>
  handleIntent: (intent: unknown) => Promise<{ ok: boolean; reason?: string }>
}

export interface EmbeddedIpc {
  handle: (channel: string, handler: (event: unknown, ...args: any[]) => unknown) => void
  on?: (channel: string, listener: (event: unknown, ...args: any[]) => void) => void
  removeHandler: (channel: string) => void
  removeListener?: (channel: string, listener: (event: unknown, ...args: any[]) => void) => void
}

export interface EmbeddedHostTestDeps {
  ipc?: EmbeddedIpc
  runtime?: EmbeddedRuntime
  /** Tests exercise the minimal bridge directly; production delegates it to the shared native runtime. */
  registerCoreBridge?: boolean
}

// Rhythm can register a backend it has already authenticated and compatibility-
// checked. This avoids guessing ownership from a health endpoint and ensures an
// embedded tab never kills a service it did not start.
const hostRuntimes = new WeakMap<object, EmbeddedRuntime>()
const hostConnectors = new WeakMap<object, (profile?: string) => Promise<EmbeddedBackendConnection>>()
const hostDescriptorRecorders = new WeakMap<object, (connection: unknown) => void>()

export function registerEmbeddedBackendRuntime(hostWindow: object, runtime: EmbeddedRuntime): () => void {
  hostRuntimes.set(hostWindow, runtime)

  return () => {
    if (hostRuntimes.get(hostWindow) === runtime) {
      hostRuntimes.delete(hostWindow)
    }
  }
}

const PROFILE_RE = /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/
const EMBEDDED_RUNTIME_MANIFEST = 'embedded-runtime.json'

function logLine(log: EmbeddedHermesHostOptions['log'], line: string) {
  log?.(`[embedded-host] ${line}`)
}

function trustedDocumentUrl(assetRoot: string): URL {
  return new URL(pathToFileURL(path.join(assetRoot, 'renderer', 'index.html')).toString())
}

function isTrustedEmbeddedSender(event: any, contents: EmbeddedWebContents, expectedUrl: URL): boolean {
  if (!event || event.sender !== contents || contents.isDestroyed()) {
    return false
  }

  // Electron exposes the document frame separately from the WebContents. A
  // same-process iframe must not inherit the main renderer's native authority.
  if (!contents.mainFrame || event.senderFrame !== contents.mainFrame) {
    return false
  }

  try {
    const frameUrl = typeof event.senderFrame?.url === 'string' ? event.senderFrame.url : contents.getURL()
    const actual = new URL(frameUrl)

    return actual.protocol === 'file:' && actual.pathname === expectedUrl.pathname
  } catch {
    return false
  }
}

function isTrustedEmbeddedDocumentUrl(rawUrl: string, expectedUrl: URL): boolean {
  try {
    const actual = new URL(rawUrl)

    return actual.protocol === 'file:' && actual.pathname === expectedUrl.pathname
  } catch {
    return false
  }
}

async function boundedMediaConsent(
  consent: NonNullable<EmbeddedHermesHostOptions['mediaConsent']>,
  request: EmbeddedPermissionRequest
): Promise<boolean> {
  let timeout: ReturnType<typeof setTimeout> | undefined

  try {
    return await Promise.race([
      Promise.resolve(consent(request)).then(Boolean, () => false),
      new Promise<boolean>(resolve => {
        timeout = setTimeout(() => resolve(false), 30_000)
      })
    ])
  } finally {
    if (timeout) {clearTimeout(timeout)}
  }
}

async function requestMicrophoneConsent(options: EmbeddedHermesHostOptions, request: EmbeddedPermissionRequest): Promise<boolean> {
  if (options.mediaConsent) {return boundedMediaConsent(options.mediaConsent, request)}

  // The renderer has already made the explicit microphone gesture. On macOS
  // ask the OS directly (or retain an existing grant); other platforms still
  // present Chromium/OS capture consent after the scoped session decision.
  if (process.platform !== 'darwin') {return true}

  try {
    const status = systemPreferences?.getMediaAccessStatus?.('microphone')

    if (status === 'granted') {return true}

    if (status === 'denied' || status === 'restricted') {return false}

    return await systemPreferences.askForMediaAccess('microphone')
  } catch {
    return false
  }
}

export function createEmbeddedIpcRegistrar(ipc: EmbeddedIpc, contents: EmbeddedWebContents, assetRoot: string) {
  const channels = new Set<string>()
  const listeners: Array<{ channel: string; listener: (event: unknown, ...args: any[]) => void }> = []
  const expectedUrl = trustedDocumentUrl(assetRoot)

  const documents = new Map<
    EmbeddedWebContents,
    {
      current: boolean
      accept: () => void
      commit: (_event: unknown, url: string, _httpResponseCode: number, _httpStatusText: string, isMainFrame: boolean) => void
      invalidate: (_event: unknown, _url: string, _isInPlace: boolean, isMainFrame: boolean) => void
    }
  >()

  const addWebContents = (candidate: EmbeddedWebContents) => {
    if (documents.has(candidate)) {return}

    const state = {
      current: true,
      invalidate: (_event: unknown, _url: string, isInPlace: boolean, isMainFrame: boolean) => {
        if (isMainFrame && !isInPlace) {state.current = false}
      },
      commit: (_event: unknown, url: string, _httpResponseCode: number, _httpStatusText: string, isMainFrame: boolean) => {
        if (isMainFrame) {state.current = isTrustedEmbeddedDocumentUrl(url, expectedUrl)}
      },
      accept: () => {
        state.current = isTrustedEmbeddedDocumentUrl(candidate.getURL(), expectedUrl)
      }
    }

    documents.set(candidate, state)
    candidate.on?.('did-start-navigation', state.invalidate)
    candidate.on?.('did-frame-navigate', state.commit)
    candidate.on?.('did-finish-load', state.accept)
  }

  addWebContents(contents)

  const assertTrusted = (event: unknown) => {
    const sender = (event as { sender?: unknown } | null)?.sender
    const state = sender && typeof sender === 'object' ? documents.get(sender as EmbeddedWebContents) : undefined

    if (!state?.current || !isTrustedEmbeddedSender(event, sender as EmbeddedWebContents, expectedUrl)) {
      throw new Error('Rejected untrusted embedded Hermes IPC sender.')
    }
  }

  return {
    handle(channel: string, handler: (event: unknown, ...args: any[]) => unknown) {
      if (channels.has(channel)) {
        throw new Error(`Duplicate embedded Hermes IPC channel: ${channel}`)
      }

      channels.add(channel)
      ipc.handle(channel, (event, ...args) => {
        assertTrusted(event)

        return handler(event, ...args)
      })
    },
    on(channel: string, listener: (event: unknown, ...args: any[]) => void) {
      if (!ipc.on) {
        throw new Error('Embedded IPC does not support event subscriptions.')
      }

      const guarded = (event: unknown, ...args: any[]) => {
        try {
          assertTrusted(event)
        } catch {
          // EventEmitter listeners have no Promise boundary. Do not let an
          // untrusted Rhythm/subframe sender become a main-process exception;
          // fail closed and provide a safe sync result when Electron expects it.
          if (event && typeof event === 'object' && 'returnValue' in event) {
            ;(event as { returnValue?: unknown }).returnValue = false
          }

          return
        }

        listener(event, ...args)
      }

      listeners.push({ channel, listener: guarded })
      ipc.on(channel, guarded)
    },
    addWebContents,
    dispose() {
      for (const channel of channels) {
        ipc.removeHandler(channel)
      }

      for (const { channel, listener } of listeners) {
        ipc.removeListener?.(channel, listener)
      }

      listeners.length = 0
      channels.clear()

      for (const [candidate, state] of documents) {
        candidate.removeListener?.('did-start-navigation', state.invalidate)
        candidate.removeListener?.('did-frame-navigate', state.commit)
        candidate.removeListener?.('did-finish-load', state.accept)
      }

      documents.clear()
    }
  }
}

function profileStorePath(userDataPath: string) {
  return path.join(userDataPath, 'hermes-embedded-profile.json')
}

function readProfile(userDataPath: string): null | string {
  try {
    const profile = JSON.parse(fs.readFileSync(profileStorePath(userDataPath), 'utf8'))?.profile

    return typeof profile === 'string' && (profile === 'default' || PROFILE_RE.test(profile)) ? profile : null
  } catch {
    return null
  }
}

function writeProfile(userDataPath: string, raw: unknown): null | string {
  const profile = typeof raw === 'string' ? raw.trim() : ''

  if (profile && profile !== 'default' && !PROFILE_RE.test(profile)) {
    throw new Error('Invalid Hermes profile.')
  }

  fs.mkdirSync(userDataPath, { recursive: true })
  fs.writeFileSync(profileStorePath(userDataPath), `${JSON.stringify({ profile: profile || null }, null, 2)}\n`, 'utf8')

  return profile || null
}

const CHILD_BINARY_DIRS = process.platform === 'win32'
  ? ['C:\\Windows\\System32', 'C:\\Windows']
  : [path.join(os.userInfo().homedir, '.local', 'bin'), '/opt/homebrew/bin', '/usr/local/bin', '/usr/bin', '/bin']
const APPROVED_BROKER_KEYS = ['OPENROUTER_API_KEY', 'ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'GOOGLE_API_KEY'] as const

function resolveBinary(command: string) {
  const entries = CHILD_BINARY_DIRS
  const names = process.platform === 'win32' ? [command, `${command}.exe`, `${command}.cmd`] : [command]

  for (const entry of entries) {
    for (const name of names) {
      const candidate = path.join(entry, name)

      try {
        fs.accessSync(candidate, fs.constants.X_OK)

        return candidate
      } catch {
        // Continue through PATH; a missing git/hermes is reported by the caller.
      }
    }
  }

  return path.join(CHILD_BINARY_DIRS[0], process.platform === 'win32' ? `${command}.exe` : command)
}

function validEnvValue(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0 && value.length <= 4096 && !/[\u0000-\u001f\u007f]/.test(value)
}

function controlledChildEnv(options: EmbeddedHermesHostOptions, token: string): NodeJS.ProcessEnv {
  const selectedHome = options.hermesHome || path.join(os.userInfo().homedir, '.hermes')
  let home: string
  try { home = fs.realpathSync(selectedHome) } catch { home = path.resolve(selectedHome) }
  const temp = path.resolve(options.userDataPath, 'hermes-temp')
  fs.mkdirSync(temp, { recursive: true, mode: 0o700 })
  const env: NodeJS.ProcessEnv = {
    PATH: CHILD_BINARY_DIRS.join(path.delimiter),
    HOME: os.userInfo().homedir,
    TMPDIR: temp,
    TMP: temp,
    TEMP: temp,
    LANG: 'C.UTF-8',
    HERMES_HOME: home,
    HERMES_DASHBOARD_SESSION_TOKEN: token,
    HERMES_DESKTOP: '1'
  }
  if (process.platform === 'win32') {
    env.SystemRoot = 'C:\\Windows'
    env.WINDIR = 'C:\\Windows'
  }
  return env
}

async function brokeredChildEnv(options: EmbeddedHermesHostOptions, env: NodeJS.ProcessEnv, profile?: string): Promise<{ names: BrokeredKeyName[]; values: string[] }> {
  const empty = () => ({ names: [] as BrokeredKeyName[], values: [] as string[] })
  if (profile && profile !== 'default') return empty()
  const context = options.backendEnvContext
  if (!options.backendEnv || !context || !validEnvValue(context.serverOrigin) ||
    !validEnvValue(context.rhythmUserId) || !validEnvValue(context.authGeneration)) return empty()
  try {
    if (fs.realpathSync(env.HERMES_HOME!) !== env.HERMES_HOME) return empty()
  } catch { return empty() }
  let origin: string
  try {
    const parsed = new URL(context.serverOrigin)
    if (!['https:', 'http:'].includes(parsed.protocol) || parsed.origin !== context.serverOrigin) return empty()
    origin = parsed.origin
  } catch { return empty() }

  try {
    let deadline: ReturnType<typeof setTimeout> | undefined
    const result = await Promise.race([
      Promise.resolve().then(() => options.backendEnv!({
        serverOrigin: origin,
        rhythmUserId: context.rhythmUserId,
        profile: 'default',
        hermesHome: env.HERMES_HOME!,
        source: 'opencode-auth-json',
        authGeneration: context.authGeneration
      })),
      new Promise<never>((_, reject) => { deadline = setTimeout(() => reject(new Error('deadline')), 2_000) })
    ]).finally(() => clearTimeout(deadline))
    if (!result || typeof result !== 'object' || Array.isArray(result)) return empty()
    const staged: Array<[BrokeredKeyName, string]> = []
    for (const key of APPROVED_BROKER_KEYS) {
      const value = result[key]
      if (validEnvValue(value)) staged.push([key, value])
    }
    for (const [key, value] of staged) env[key] = value
    return { names: staged.map(([name]) => name), values: staged.map(([, value]) => value) }
  } catch {
    logLine(options.log, 'Credential broker unavailable; starting without grants.')
    return empty()
  }
}

async function prepareNativeOwnedAttempt(options: EmbeddedHermesHostOptions, profile: string, token: string, isDisposed: () => boolean) {
  if (isDisposed()) {throw new Error('Embedded Hermes host is disposed.')}
  const isDefault = profile === 'default'
  const attemptId = crypto.randomUUID()
  let accepted = false
  let retired = false
  const observe = (event: OwnedBackendAttemptEvent) => options.onOwnedBackendAttempt?.(Object.freeze(event))
  if (isDefault && options.onOwnedBackendAttempt) {
    observe({ attemptId, phase: 'starting', profile: 'default', acceptedEnvNames: Object.freeze([]) })
  }
  let env: NodeJS.ProcessEnv
  let granted: Awaited<ReturnType<typeof brokeredChildEnv>>
  try {
    env = controlledChildEnv(options, token)
    granted = await brokeredChildEnv(options, env, profile)
    if (isDisposed()) {throw new Error('Embedded Hermes host was disposed while a native backend was starting.')}
  } catch (error) {
    if (isDefault && options.onOwnedBackendAttempt) {
      try {
        observe({ attemptId, phase: 'retired', profile: 'default', acceptedEnvNames: Object.freeze([]), cause: 'failed' })
      } catch {logLine(options.log, 'Owned backend lifecycle observer failed during preparation cleanup.')}
    }
    throw error
  }
  return {
    env,
    redactValues: Object.freeze([token, ...granted.values]),
    assertActive: () => {
      if (retired || isDisposed()) {throw new Error('Owned Hermes backend is no longer active.')}
    },
    accept: () => {
      if (retired || isDisposed()) {throw new Error('Owned Hermes backend retired before acceptance.')}
      if (accepted) {return}
      if (isDefault && options.onOwnedBackendAttempt) {
        observe({ attemptId, phase: 'accepted', profile: 'default', acceptedEnvNames: Object.freeze([...granted.names]) })
      }
      accepted = true
    },
    retire: (cause: 'failed' | 'exited' | 'disposed') => {
      if (retired) {return}
      retired = true
      if (isDefault && options.onOwnedBackendAttempt) {
        try {
          observe({ attemptId, phase: 'retired', profile: 'default', acceptedEnvNames: Object.freeze([]), cause })
        } catch {logLine(options.log, 'Owned backend lifecycle observer failed during retirement.')}
      }
    }
  }
}

function captureChildOutput(stream: NodeJS.ReadableStream, log: EmbeddedHermesHostOptions['log'], secrets: string[]) {
  const decoder = new StringDecoder('utf8')
  const redactionValues = [...new Set(secrets.filter(Boolean))].sort((left, right) => right.length - left.length)
  let line = ''
  let oversized = false
  const emit = () => {
    if (oversized) logLine(log, '[backend output omitted: oversized line]')
    else if (line) {
      let safe = line
      for (const secret of redactionValues) safe = safe.replaceAll(secret, '[redacted]')
      safe = safe.replace(/([?&](?:access_token|token|session_token)=)[^&#\s]+/gi, '$1[redacted]')
      logLine(log, safe)
    }
    line = ''
    oversized = false
  }
  const append = (text: string) => {
    const parts = text.split('\n')
    for (const [index, part] of parts.entries()) {
      if (!oversized) {
        line += part
        if (line.length > 8192) { line = ''; oversized = true }
      }
      if (index < parts.length - 1) emit()
    }
  }
  stream.on('data', chunk => append(decoder.write(chunk)))
  stream.on('end', () => {
    append(decoder.end())
    emit()
  })
}

function resolveHermesBinary(hermesHome?: string) {
  const suffix = process.platform === 'win32' ? ['Scripts', 'hermes.exe'] : ['bin', 'hermes']
  const home = hermesHome || path.join(os.homedir(), '.hermes')

  const candidates = [
    path.join(home, '.venv', ...suffix),
    path.join(home, 'venv', ...suffix),
    path.join(home, 'hermes-agent', '.venv', ...suffix),
    path.join(home, 'hermes-agent', 'venv', ...suffix)
  ]

  for (const candidate of candidates) {
    try {
      fs.accessSync(candidate, fs.constants.X_OK)

      return candidate
    } catch {
      // A missing managed runtime is reported without invoking the installer.
    }
  }

  return resolveBinary('hermes')
}

function fetchJson(url: string, token?: string) {
  return fetch(url, {
    headers: token ? { 'X-Hermes-Session-Token': token } : undefined,
    signal: AbortSignal.timeout(5_000)
  }).then(async response => {
    if (!response.ok) {
      throw new Error(`${response.status}: ${await response.text()}`)
    }

    return response.json()
  })
}

type OwnedAttemptState = {
  accept: () => void
  isRetired: () => boolean
  onRetired: (listener: () => void) => void
}

const ownedConnectionAttempts = new WeakMap<object, OwnedAttemptState>()

class DisposedDuringStart extends Error {}

function createSpawnRuntime(options: EmbeddedHermesHostOptions): EmbeddedRuntime {
  const connections = new Map<string, Promise<EmbeddedBackendConnection>>()

  return {
    connect(profile) {
      const profileKey = profile || 'default'
      const existing = connections.get(profileKey)

      if (existing) {return existing}

      let pending: Promise<EmbeddedBackendConnection>
      pending = (async () => {
        const isDefault = profileKey === 'default'
        const attemptId = crypto.randomUUID()
        let started = false
        let accepted = false
        let retired = false
        let child: ChildProcess | undefined
        let retiredListener: (() => void) | undefined
        const observe = (event: OwnedBackendAttemptEvent) => options.onOwnedBackendAttempt?.(Object.freeze(event))
        const retire = (cause: 'failed' | 'exited' | 'disposed') => {
          if (retired) {return}
          retired = true
          if (connections.get(profileKey) === pending) {connections.delete(profileKey)}
          retiredListener?.()
          if (started) {
            observe({ attemptId, phase: 'retired', profile: 'default', acceptedEnvNames: Object.freeze([]), cause })
          }
        }

        try {
          if (isDefault && options.onOwnedBackendAttempt) {
            observe({ attemptId, phase: 'starting', profile: 'default', acceptedEnvNames: Object.freeze([]) })
            started = true
          }
          const token = crypto.randomBytes(32).toString('base64url')
          const args = [...(!isDefault ? ['--profile', profileKey] : []), 'serve', '--host', '127.0.0.1', '--port', '0']
          const env = controlledChildEnv(options, token)
          const granted = await brokeredChildEnv(options, env, profile)
          const hermes = resolveHermesBinary(env.HERMES_HOME)

          child = spawn(hermes, args, {
            cwd: env.HERMES_HOME,
            env,
            stdio: ['ignore', 'pipe', 'pipe']
          })
          const ownedChild = child
          const retireFromEvent = (cause: 'failed' | 'exited') => {
            try {retire(cause)} catch {logLine(options.log, 'Owned backend lifecycle observer failed.')}
          }
          ownedChild.once('error', () => retireFromEvent('failed'))
          ownedChild.once('exit', () => retireFromEvent('exited'))
          captureChildOutput(ownedChild.stdout!, options.log, [token, ...granted.values])
          captureChildOutput(ownedChild.stderr!, options.log, [token, ...granted.values])

          const port = await waitForDashboardPortAnnouncement(ownedChild)
          const baseUrl = `http://127.0.0.1:${port}`

          // This verifies the exact token-bearing local leg the renderer will use.
          await fetchJson(`${baseUrl}/api/status`, token)
          const wsUrl = `ws://127.0.0.1:${port}/api/ws?token=${encodeURIComponent(token)}`
          const wsProbe = await probeGatewayWebSocket(wsUrl, { WebSocketImpl: globalThis.WebSocket })

          if (!wsProbe.ok) {
            throw new Error(`Local Hermes backend WebSocket authentication failed: ${wsProbe.reason || 'unknown error'}`)
          }

          const connection: EmbeddedBackendConnection = {
            baseUrl,
            endpoint: baseUrl,
            logs: [],
            mode: 'local',
            owned: true,
            profile: profile || undefined,
            token,
            wsUrl,
            stop: async () => {
              await stopChild(ownedChild)
              retire('disposed')
            }
          }
          ownedConnectionAttempts.set(connection, {
            accept: () => {
              if (retired || ownedChild.exitCode !== null || ownedChild.signalCode !== null) {
                throw new Error('Owned Hermes backend exited before host acceptance.')
              }
              if (accepted) {return}
              if (started) {
                observe({ attemptId, phase: 'accepted', profile: 'default', acceptedEnvNames: Object.freeze([...granted.names]) })
              }
              accepted = true
            },
            isRetired: () => retired,
            onRetired: listener => {
              retiredListener = listener
              if (retired) {listener()}
            }
          })
          return connection
        } catch (error) {
          if (child?.pid !== undefined) {
            await stopChild(child)
          }
          retire('failed')
          throw error
        }
      })()

      connections.set(profileKey, pending)
      pending.catch(() => {
        if (connections.get(profileKey) === pending) {connections.delete(profileKey)}
      })

      return pending
    }
  }
}

interface EmbeddedRuntimeManifest {
  schemaVersion?: unknown
  baseUrl?: unknown
  profile?: unknown
  token?: unknown
  wsUrl?: unknown
}

/**
 * A running service is reusable only when an owner publishes its exact endpoint
 * and credential in the Hermes home, then both HTTP and WebSocket legs succeed.
 * The standalone ownership ledger intentionally has no token/port and is not a
 * safe discovery source. This manifest is opt-in; it is never written by the
 * embedded host and cannot overwrite a standalone connection.
 */
async function discoverCompatibleRuntime(options: EmbeddedHermesHostOptions): Promise<EmbeddedRuntime | undefined> {
  const home = options.hermesHome || path.join(os.homedir(), '.hermes')
  const manifestPath = path.join(home, EMBEDDED_RUNTIME_MANIFEST)
  let manifest: EmbeddedRuntimeManifest

  try {
    const stat = fs.lstatSync(manifestPath)

    if (!stat.isFile() || stat.isSymbolicLink() || (process.platform !== 'win32' && stat.uid !== process.getuid())) {
      return undefined
    }

    manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'))
  } catch {
    return undefined
  }

  if (
    manifest.schemaVersion !== 1 ||
    typeof manifest.baseUrl !== 'string' ||
    typeof manifest.token !== 'string' ||
    !manifest.token ||
    typeof manifest.wsUrl !== 'string'
  ) {
    logLine(options.log, 'ignored incompatible embedded-runtime.json')

    return undefined
  }

  try {
    const baseUrl = new URL(manifest.baseUrl)
    const wsUrl = new URL(manifest.wsUrl)
    const loopbackHosts = new Set(['127.0.0.1', '[::1]', '::1'])
    const normalizedPort = (url: URL) => url.port || (url.protocol === 'https:' || url.protocol === 'wss:' ? '443' : '80')

    if (
      !['http:', 'https:'].includes(baseUrl.protocol) ||
      !['ws:', 'wss:'].includes(wsUrl.protocol) ||
      !loopbackHosts.has(baseUrl.hostname) ||
      wsUrl.hostname !== baseUrl.hostname ||
      normalizedPort(wsUrl) !== normalizedPort(baseUrl) ||
      wsUrl.pathname !== '/api/ws'
    ) {
      return undefined
    }

    const status = await fetchJson(`${baseUrl.toString().replace(/\/$/, '')}/api/status`, manifest.token) as { version?: unknown }

    if (typeof status?.version !== 'string' || !status.version.trim()) {
      return undefined
    }

    const wsProbe = await probeGatewayWebSocket(wsUrl.toString(), { WebSocketImpl: globalThis.WebSocket })

    if (!wsProbe.ok) {
      logLine(options.log, `rejected reusable backend: ${wsProbe.reason || 'WebSocket validation failed'}`)

      return undefined
    }
  } catch (error) {
    logLine(options.log, `rejected reusable backend: ${error instanceof Error ? error.message : String(error)}`)

    return undefined
  }

  return {
    connect: async profile => {
      const declaredProfile = typeof manifest.profile === 'string' ? manifest.profile : undefined

      if (profile && declaredProfile && profile !== declaredProfile) {
        throw new Error('Reusable Hermes backend does not match the requested profile.')
      }

      return {
        baseUrl: manifest.baseUrl as string,
        endpoint: manifest.baseUrl as string,
        logs: [],
        mode: 'local',
        owned: false,
        profile: profile || declaredProfile,
        token: manifest.token as string,
        wsUrl: manifest.wsUrl as string
      }
    }
  }
}

async function stopChild(child: ChildProcess) {
  if (child.exitCode !== null || child.signalCode !== null) {
    return
  }

  const waitForExit = (timeoutMs: number) =>
    new Promise<boolean>(resolve => {
      if (child.exitCode !== null || child.signalCode !== null) {return resolve(true)}
      const timer = setTimeout(() => resolve(false), timeoutMs)
      child.once('exit', () => {
        clearTimeout(timer)
        resolve(true)
      })
    })

  try {
    if (!child.kill('SIGTERM') && child.exitCode === null && child.signalCode === null) {
      throw new Error('Owned Hermes child refused termination.')
    }
  } catch (error) {
    throw new Error('Owned Hermes child stop failed.', { cause: error })
  }

  if (await waitForExit(2_000)) {return}

  try {
    if (!child.kill('SIGKILL') && child.exitCode === null && child.signalCode === null) {
      throw new Error('Owned Hermes child refused forced termination.')
    }
  } catch (error) {
    throw new Error('Owned Hermes child forced stop failed.', { cause: error })
  }

  if (!await waitForExit(1_000)) {
    throw new Error('Owned Hermes child remained active after forced termination.')
  }
}

function connectionForRenderer(connection: EmbeddedBackendConnection, profile?: string) {
  const baseUrl = connection.baseUrl || connection.endpoint

  return {
    baseUrl,
    logs: connection.logs || [],
    mode: connection.mode || 'local',
    profile: profile || connection.profile,
    token: connection.token || '',
    wsUrl: connection.wsUrl || baseUrl.replace(/^http/, 'ws').replace(/\/$/, '') + '/api/ws'
  }
}

async function proxyApiRequest(connection: EmbeddedBackendConnection, rawRequest: unknown) {
  const request = rawRequest && typeof rawRequest === 'object' ? (rawRequest as Record<string, unknown>) : null
  const requestPath = typeof request?.path === 'string' ? request.path : ''

  if (!requestPath.startsWith('/api/') || requestPath.startsWith('//')) {
    throw new Error('Invalid Hermes API path.')
  }

  const method = typeof request?.method === 'string' ? request.method.toUpperCase() : 'GET'

  if (!['DELETE', 'GET', 'PATCH', 'POST', 'PUT'].includes(method) || request?.upload) {
    throw new Error('Unsupported embedded Hermes API request.')
  }

  const body = request?.body === undefined ? undefined : JSON.stringify(request.body)

  const response = await fetch(`${(connection.baseUrl || connection.endpoint).replace(/\/$/, '')}${requestPath}`, {
    method,
    headers: {
      ...(connection.token ? { 'X-Hermes-Session-Token': connection.token } : {}),
      ...(body ? { 'Content-Type': 'application/json' } : {})
    },
    ...(body ? { body } : {}),
    signal: AbortSignal.timeout(30_000)
  })

  const text = await response.text()

  if (!response.ok) {
    throw new Error(`${response.status}: ${text}`)
  }

  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

/**
 * Production entrypoint. Rhythm calls it once for a live Hermes WebContentsView
 * before loading the renderer. The test entrypoint below only substitutes the
 * Electron/process boundary; it drives this same scoped registration surface.
 */
export async function createEmbeddedHermesHost(options: EmbeddedHermesHostOptions): Promise<EmbeddedHermesHost> {
  let nativeOwnedDisposed = false
  const nativeOwnedPending = new Set<Promise<unknown>>()
  const injectedRuntime = options.hostWindow && typeof options.hostWindow === 'object' ? hostRuntimes.get(options.hostWindow) : undefined
  const discoveredRuntime = injectedRuntime ? undefined : await discoverCompatibleRuntime(options)
  // Only a verified external runtime belongs at the shared runtime's local
  // connection seam. When none is available, Desktop's original bootstrap
  // path remains the sole owner of runtime resolution and process startup.
  const borrowedRuntime = injectedRuntime || discoveredRuntime

  const host = await createEmbeddedHermesHostForTest(options, {
    ipc: ipcMain,
    registerCoreBridge: false,
    runtime: borrowedRuntime || createSpawnRuntime(options)
  })

  const connect = hostConnectors.get(host)
  const recordConnection = hostDescriptorRecorders.get(host)

  if (!connect || !recordConnection) {throw new Error('Embedded Hermes host connection boundary was not initialized.')}

  const runtimeIpc = createEmbeddedIpcRegistrar(ipcMain as unknown as EmbeddedIpc, options.webContents, options.assetRoot)
  const ownedWindows = new Set<any>()

  try {
  const { BrowserWindow, session } = await import('electron')
  const auxiliarySessions = new Map<'link-titles' | 'oauth', unknown>()
  const expectedPreload = path.resolve(options.assetRoot, 'electron', 'preload.cjs')

  const windowAdapter: DesktopRuntimeWindowAdapter = {
    async dispose() {
      for (const window of ownedWindows) {
        if (!window.isDestroyed?.()) {window.close?.()}
      }

      ownedWindows.clear()
    },
    getDialogWindow: () => options.hostWindow,
    getOwnedWebContents: () => [...ownedWindows].map(window => window.webContents).filter(Boolean),
    getPartitionSession(kind) {
      const existing = auxiliarySessions.get(kind)

      if (existing) {return existing}
      const viewId = Number.isInteger(options.webContents.id) ? options.webContents.id : 'view'
      const scoped = session.fromPartition(`persist:hermes-embedded-${viewId}-${kind}`)
      auxiliarySessions.set(kind, scoped)

      return scoped
    },
    getRendererWebContents: () => options.webContents,
    listOwnedWindows: () => [...ownedWindows].filter(window => !window.isDestroyed?.()),
    openExternal: async rawUrl => {
      const url = new URL(rawUrl)
      const opener = options.openExternal ?? (options.hostWindow as { openEmbeddedExternal?: unknown } | null)?.openEmbeddedExternal

      if (!['http:', 'https:', 'mailto:'].includes(url.protocol) || typeof opener !== 'function') {
        throw new Error('Rhythm external browser adapter is unavailable.')
      }

      await (opener as (value: string) => Promise<void> | void)(url.toString())
    },
    openInTerminal: async () => ({ ok: false, reason: 'runtime-handler-required' }),
    openInstance: async () => ({ ok: false, reason: 'runtime-handler-required' }),
    openSession: async () => ({ ok: false, reason: 'runtime-handler-required' }),
    createOwnedPopout(rawOptions) {
      if (!rawOptions || typeof rawOptions !== 'object') {
        throw new Error('Embedded Hermes popout requires BrowserWindow options.')
      }

      const source = rawOptions as { webPreferences?: Record<string, unknown> }
      const candidatePreload = typeof source.webPreferences?.preload === 'string' ? path.resolve(source.webPreferences.preload) : undefined

      const safeOptions = {
        ...source,
        webPreferences: {
          ...source.webPreferences,
          contextIsolation: true,
          nodeIntegration: false,
          // Only windows created by the actual Desktop session/instance path
          // may receive its artifact-local preload. OAuth/browser guests get
          // no preload even if a caller tries to smuggle one into options.
          preload: candidatePreload === expectedPreload ? expectedPreload : undefined,
          sandbox: true
        }
      }

      const popout: any = new BrowserWindow(safeOptions)
      ownedWindows.add(popout)
      popout.once?.('closed', () => ownedWindows.delete(popout))
      runtimeIpc.addWebContents(popout.webContents)

      return popout
    }
  }

  const { initializeDesktopNativeRuntime } = await import('./desktop-native-runtime')

  const nativeRuntime = initializeDesktopNativeRuntime({
    backend: {
      disposeOwned: async () => undefined,
      // The extracted runtime normally owns these routes. Keep this legacy
      // adapter clone-safe as well: host-only ownership and stop callbacks
      // must never escape through an IPC return value.
      ensure: async profile => connectionForRenderer(await connect(profile), profile),
      gatewayWsUrl: async profile => connectionForRenderer(await connect(profile), profile).wsUrl,
      handleApi: async request => proxyApiRequest(await connect((request as { profile?: string } | null)?.profile), request)
    },
    ipc: runtimeIpc,
    // Borrowed local connections are accepted before native setup. The native
    // runtime retains startup and ownership of every newly spawned backend.
    ...(borrowedRuntime
      ? { localBackend: { connect: async profile => connectionForRenderer(await connect(profile), profile) } }
      : {}),
    ownedSpawn: {
      probeEnv: () => {
        const { HERMES_DASHBOARD_SESSION_TOKEN: _token, ...env } = controlledChildEnv(options, '')
        return env
      },
      prepare: (profile, token) => {
        const pending = prepareNativeOwnedAttempt(options, profile, token, () => nativeOwnedDisposed)
        nativeOwnedPending.add(pending)
        pending.then(() => nativeOwnedPending.delete(pending), () => nativeOwnedPending.delete(pending))
        return pending
      }
    },
    mode: 'embedded',
    paths: {
      assetRoot: options.assetRoot,
      hermesHome: options.hermesHome || path.join(os.homedir(), '.hermes'),
      userData: path.join(options.userDataPath, 'hermes-desktop')
    },
    windowAdapter,
    onConnectionDescriptor: recordConnection
  })

  let disposePromise: Promise<void> | undefined
  return {
    ...host,
    dispose() {
      if (disposePromise) {return disposePromise}
      nativeOwnedDisposed = true
      disposePromise = (async () => {
        await Promise.allSettled([...nativeOwnedPending])
        let nativeFailure: unknown
        let ipcFailure: unknown
        let hostFailure: unknown
        try {await nativeRuntime.dispose()} catch (error) {nativeFailure = error}
        try {runtimeIpc.dispose()} catch (error) {ipcFailure = error}
        // Credential-bearing children belong to the host. Stop them even if an
        // unrelated native/IPC teardown step failed earlier.
        try {await host.dispose()} catch (error) {hostFailure = error}
        if (hostFailure !== undefined) {throw hostFailure}
        if (nativeFailure !== undefined) {throw nativeFailure}
        if (ipcFailure !== undefined) {throw ipcFailure}
      })()
      return disposePromise
    }
  }
  } catch (error) {
    for (const window of ownedWindows) {
      if (!window.isDestroyed?.()) {window.close?.()}
    }

    ownedWindows.clear()
    runtimeIpc.dispose()
    await host.dispose()
    throw error
  }
}

export async function createEmbeddedHermesHostForTest(
  options: EmbeddedHermesHostOptions,
  deps: EmbeddedHostTestDeps = {}
): Promise<EmbeddedHermesHost> {
  const ipc = deps.ipc || (ipcMain as unknown as EmbeddedIpc)
  const scopedIpc = createEmbeddedIpcRegistrar(ipc, options.webContents, options.assetRoot)
  const expectedRendererUrl = trustedDocumentUrl(options.assetRoot)
  const runtime = deps.runtime || createSpawnRuntime(options)
  const registerCoreBridge = deps.registerCoreBridge !== false
  let disposed = false
  const connections = new Map<string, EmbeddedBackendConnection>()
  // A route can be removed from the renderer's registry before the host closes.
  // Retain owned children separately so revoking its origin never loses the
  // process handle needed for the final host-scoped cleanup.
  const retiredOwnedConnections = new Set<EmbeddedBackendConnection>()
  const sharedConnections = new Map<string, EmbeddedBackendConnection>()
  const connecting = new Map<string, Promise<EmbeddedBackendConnection>>()
  let disposePromise: Promise<void> | undefined
  const allowedOriginListeners = new Set<(origins: string[]) => void>()
  let microphoneConsentUntil = 0
  let bootProgress = { error: null as null | string, message: 'Hermes Desktop is ready to connect.', phase: 'backend.idle', progress: 0, running: false }
  const publishBootProgress = () => options.webContents.send?.('hermes:boot-progress', bootProgress)

  const allowedOrigins = () => {
    const origins = new Set<string>()

    for (const connection of [...connections.values(), ...sharedConnections.values()]) {
      const base = new URL(connection.baseUrl || connection.endpoint)
      const websocket = new URL(connection.wsUrl || base.toString().replace(/^http/, 'ws'))

      if (['http:', 'https:'].includes(base.protocol)) {origins.add(base.origin)}

      if (['ws:', 'wss:'].includes(websocket.protocol)) {origins.add(websocket.origin)}
    }

    return [...origins]
  }

  const publishAllowedOrigins = () => {
    const origins = allowedOrigins()

    for (const listener of allowedOriginListeners) {listener(origins)}
  }

  const descriptorIdentity = (connection: Partial<EmbeddedBackendConnection>) => {
    const connectionId = typeof connection.connectionId === 'string' && connection.connectionId ? connection.connectionId : undefined
    const profile = typeof connection.profile === 'string' && connection.profile ? connection.profile : ''

    if (connectionId) {
      return `connection:${connectionId}:profile:${profile}`
    }

    try {
      const endpoint = new URL(connection.baseUrl || connection.endpoint || '').origin

      return endpoint === 'null' ? undefined : `endpoint:${endpoint}:profile:${profile}`
    } catch {
      return undefined
    }
  }

  const removeConnectionDescriptor = (identity: string | undefined) => {
    if (!identity) {
      return false
    }

    let removed = sharedConnections.delete(identity)

    for (const [key, connection] of connections) {
      if (descriptorIdentity(connection) === identity) {
        if (connection.owned) {
          retiredOwnedConnections.add(connection)
        }

        connections.delete(key)
        removed = true
      }
    }

    return removed
  }

  const recordConnectionDescriptor = (raw: unknown) => {
    if (!raw || typeof raw !== 'object') {return}

    const event = raw as {
      connection?: unknown
      connectionId?: unknown
      profile?: unknown
      type?: unknown
    }

    const type = event.type

    if (type === 'reset') {
      const changed = sharedConnections.size > 0 || connections.size > 0

      for (const connection of connections.values()) {
        if (connection.owned) {
          retiredOwnedConnections.add(connection)
        }
      }

      sharedConnections.clear()
      connections.clear()

      if (changed) {publishAllowedOrigins()}

      return
    }

    if (type === 'remove') {
      const removed = removeConnectionDescriptor(
        descriptorIdentity({
          connectionId: typeof event.connectionId === 'string' ? event.connectionId : undefined,
          profile: typeof event.profile === 'string' ? event.profile : undefined
        })
      )

      if (removed) {publishAllowedOrigins()}

      return
    }

    const connection = (type === 'upsert' ? event.connection : raw) as EmbeddedBackendConnection

    if (!connection || typeof connection !== 'object') {return}

    try {
      const base = new URL(connection.baseUrl || connection.endpoint)
      const websocket = new URL(connection.wsUrl || base.toString().replace(/^http/, 'ws'))

      if (!['http:', 'https:'].includes(base.protocol) || !['ws:', 'wss:'].includes(websocket.protocol)) {return}
      const key = descriptorIdentity(connection)

      if (!key) {return}

      // `connection:for` can resolve through the legacy local route first,
      // which publishes the same endpoint without a registry ID. Once the
      // scoped descriptor arrives, replace that fallback record so a later
      // `connections:remove(id)` revokes this exact origin instead of leaving
      // the endpoint-only entry approved for the rest of the view lifetime.
      if (connection.connectionId) {
        const fallbackIdentity = descriptorIdentity({
          baseUrl: connection.baseUrl,
          endpoint: connection.endpoint,
          profile: connection.profile,
          wsUrl: connection.wsUrl
        })

        if (fallbackIdentity && fallbackIdentity !== key) {
          sharedConnections.delete(fallbackIdentity)

          for (const [connectionKey, cached] of connections) {
            if (descriptorIdentity(cached) !== fallbackIdentity) {
              continue
            }

            if (cached.owned) {
              retiredOwnedConnections.add(cached)
            }

            connections.delete(connectionKey)
          }
        }
      }

      sharedConnections.set(key, connection)
      publishAllowedOrigins()
    } catch {
      // The shared runtime callback is internal, but malformed descriptors are
      // still not allowed to widen Rhythm's network policy.
    }
  }

  const openExternal = async (url: URL): Promise<boolean> => {
    const opener = options.openExternal ?? (options.hostWindow as { openEmbeddedExternal?: unknown } | null)?.openEmbeddedExternal

    if (typeof opener !== 'function') {return false}
    await (opener as (value: string) => Promise<void> | void)(url.toString())

    return true
  }

  const connect = async (profile?: string) => {
    if (disposed) {throw new Error('Embedded Hermes host is disposed.')}
    const selectedProfile = profile || readProfile(options.userDataPath) || undefined
    const key = selectedProfile || 'default'
    let currentConnection = connections.get(key)

    if (!currentConnection) {
      const inFlight = connecting.get(key)

      if (inFlight) {
        return inFlight
      }

      bootProgress = { error: null, message: 'Connecting Hermes backend…', phase: 'backend.connecting', progress: 40, running: true }
      publishBootProgress()

      const pending = (async () => {
        try {
          currentConnection = await runtime.connect(selectedProfile)

          if (disposed) {
            if (currentConnection.owned) {
              await currentConnection.stop?.()
            }

            throw new DisposedDuringStart('Embedded Hermes host was disposed while the backend was starting.')
          }

          const attempt = ownedConnectionAttempts.get(currentConnection)
          if (attempt) {
            try {
              attempt.accept()
            } catch (error) {
              await currentConnection.stop?.()
              throw error
            }
          }
          connections.set(key, currentConnection)
          attempt?.onRetired(() => {
            if (connections.get(key) === currentConnection) {
              connections.delete(key)
              publishAllowedOrigins()
            }
            retiredOwnedConnections.delete(currentConnection!)
          })
          if (attempt?.isRetired()) {
            throw new Error('Owned Hermes backend exited before host acceptance.')
          }
          const identity = descriptorIdentity(currentConnection)

          if (identity) {
            retiredOwnedConnections.delete(currentConnection)
          }

          publishAllowedOrigins()
          bootProgress = { error: null, message: 'Hermes backend is ready.', phase: 'backend.ready', progress: 100, running: true }
          publishBootProgress()

          return currentConnection
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error)
          bootProgress = { error: message, message, phase: 'backend.error', progress: 0, running: false }
          publishBootProgress()
          options.webContents.send?.('hermes:backend-exit', { code: null, error: message, signal: null })
          throw error
        } finally {
          connecting.delete(key)
        }
      })()

      connecting.set(key, pending)

      return pending
    }

    return currentConnection
  }

  scopedIpc.handle('hermes:embedded:metadata', () => ({
    assetRoot: options.assetRoot,
    embedded: true,
    host: 'rhythm',
    schemaVersion: 1
  }))

  if (registerCoreBridge) {
    scopedIpc.handle('hermes:boot-progress:get', () => bootProgress)
    scopedIpc.handle('hermes:connection', async (_event, profile) => connectionForRenderer(await connect(profile), profile))
    scopedIpc.handle('hermes:gateway:ws-url', async (_event, profile) => ({ ok: true, wsUrl: connectionForRenderer(await connect(profile), profile).wsUrl }))
    scopedIpc.handle('hermes:backend:touch', async (_event, profile) => {
      await connect(profile)

      return { ok: true }
    })
    scopedIpc.handle('hermes:profile:get', () => ({ profile: readProfile(options.userDataPath) }))
    scopedIpc.handle('hermes:profile:set', async (_event, profile) => {
      const next = writeProfile(options.userDataPath, profile)
      publishAllowedOrigins()

      return { profile: next }
    })
  }

  scopedIpc.handle('hermes:requestMicrophoneAccess', async () => {
    // The renderer invokes this from the explicit microphone gesture before
    // getUserMedia. The scoped registrar proves it is the current main Hermes
    // document; the Rhythm-owned callback renders the only user consent UI.
    if (options.webContents.isDestroyed()) {return false}

    const granted = await requestMicrophoneConsent(options, {
      isMainFrame: true,
      mediaTypes: ['audio'],
      permission: 'media',
      requestingUrl: options.webContents.getURL()
    })

    microphoneConsentUntil = granted ? Date.now() + 60_000 : 0

    return granted
  })

  if (registerCoreBridge) {
    scopedIpc.handle('hermes:api', async (_event, request) => proxyApiRequest(await connect((request as any)?.profile), request))
  }

  // Production registers the real shared-runtime handler through a separate
  // scoped registrar. Keep this minimal bridge only for direct host tests.
  if (registerCoreBridge) {
    scopedIpc.handle('hermes:openExternal', async (_event, rawUrl) => {
      const url = new URL(String(rawUrl || ''))

      if (!['http:', 'https:', 'mailto:'].includes(url.protocol)) {
        throw new Error('Unsupported external URL protocol.')
      }

      // Rhythm owns external-window policy. It may supply this narrowly scoped
      // adapter; host receives only a validated URL and no generic window access.
      return (await openExternal(url)) ? { ok: true } : { ok: false, reason: 'host-open-external-required' }
    })
  }

  const host: EmbeddedHermesHost = {
    async dispose() {
      if (disposePromise) {return disposePromise}
      disposed = true
      disposePromise = (async () => {
        microphoneConsentUntil = 0
        scopedIpc.dispose()
        const inFlight = await Promise.allSettled([...connecting.values()])
        const owned = [...new Set([...connections.values(), ...retiredOwnedConnections])].filter(connection => connection.owned)
        connections.clear()
        retiredOwnedConnections.clear()
        sharedConnections.clear()
        publishAllowedOrigins()
        allowedOriginListeners.clear()

        const failures = inFlight.filter((result): result is PromiseRejectedResult =>
          result.status === 'rejected' && !(result.reason instanceof DisposedDuringStart))
        for (const connection of owned) {
          try {await connection.stop?.()} catch (error) {failures.push({ status: 'rejected', reason: error })}
        }
        if (failures.length > 0) {throw failures[0].reason}
      })()
      return disposePromise
    },
    async getAllowedOrigins() {
      if (registerCoreBridge) {await connect()}

      return allowedOrigins()
    },
    onAllowedOrigins(callback) {
      allowedOriginListeners.add(callback)
      callback(allowedOrigins())

      return () => allowedOriginListeners.delete(callback)
    },
    async handlePermissionRequest(request) {
      // This API is called only by Rhythm's session permission hook for this
      // view. Verify the document again here because the hook can outlive a
      // renderer navigation and Electron reports permission names from guests.
      const requestingUrl = request.requestingUrl ?? request.requestingOrigin
      const audioOnly = Array.isArray(request.mediaTypes) && request.mediaTypes.length === 1 && request.mediaTypes[0] === 'audio'

      if (
        disposed ||
        request.permission !== 'media' ||
        request.isMainFrame === false ||
        options.webContents.isDestroyed() ||
        typeof requestingUrl !== 'string' ||
        !audioOnly ||
        microphoneConsentUntil < Date.now() ||
        !isTrustedEmbeddedDocumentUrl(requestingUrl, expectedRendererUrl) ||
        !isTrustedEmbeddedDocumentUrl(options.webContents.getURL(), expectedRendererUrl)
      ) {
        return false
      }

      // Consume the short-lived grant: Chromium may ask repeatedly, but each
      // capture session must follow a fresh renderer gesture and consent.
      microphoneConsentUntil = 0

      return true
    },
    handleWillAttachWebview(webPreferences, params) {
      // The built-in Desktop Browser remains usable for remote HTTP(S) sites,
      // but a guest is an untrusted browser document: it cannot inherit the
      // Hermes preload, Node, nested webviews, or the parent view's privilege.
      if (typeof params.src !== 'string') {return false}

      try {
        const source = new URL(params.src)

        // The Browser component first attaches an inert blank guest and only
        // then invokes navigation after dom-ready. Permit this exact bootstrap
        // URL once; later guest navigation is checked separately and accepts
        // HTTP(S) only.
        if (!['http:', 'https:'].includes(source.protocol) && source.href !== 'about:blank') {return false}
      } catch {
        return false
      }

      const viewId = Number.isInteger(options.webContents.id) ? options.webContents.id : 'view'
      const partition = `persist:hermes-embedded-${viewId}-preview`

      if (params.partition !== undefined && params.partition !== partition) {return false}
      params.partition = partition
      webPreferences.contextIsolation = true
      webPreferences.nodeIntegration = false
      webPreferences.preload = undefined
      webPreferences.sandbox = true
      webPreferences.webviewTag = false

      return true
    },
    handleGuestNavigation(rawUrl) {
      try {
        const url = new URL(rawUrl)

        return ['http:', 'https:'].includes(url.protocol)
      } catch {
        return false
      }
    },
    async handleGuestWindowOpen(rawUrl) {
      let url: URL

      try {
        url = new URL(rawUrl)
      } catch {
        return false
      }

      if (!['http:', 'https:'].includes(url.protocol)) {return false}

      return openExternal(url)
    },
    async handleIntent(intent) {
      if (disposed) {
        return { ok: false, reason: 'disposed' }
      }

      if (!intent || typeof intent !== 'object') {
        return { ok: false, reason: 'invalid-intent' }
      }

      const record = intent as { v?: unknown; type?: unknown; sessionId?: unknown; context?: unknown }

      if (record.v !== 1 || !['new-chat', 'navigate-session'].includes(String(record.type))) {
        return { ok: false, reason: 'unsupported-intent' }
      }

      if (record.type === 'navigate-session' && (typeof record.sessionId !== 'string' || !record.sessionId.trim())) {
        return { ok: false, reason: 'invalid-session-id' }
      }

      options.webContents.send?.('hermes:embedded:intent', {
        v: 1,
        type: record.type,
        ...(record.type === 'navigate-session' ? { sessionId: String(record.sessionId).trim() } : {}),
        ...(record.type === 'new-chat' && typeof record.context === 'string' ? { context: record.context } : {})
      })

      return { ok: true }
    }
  }

  hostConnectors.set(host, connect)
  hostDescriptorRecorders.set(host, recordConnectionDescriptor)

  return host
}
