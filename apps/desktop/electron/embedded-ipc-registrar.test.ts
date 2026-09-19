import assert from 'node:assert/strict'

import { test, vi } from 'vitest'

vi.mock('electron', () => ({ ipcMain: {}, shell: {} }))

import { createEmbeddedIpcRegistrar } from './embedded-host'
import { registerHudIpc } from './hud-ipc'
import { registerPetOverlayIpc } from './pet-overlay-ipc'

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

test('HUD and pet-overlay registration inherit the embedded sender guard', async () => {
  // Regression caught: a module's direct ipcMain import bypasses the host guard,
  // allowing the Rhythm shell to open or manipulate a Hermes popout.
  const ipc = rawIpc()
  const mainFrame = { url: 'file:///tmp/hermes-artifact/renderer/index.html?embedded=1' }
  const contents = { getURL: () => mainFrame.url, isDestroyed: () => false, mainFrame }
  const registrar = createEmbeddedIpcRegistrar(ipc, contents, '/tmp/hermes-artifact')
  const moveHud = vi.fn()

  registerHudIpc({
    ipcMain: registrar as never,
    isMac: false,
    isWindows: false,
    glassSupported: false,
    getTranslucencyState: () => ({ enabled: false } as never),
    getHudWindow: () => null,
    openHudWindow: moveHud,
    closeHudWindow: vi.fn(),
    setHudSessionId: vi.fn()
  })
  registerPetOverlayIpc({
    ipcMain: registrar as never,
    getMainWindow: () => null,
    getPetOverlayWindow: () => null,
    openPetOverlay: vi.fn(),
    closePetOverlay: vi.fn()
  })

  const foreign = { sender: { id: 2 }, senderFrame: mainFrame }
  assert.throws(() => ipc.handlers.get('hermes:hud:open')!(foreign, {}), /untrusted embedded Hermes IPC sender/)
  assert.throws(() => ipc.handlers.get('hermes:pet-overlay:open')!(foreign, {}), /untrusted embedded Hermes IPC sender/)

  // ipcMain.on listeners run from Electron's EventEmitter. A foreign event
  // must be silently ignored, not throw into main-process uncaughtException.
  assert.doesNotThrow(() => ipc.listeners.get('hermes:hud:move-by')!(foreign, { x: 10, y: 10 }))
  assert.equal(moveHud.mock.calls.length, 0)

  await registrar.dispose()
  assert.equal(ipc.handlers.size, 0)
  assert.equal(ipc.listeners.size, 0)
})
