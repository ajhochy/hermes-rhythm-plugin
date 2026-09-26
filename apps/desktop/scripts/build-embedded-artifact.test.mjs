import assert from 'node:assert/strict'
import { existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'vitest'

import { buildEmbeddedArtifact, hostApiVersionOf, sequenceFromArgs } from './build-embedded-artifact.mjs'

function write(file, contents) {
  mkdirSync(path.dirname(file), { recursive: true })
  writeFileSync(file, contents)
}

function minimalArtifactInputs(root) {
  const rendererDir = path.join(root, 'dist')
  const hostFile = path.join(root, 'host', 'embedded-host.mjs')
  const preloadFile = path.join(root, 'preload', 'preload.cjs')
  const installStampFile = path.join(root, 'build', 'install-stamp.json')
  write(path.join(rendererDir, 'index.html'), '<div id="root"></div>')
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
  return {
    rendererDir,
    hostFile,
    preloadFile,
    installStampFile,
    sourceCommit: '9c8dcf4230cbf3d386c29b730c5f82deea9523b0',
    electronMajor: 40
  }
}

test('buildEmbeddedArtifact packages the actual renderer, host, preload, and native dependencies with an inspectable manifest', () => {
  const root = mkdtempSync(path.join(os.tmpdir(), 'hermes-embedded-artifact-'))
  try {
    const rendererDir = path.join(root, 'dist')
    const hostFile = path.join(root, 'host', 'embedded-host.mjs')
    const preloadFile = path.join(root, 'preload', 'preload.cjs')
    const installStampFile = path.join(root, 'build', 'install-stamp.json')
    const nativeDir = path.join(root, 'native', 'node-pty')
    const sourceLicense = path.join(root, 'LICENSE')
    const nodePtyLicense = path.join(root, 'native-source', 'node-pty', 'LICENSE')
    const getWindowsLicense = path.join(root, 'native-source', 'get-windows', 'license')
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
    write(sourceLicense, 'Nous Research license')
    write(nodePtyLicense, 'node-pty license')
    write(getWindowsLicense, 'get-windows license')

    const manifest = buildEmbeddedArtifact({
      artifactRoot,
      rendererDir,
      hostFile,
      installStampFile,
      preloadFile,
      nativeDependencies: [{ source: nativeDir, destination: 'native/node-pty' }],
      licenseFiles: [
        { source: sourceLicense, destination: 'licenses/LICENSE' },
        { source: nodePtyLicense, destination: 'licenses/node-pty/LICENSE' },
        { source: getWindowsLicense, destination: 'licenses/get-windows/LICENSE' }
      ],
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
    assert.equal(manifest.dirty, false)
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
    assert.equal(readFileSync(path.join(artifactRoot, 'licenses', 'LICENSE'), 'utf8'), 'Nous Research license')
    assert.equal(readFileSync(path.join(artifactRoot, 'licenses', 'node-pty', 'LICENSE'), 'utf8'), 'node-pty license')
    assert.equal(readFileSync(path.join(artifactRoot, 'licenses', 'get-windows', 'LICENSE'), 'utf8'), 'get-windows license')
    assert.match(manifest.integrity['licenses/LICENSE'], /^sha256-[A-Za-z0-9+/]+={0,2}$/)
    assert.match(manifest.integrity['licenses/node-pty/LICENSE'], /^sha256-[A-Za-z0-9+/]+={0,2}$/)
    assert.match(manifest.integrity['licenses/get-windows/LICENSE'], /^sha256-[A-Za-z0-9+/]+={0,2}$/)
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

// #1543-b: generic bundled theme JSON, so an embedding host's default skin
// works offline without its plugin installed. Covered by the same full-tree
// integrity check as every other artifact file -- no extra manifest wiring.
test('buildEmbeddedArtifact bundles generic theme JSON under themes/, covered by integrity', () => {
  const root = mkdtempSync(path.join(os.tmpdir(), 'hermes-embedded-artifact-theme-'))
  try {
    const artifactRoot = path.join(root, 'artifact')
    const themeSource = path.join(root, 'theme-source', 'example.json')
    write(themeSource, JSON.stringify({ name: 'example', colors: { primary: '#000000' } }))

    const manifest = buildEmbeddedArtifact({
      artifactRoot,
      ...minimalArtifactInputs(root),
      themeFiles: [{ source: themeSource, destination: 'themes/example.json' }]
    })

    assert.deepEqual(
      JSON.parse(readFileSync(path.join(artifactRoot, 'themes', 'example.json'), 'utf8')),
      { name: 'example', colors: { primary: '#000000' } }
    )
    assert.match(manifest.integrity['themes/example.json'], /^sha256-[A-Za-z0-9+/]+={0,2}$/)
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})

// #1570-b: the v2 fields Rhythm's installed-artifact verifier reads
// (hermesVersion, hostApiVersion, electronVersion, sequence). schemaVersion
// stays 1 here -- Rhythm only requires these under artifactSource:'installed'
// -- so an older Rhythm build, and every existing call site of this function
// that omits them, are unaffected.
test('buildEmbeddedArtifact includes hermesVersion, hostApiVersion, electronVersion and sequence when supplied', () => {
  const root = mkdtempSync(path.join(os.tmpdir(), 'hermes-embedded-artifact-v2-'))
  try {
    const artifactRoot = path.join(root, 'artifact')
    const manifest = buildEmbeddedArtifact({
      artifactRoot,
      ...minimalArtifactInputs(root),
      hermesVersion: '0.20.4',
      hostApiVersion: 1,
      electronVersion: '40.10.2',
      sequence: 7
    })

    assert.equal(manifest.schemaVersion, 1)
    assert.equal(manifest.hermesVersion, '0.20.4')
    assert.equal(manifest.hostApiVersion, 1)
    assert.equal(manifest.electronVersion, '40.10.2')
    assert.equal(manifest.sequence, 7)
    assert.deepEqual(JSON.parse(readFileSync(path.join(artifactRoot, 'manifest.json'), 'utf8')), manifest)
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})

test('buildEmbeddedArtifact omits the v2 fields entirely when the caller does not supply them', () => {
  const root = mkdtempSync(path.join(os.tmpdir(), 'hermes-embedded-artifact-v2-omit-'))
  try {
    const manifest = buildEmbeddedArtifact({ artifactRoot: path.join(root, 'artifact'), ...minimalArtifactInputs(root) })
    for (const key of ['hermesVersion', 'hostApiVersion', 'electronVersion', 'sequence']) {
      assert.equal(key in manifest, false, `${key} must not appear when omitted`)
    }
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})

test('buildEmbeddedArtifact rejects a malformed v2 field instead of shipping an unverifiable value', () => {
  const root = mkdtempSync(path.join(os.tmpdir(), 'hermes-embedded-artifact-v2-invalid-'))
  try {
    const base = { artifactRoot: path.join(root, 'artifact'), ...minimalArtifactInputs(root) }
    assert.throws(() => buildEmbeddedArtifact({ ...base, hermesVersion: 'not-a-semver' }), /hermesVersion/)
    assert.throws(() => buildEmbeddedArtifact({ ...base, hostApiVersion: 0 }), /hostApiVersion/)
    assert.throws(() => buildEmbeddedArtifact({ ...base, hostApiVersion: 1.5 }), /hostApiVersion/)
    assert.throws(() => buildEmbeddedArtifact({ ...base, electronVersion: 'forty' }), /electronVersion/)
    // sequence is optional (see sequenceFromArgs), but a *present*, malformed
    // value (e.g. --sequence not-a-number, or a caller passing NaN/0 directly)
    // must still fail rather than shipping an unverifiable value.
    assert.throws(() => buildEmbeddedArtifact({ ...base, sequence: Number.NaN }), /sequence/)
    assert.throws(() => buildEmbeddedArtifact({ ...base, sequence: 0 }), /sequence/)
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})

// Regression: `npm run build:rhythm-embedded` (package.json) runs this script
// with `--electron-major 40` and NO --sequence -- the standard factory build
// Rhythm bundles. It must keep succeeding with sequence simply omitted from
// the manifest, not throw on a NaN default.
test('sequenceFromArgs: absent for the standard factory build, parsed when present, malformed passes through unvalidated for buildEmbeddedArtifact to reject', () => {
  const factoryBuildArgv = ['node', 'build-embedded-artifact.mjs', '--electron-major', '40']
  assert.equal(sequenceFromArgs(factoryBuildArgv), undefined)

  assert.equal(sequenceFromArgs(['node', 'script.mjs', '--sequence', '7']), 7)

  const invalid = sequenceFromArgs(['node', 'script.mjs', '--sequence', 'not-a-number'])
  assert.ok(Number.isNaN(invalid))
})

test('buildEmbeddedArtifact accepts the exact sequence:undefined the factory-build CLI path now produces', () => {
  const root = mkdtempSync(path.join(os.tmpdir(), 'hermes-embedded-artifact-no-sequence-'))
  try {
    const manifest = buildEmbeddedArtifact({
      artifactRoot: path.join(root, 'artifact'),
      ...minimalArtifactInputs(root),
      sequence: sequenceFromArgs(['node', 'build-embedded-artifact.mjs', '--electron-major', '40'])
    })
    assert.equal('sequence' in manifest, false)
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})

test('hostApiVersionOf reads EMBEDDED_HOST_API_VERSION from the actual compiled host bytes', async () => {
  const root = mkdtempSync(path.join(os.tmpdir(), 'hermes-embedded-host-api-version-'))
  try {
    const hostFile = path.join(root, 'embedded-host.mjs')
    write(hostFile, "import { definitelyNotAnExport } from 'node:fs'\nexport const EMBEDDED_HOST_API_VERSION = 3\nexport async function createEmbeddedHermesHost() { return definitelyNotAnExport }\n")
    assert.equal(await hostApiVersionOf(hostFile), 3)

    const badHostFile = path.join(root, 'embedded-host-bad.mjs')
    write(badHostFile, 'export async function createEmbeddedHermesHost() {}\n')
    await assert.rejects(hostApiVersionOf(badHostFile), /EMBEDDED_HOST_API_VERSION/)
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})

test('buildEmbeddedArtifact rejects a theme file outside themes/ or that is not valid JSON', () => {
  const root = mkdtempSync(path.join(os.tmpdir(), 'hermes-embedded-artifact-theme-invalid-'))
  try {
    const artifactRoot = path.join(root, 'artifact')
    const outsideDestination = path.join(root, 'theme-source', 'escape.json')
    write(outsideDestination, '{}')

    assert.throws(
      () => buildEmbeddedArtifact({
        artifactRoot,
        ...minimalArtifactInputs(root),
        themeFiles: [{ source: outsideDestination, destination: '../escape.json' }]
      }),
      /theme destination/i
    )

    const corruptSource = path.join(root, 'theme-source', 'corrupt.json')
    write(corruptSource, '{ not valid json')

    assert.throws(
      () => buildEmbeddedArtifact({
        artifactRoot,
        ...minimalArtifactInputs(root),
        themeFiles: [{ source: corruptSource, destination: 'themes/corrupt.json' }]
      }),
      /not valid JSON/i
    )
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})
