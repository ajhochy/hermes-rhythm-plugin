import assert from 'node:assert/strict'

import { test, vi } from 'vitest'

const requestSingleInstanceLock = vi.fn()
const setPath = vi.fn()

vi.mock('electron', () => ({
  app: { requestSingleInstanceLock, setPath },
  ipcMain: { handle: vi.fn(), on: vi.fn() }
}))

// Load during module setup. Under the full Electron suite, a first dynamic
// transform inside the test body can wait on parallel workers past Vitest's
// per-test timeout even though the inert import itself is correct.
const runtime = await import('./desktop-native-runtime')

test('imports the shared runtime without taking over the host Electron app', async () => {
  assert.equal(requestSingleInstanceLock.mock.calls.length, 0)
  assert.equal(setPath.mock.calls.length, 0)
  assert.equal(runtime.isHostOwnedEmbeddedChannel('hermes:updates:apply'), true)
  assert.equal(runtime.isHostOwnedEmbeddedChannel('hermes:uninstall:run'), true)
  assert.equal(runtime.isHostOwnedEmbeddedChannel('hermes:requestMicrophoneAccess'), true)
  assert.equal(runtime.isHostOwnedEmbeddedChannel('hermes:selectPaths'), false)
})

test('embedded disposal stops only runtime-owned pool backends and clears their reaper', async () => {
  const clearReaper = vi.fn()
  const stopAll = vi.fn(async () => undefined)
  const reaper = {} as ReturnType<typeof setInterval>

  await runtime.disposeRuntimeOwnedPool({ clearReaper, idleReaper: reaper, stopAll })

  assert.deepEqual(clearReaper.mock.calls, [[reaper]])
  assert.deepEqual(stopAll.mock.calls, [[]])
})

test('embedded disposal preserves a borrowed primary but stops a runtime-spawned primary', async () => {
  const invalidate = vi.fn(() => ({ pid: 42 }))
  const stop = vi.fn()
  const waitForExit = vi.fn(async () => undefined)

  await runtime.disposeRuntimeOwnedPrimary({ invalidate, owned: false, stop, waitForExit })
  assert.equal(invalidate.mock.calls.length, 0)
  assert.equal(stop.mock.calls.length, 0)
  assert.equal(waitForExit.mock.calls.length, 0)

  await runtime.disposeRuntimeOwnedPrimary({ invalidate, owned: true, stop, waitForExit })
  assert.deepEqual(invalidate.mock.calls, [[]])
  assert.deepEqual(stop.mock.calls, [[{ pid: 42 }]])
  assert.deepEqual(waitForExit.mock.calls, [[{ pid: 42 }]])
})

test('external-link IPC retains standalone handling and delegates embedded links to the host adapter', async () => {
  const standalone = vi.fn(() => true)
  const embedded = vi.fn(async () => undefined)

  assert.equal(await runtime.openRuntimeExternal({ embedded: false, openEmbedded: embedded, openStandalone: standalone, rawUrl: 'file:///tmp/report.md' }), true)
  assert.deepEqual(standalone.mock.calls, [['file:///tmp/report.md']])

  assert.equal(await runtime.openRuntimeExternal({ embedded: true, openEmbedded: embedded, openStandalone: standalone, rawUrl: 'https://example.test/docs' }), true)
  assert.deepEqual(embedded.mock.calls, [['https://example.test/docs']])
  await assert.rejects(
    runtime.openRuntimeExternal({ embedded: true, openEmbedded: embedded, openStandalone: standalone, rawUrl: 'file:///tmp/report.md' }),
    /Unsupported external URL protocol/
  )
})

test('embedded runtime prefers the explicitly isolated Hermes home', () => {
  assert.equal(
    runtime.resolveEmbeddedHermesHome(true, '/tmp/rhythm-user-data/hermes-home'),
    '/tmp/rhythm-user-data/hermes-home'
  )
  assert.equal(runtime.resolveEmbeddedHermesHome(false, '/tmp/rhythm-user-data/hermes-home'), null)
})
