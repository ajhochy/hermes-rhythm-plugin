import os from 'node:os'
// Window authority boundary for Desktop rendered inside Rhythm's WebContentsView.
// The host BrowserWindow belongs to Rhythm; Hermes may use it only as an explicit
// parent for native dialogs. Every window created through this adapter is tracked
// as Hermes-owned and is closed on embedded-host disposal.
import path from 'node:path'

export interface EmbeddedOwnedWindow {
  close: () => void
  isDestroyed: () => boolean
  once?: (event: 'closed', listener: () => void) => void
}

export interface EmbeddedRendererWebContents {
  isDestroyed: () => boolean
  send: (channel: string, payload: unknown) => void
}

export interface EmbeddedWindowAdapterOptions<HostWindow, OwnedWindow extends EmbeddedOwnedWindow> {
  hostWindow: HostWindow
  rendererWebContents: EmbeddedRendererWebContents
  // BrowserWindow construction is synchronous. The shared Desktop factory
  // calls this from `new BrowserWindow(...)`, so async factories would hand a
  // Promise to existing window lifecycle code instead of a real window.
  createPopout: (request: { kind: 'instance' | 'session'; sessionId?: string }) => OwnedWindow
  openExternal: (url: string) => Promise<void> | void
  openInTerminal: (sessionId: string, opts?: unknown) => Promise<void> | void
}

export interface EmbeddedRuntimePaths {
  assetRoot: string
  desktopUserDataPath: string
  hermesHome: string
}

export function resolveEmbeddedPaths({
  assetRoot,
  hermesHome,
  userDataPath
}: {
  assetRoot: string
  hermesHome?: string
  userDataPath: string
}): EmbeddedRuntimePaths {
  const desktopUserDataPath = path.join(userDataPath, 'hermes-desktop')

  return {
    assetRoot: path.resolve(assetRoot),
    desktopUserDataPath,
    // Preserve the existing Desktop/CLI home unless the caller explicitly
    // supplies a profile root. userData is only for embedding-owned UI state.
    hermesHome: hermesHome ? path.resolve(hermesHome) : path.join(os.homedir(), '.hermes')
  }
}

export function createEmbeddedWindowAdapter<HostWindow, OwnedWindow extends EmbeddedOwnedWindow>(
  options: EmbeddedWindowAdapterOptions<HostWindow, OwnedWindow>
) {
  const owned = new Set<OwnedWindow>()

  const track = (window: OwnedWindow) => {
    owned.add(window)
    window.once?.('closed', () => owned.delete(window))

    return window
  }

  const openExternal = async (rawUrl: string) => {
    const url = new URL(rawUrl)

    if (!['http:', 'https:', 'mailto:'].includes(url.protocol)) {
      throw new Error('Unsupported external URL protocol.')
    }

    await options.openExternal(url.toString())
  }

  return {
    createOwnedPopout: (rawRequest: unknown) => {
      const request = rawRequest && typeof rawRequest === 'object' ? (rawRequest as { kind?: unknown; sessionId?: unknown }) : {}

      if (request.kind !== 'instance' && request.kind !== 'session') {
        throw new Error('Unsupported embedded popout request.')
      }

      if (request.kind === 'session' && (typeof request.sessionId !== 'string' || !request.sessionId.trim())) {
        throw new Error('Embedded session popout requires a session id.')
      }

      const sessionId = typeof request.sessionId === 'string' ? request.sessionId.trim() : undefined

      return track(options.createPopout({
        kind: request.kind,
        ...(request.kind === 'session' ? { sessionId } : {})
      }))
    },
    dispose: async () => {
      for (const window of owned) {
        if (!window.isDestroyed()) {
          window.close()
        }
      }

      owned.clear()
    },
    getDialogWindow: () => options.hostWindow,
    getRendererWebContents: () => options.rendererWebContents,
    listOwnedWindows: () => [...owned].filter(window => !window.isDestroyed()),
    openExternal,
    openInstance: async () => {
      track(options.createPopout({ kind: 'instance' }))

      return { ok: true }
    },
    openInTerminal: async (sessionId: string, opts?: unknown) => {
      if (!sessionId.trim()) {return { ok: false, reason: 'invalid-session-id' }}
      await options.openInTerminal(sessionId, opts)

      return { ok: true }
    },
    openSession: async (sessionId: string, opts?: unknown) => {
      if (!sessionId.trim()) {return { ok: false, reason: 'invalid-session-id' }}
      void opts
      track(options.createPopout({ kind: 'session', sessionId }))

      return { ok: true }
    },
    send: (channel: string, payload: unknown) => {
      if (!options.rendererWebContents.isDestroyed()) {
        options.rendererWebContents.send(channel, payload)
      }
    }
  }
}
