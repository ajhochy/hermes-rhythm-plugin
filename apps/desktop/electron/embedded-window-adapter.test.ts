import assert from 'node:assert/strict'
import os from 'node:os'

import { test, vi } from 'vitest'

import { createEmbeddedWindowAdapter, resolveEmbeddedPaths } from './embedded-window-adapter'

function fakeWindow(id: number) {
  let destroyed = false
  const listeners = new Map<string, Set<() => void>>()

  return {
    id,
    close: vi.fn(() => {
      destroyed = true

      for (const listener of listeners.get('closed') || []) {listener()}
    }),
    isDestroyed: () => destroyed,
    once(name: string, listener: () => void) {
      const set = listeners.get(name) || new Set()
      set.add(listener)
      listeners.set(name, set)
    }
  }
}

test('embedded window adapter exposes the Rhythm host only for dialogs and enumerates only Hermes-owned popouts', async () => {
  // Regression caught: a shared Desktop handler uses BrowserWindow.getAllWindows
  // and controls Rhythm's main window or another app-owned window.
  const hostWindow = fakeWindow(1)
  const firstPopout = fakeWindow(2)
  const secondPopout = fakeWindow(3)
  const createPopout = vi.fn(() => firstPopout)
  const viewContents = { isDestroyed: () => false, send: vi.fn() }

  const adapter = createEmbeddedWindowAdapter({
    createPopout,
    hostWindow,
    openExternal: vi.fn(async () => undefined),
    openInTerminal: vi.fn(async () => undefined),
    rendererWebContents: viewContents
  })

  assert.equal(adapter.getDialogWindow(), hostWindow)
  assert.deepEqual(adapter.listOwnedWindows(), [])
  assert.equal(await adapter.createOwnedPopout({ kind: 'session', sessionId: 's-1' }), firstPopout)
  assert.deepEqual(adapter.listOwnedWindows(), [firstPopout])

  firstPopout.close()
  assert.deepEqual(adapter.listOwnedWindows(), [])
  createPopout.mockReturnValueOnce(secondPopout)
  await adapter.createOwnedPopout({ kind: 'instance' })
  await adapter.dispose()

  assert.equal(secondPopout.close.mock.calls.length, 1)
  assert.equal(hostWindow.close.mock.calls.length, 0)
})

test('embedded window adapter routes only bounded external URLs through Rhythm and keeps app paths isolated', async () => {
  const hostWindow = fakeWindow(1)
  const openExternal = vi.fn(async () => undefined)

  const adapter = createEmbeddedWindowAdapter({
    createPopout: () => fakeWindow(2),
    hostWindow,
    openExternal,
    openInTerminal: vi.fn(async () => undefined),
    rendererWebContents: { isDestroyed: () => false, send: vi.fn() }
  })

  await adapter.openExternal('https://example.test/docs')
  assert.deepEqual(openExternal.mock.calls, [['https://example.test/docs']])
  await assert.rejects(adapter.openExternal('file:///private/secret'), /Unsupported external URL protocol/)

  assert.deepEqual(
    resolveEmbeddedPaths({ assetRoot: '/tmp/artifact', userDataPath: '/tmp/rhythm-user-data' }),
    {
      assetRoot: '/tmp/artifact',
      desktopUserDataPath: '/tmp/rhythm-user-data/hermes-desktop',
      hermesHome: `${os.homedir()}/.hermes`
    }
  )
})
