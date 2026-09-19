import assert from 'node:assert/strict'
import { existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'vitest'

import { buildEmbeddedArtifact } from './build-embedded-artifact.mjs'

function write(file, contents) {
  mkdirSync(path.dirname(file), { recursive: true })
  writeFileSync(file, contents)
}

test('buildEmbeddedArtifact packages the actual renderer, host, preload, and native dependencies with an inspectable manifest', () => {
  const root = mkdtempSync(path.join(os.tmpdir(), 'hermes-embedded-artifact-'))
  try {
    const rendererDir = path.join(root, 'dist')
    const hostFile = path.join(root, 'host', 'embedded-host.mjs')
    const preloadFile = path.join(root, 'preload', 'preload.cjs')
    const installStampFile = path.join(root, 'build', 'install-stamp.json')
    const nativeDir = path.join(root, 'native', 'node-pty')
    const artifactRoot = path.join(root, 'artifact')

    write(path.join(rendererDir, 'index.html'), '<div id="root"></div><script type="module" src="/assets/main.js"></script>')
    write(path.join(rendererDir, 'assets', 'main.js'), 'window.desktop = true')
    write(hostFile, 'export async function createEmbeddedHermesHost() {}')
    write(preloadFile, 'globalThis.hermesDesktop = {}')
    write(installStampFile, JSON.stringify({
      schemaVersion: 1,
      commit: '9c8dcf4230cbf3d386c29b730c5f82deea9523b0',
      branch: 'codex/hermes-desktop-embedded',
      builtAt: '2026-09-19T00:00:00.000Z',
      dirty: false,
      source: 'ci'
    }))
    write(path.join(nativeDir, 'package.json'), '{"name":"node-pty"}')
    write(path.join(nativeDir, 'prebuilds', 'darwin-arm64', 'pty.node'), 'native')

    const manifest = buildEmbeddedArtifact({
      artifactRoot,
      rendererDir,
      hostFile,
      installStampFile,
      preloadFile,
      nativeDependencies: [{ source: nativeDir, destination: 'native/node-pty' }],
      sourceCommit: '9c8dcf4230cbf3d386c29b730c5f82deea9523b0',
      electronMajor: 40
    })

    assert.deepEqual(manifest.files, {
      renderer: 'renderer/index.html',
      host: 'electron/embedded-host.mjs',
      preload: 'electron/preload.cjs'
    })
    assert.equal(manifest.product, 'hermes-desktop')
    assert.equal(manifest.schemaVersion, 1)
    assert.equal(manifest.sourceCommit, '9c8dcf4230cbf3d386c29b730c5f82deea9523b0')
    assert.equal(manifest.electronMajor, 40)
    assert.match(manifest.integrity['renderer/index.html'], /^sha256-[A-Za-z0-9+/]+={0,2}$/)
    assert.equal(readFileSync(path.join(artifactRoot, 'renderer', 'assets', 'main.js'), 'utf8'), 'window.desktop = true')
    assert.equal(readFileSync(path.join(artifactRoot, 'electron', 'embedded-host.mjs'), 'utf8'), 'export async function createEmbeddedHermesHost() {}')
    assert.equal(readFileSync(path.join(artifactRoot, 'electron', 'preload.cjs'), 'utf8'), 'globalThis.hermesDesktop = {}')
    assert.deepEqual(JSON.parse(readFileSync(path.join(artifactRoot, 'install-stamp.json'), 'utf8')), {
      schemaVersion: 1,
      commit: '9c8dcf4230cbf3d386c29b730c5f82deea9523b0',
      branch: 'codex/hermes-desktop-embedded',
      builtAt: '2026-09-19T00:00:00.000Z',
      dirty: false,
      source: 'ci'
    })
    assert.match(manifest.integrity['install-stamp.json'], /^sha256-[A-Za-z0-9+/]+={0,2}$/)
    assert.equal(readFileSync(path.join(artifactRoot, 'native', 'node-pty', 'package.json'), 'utf8'), '{"name":"node-pty"}')
    assert.deepEqual(JSON.parse(readFileSync(path.join(artifactRoot, 'manifest.json'), 'utf8')), manifest)
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})

test('buildEmbeddedArtifact refuses an incomplete bridge instead of emitting a loadable-looking manifest', () => {
  const root = mkdtempSync(path.join(os.tmpdir(), 'hermes-embedded-artifact-'))
  try {
    const rendererDir = path.join(root, 'dist')
    const artifactRoot = path.join(root, 'artifact')
    write(path.join(rendererDir, 'index.html'), '<div id="root"></div>')

    assert.throws(
      () => buildEmbeddedArtifact({
        artifactRoot,
        rendererDir,
        hostFile: path.join(root, 'missing-host.mjs'),
        preloadFile: path.join(root, 'missing-preload.cjs'),
        sourceCommit: '9c8dcf4230cbf3d386c29b730c5f82deea9523b0',
        electronMajor: 40
      }),
      /embedded host/i
    )
    assert.equal(existsSync(path.join(artifactRoot, 'manifest.json')), false)
  } catch (error) {
    if (error?.code === 'ENOENT') {
      // The build must not leave a manifest behind when the required bridge is absent.
      assert.equal(error.path.endsWith(path.join('artifact', 'manifest.json')), true)
    } else {
      throw error
    }
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})
