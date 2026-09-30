#!/usr/bin/env node
// Build the payload Rhythm loads into its owned WebContentsView. This deliberately
// copies from this fork's build output; `~/.hermes` is never an input.

import { createHash } from 'node:crypto'
import {
  cpSync,
  existsSync,
  lstatSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
  writeFileSync
} from 'node:fs'
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from 'node:path'
import { execFileSync } from 'node:child_process'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

const desktopRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const repositoryRoot = resolve(desktopRoot, '..', '..')
const require = createRequire(import.meta.url)
const REQUIRED_FILES = Object.freeze({
  renderer: 'renderer/index.html',
  host: 'electron/embedded-host.mjs',
  preload: 'electron/preload.cjs'
})
const THEMES_DIR = 'themes'

function assertFile(filePath, label) {
  if (!existsSync(filePath) || !lstatSync(filePath).isFile()) {
    throw new Error(`Embedded ${label} is missing: ${filePath}`)
  }
}

function assertDirectory(directory, label) {
  if (!existsSync(directory) || !lstatSync(directory).isDirectory()) {
    throw new Error(`Embedded ${label} is missing: ${directory}`)
  }
}

function assertNoSymlinks(directory, label) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const child = join(directory, entry.name)
    if (entry.isSymbolicLink()) {
      throw new Error(`Embedded ${label} must not contain symlinks: ${child}`)
    }
    if (entry.isDirectory()) {
      assertNoSymlinks(child, label)
    }
  }
}

function assertInside(root, candidate, label) {
  const rel = relative(root, candidate)
  if (rel === '' || rel === '..' || rel.startsWith(`..${sep}`) || isAbsolute(rel)) {
    throw new Error(`Embedded ${label} must be inside the artifact root: ${candidate}`)
  }
}

function sha256(filePath) {
  return `sha256-${createHash('sha256').update(readFileSync(filePath)).digest('base64')}`
}

function collectIntegrity(root) {
  const integrity = {}
  const visit = directory => {
    for (const entry of readdirSync(directory, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const absolute = join(directory, entry.name)
      if (entry.isDirectory()) {
        visit(absolute)
      } else if (entry.isFile()) {
        integrity[relative(root, absolute).split(sep).join('/')] = sha256(absolute)
      }
    }
  }
  visit(root)
  return integrity
}

function assertSourceCommit(sourceCommit) {
  if (!/^[0-9a-f]{40}$/i.test(sourceCommit ?? '')) {
    throw new Error(`Embedded artifact requires a full 40-character source commit, received: ${sourceCommit ?? '<none>'}`)
  }
}

function assertInstallStamp(installStampFile, sourceCommit) {
  assertFile(installStampFile, 'install stamp')
  if (lstatSync(installStampFile).isSymbolicLink()) {
    throw new Error('Embedded install stamp must not be a symlink')
  }

  let stamp
  try {
    stamp = JSON.parse(readFileSync(installStampFile, 'utf8'))
  } catch (error) {
    throw new Error(`Embedded install stamp is not valid JSON: ${error instanceof Error ? error.message : String(error)}`)
  }

  if (stamp?.schemaVersion !== 1 || !/^[0-9a-f]{40}$/i.test(stamp.commit ?? '')) {
    throw new Error('Embedded install stamp requires schemaVersion 1 and a full source commit')
  }
  if (stamp.commit !== sourceCommit) {
    throw new Error(`Embedded install stamp commit ${stamp.commit} does not match artifact source commit ${sourceCommit}`)
  }
}

/**
 * Create an immutable-on-disk payload that Rhythm can verify before loading.
 * Exposed for behavioral tests; callers provide concrete build products rather
 * than a mutable user installation or a fake renderer facade.
 */
const SEMVER_LIKE = /^\d+\.\d+\.\d+/

export function buildEmbeddedArtifact({
  artifactRoot,
  rendererDir,
  hostFile,
  installStampFile,
  preloadFile,
  nativeDependencies = [],
  licenseFiles = [],
  themeFiles = [],
  sourceCommit,
  electronMajor,
  sourceDirty = false,
  sourceDiffHash,
  // v2 manifest fields (#1570-b). Rhythm's verifier only requires these for an
  // *installed* (updated) artifact -- schemaVersion stays 1 here, so an older
  // Rhythm build ignores them and a factory build stays exactly as backward
  // compatible as before. Optional so every existing caller/test is unaffected;
  // `main()` below always supplies real values for a CLI build.
  hermesVersion,
  hostApiVersion,
  electronVersion,
  sequence
}) {
  assertSourceCommit(sourceCommit)
  if (!Number.isInteger(electronMajor) || electronMajor < 1) {
    throw new Error(`Embedded artifact requires a positive Electron major, received: ${electronMajor}`)
  }
  if (hermesVersion !== undefined && !SEMVER_LIKE.test(hermesVersion)) {
    throw new Error(`Embedded artifact hermesVersion must be a semver string, received: ${hermesVersion}`)
  }
  if (hostApiVersion !== undefined && (!Number.isInteger(hostApiVersion) || hostApiVersion < 1)) {
    throw new Error(`Embedded artifact hostApiVersion must be a positive integer, received: ${hostApiVersion}`)
  }
  if (electronVersion !== undefined && !SEMVER_LIKE.test(electronVersion)) {
    throw new Error(`Embedded artifact electronVersion must be a semver string, received: ${electronVersion}`)
  }
  if (sequence !== undefined && (!Number.isInteger(sequence) || sequence < 1)) {
    throw new Error(`Embedded artifact sequence must be a positive integer, received: ${sequence}`)
  }

  const output = resolve(artifactRoot)
  const renderer = resolve(rendererDir)
  const host = resolve(hostFile)
  const preload = resolve(preloadFile)

  assertFile(join(renderer, 'index.html'), 'renderer index.html')
  assertFile(host, 'host')
  assertFile(preload, 'preload')
  assertInstallStamp(installStampFile, sourceCommit)
  if (lstatSync(host).isSymbolicLink() || lstatSync(preload).isSymbolicLink()) {
    throw new Error('Embedded host and preload must not be symlinks')
  }
  assertNoSymlinks(renderer, 'renderer')

  if (sourceDirty && !/^[0-9a-f]{64}$/i.test(sourceDiffHash ?? '')) {
    throw new Error('Dirty embedded artifacts require a SHA-256 sourceDiffHash')
  }

  for (const dependency of nativeDependencies) {
    assertDirectory(dependency.source, `native dependency ${dependency.destination}`)
    assertNoSymlinks(dependency.source, `native dependency ${dependency.destination}`)
    assertInside(output, resolve(output, dependency.destination), `native dependency destination ${dependency.destination}`)
  }

  for (const license of licenseFiles) {
    assertFile(license.source, `license ${license.destination}`)
    if (lstatSync(license.source).isSymbolicLink()) {
      throw new Error(`Embedded license must not be a symlink: ${license.source}`)
    }
    assertInside(output, resolve(output, license.destination), `license destination ${license.destination}`)
  }

  // Generic theme JSON (#1543-b): any embedding host may bundle skin data
  // here, loaded only in embedded mode. This builder has no opinion on the
  // theme's contents beyond "valid JSON" -- a bad source file fails the BUILD
  // rather than shipping unverifiable bytes into a signed artifact.
  for (const theme of themeFiles) {
    assertFile(theme.source, `theme ${theme.destination}`)
    if (lstatSync(theme.source).isSymbolicLink()) {
      throw new Error(`Embedded theme file must not be a symlink: ${theme.source}`)
    }
    if (!theme.destination.startsWith(`${THEMES_DIR}/`) || !theme.destination.endsWith('.json')) {
      throw new Error(`Embedded theme destination must be themes/<name>.json, received: ${theme.destination}`)
    }
    assertInside(output, resolve(output, theme.destination), `theme destination ${theme.destination}`)
    try {
      JSON.parse(readFileSync(theme.source, 'utf8'))
    } catch (error) {
      throw new Error(`Embedded theme file is not valid JSON: ${theme.source} (${error instanceof Error ? error.message : String(error)})`)
    }
  }

  rmSync(output, { recursive: true, force: true })
  mkdirSync(output, { recursive: true })
  cpSync(renderer, join(output, 'renderer'), { recursive: true })
  mkdirSync(join(output, 'electron'), { recursive: true })
  cpSync(host, join(output, REQUIRED_FILES.host))
  cpSync(preload, join(output, REQUIRED_FILES.preload))
  // Preserve the build's real pinned-ref metadata byte-for-byte. The embedded
  // runtime reads it from its asset root; it must never infer a release stamp
  // from Rhythm's app version or rewrite a dirty local stamp as a release one.
  cpSync(installStampFile, join(output, 'install-stamp.json'))

  for (const dependency of nativeDependencies) {
    cpSync(dependency.source, join(output, dependency.destination), { recursive: true })
  }

  // Keep the exact license bytes beside the immutable payload. Native staging
  // deliberately copies only executable/runtime files, so these notices would
  // otherwise disappear from the embedded artifact.
  for (const license of licenseFiles) {
    const destination = join(output, license.destination)
    mkdirSync(dirname(destination), { recursive: true })
    cpSync(license.source, destination)
  }

  for (const theme of themeFiles) {
    const destination = join(output, theme.destination)
    mkdirSync(dirname(destination), { recursive: true })
    cpSync(theme.source, destination)
  }

  const manifest = {
    schemaVersion: 1,
    product: 'hermes-desktop',
    sourceCommit,
    dirty: sourceDirty,
    electronMajor,
    files: REQUIRED_FILES,
    integrity: collectIntegrity(output),
    ...(sourceDirty ? { sourceDirty: true, sourceDiffHash } : {}),
    ...(hermesVersion !== undefined ? { hermesVersion } : {}),
    ...(hostApiVersion !== undefined ? { hostApiVersion } : {}),
    ...(electronVersion !== undefined ? { electronVersion } : {}),
    ...(sequence !== undefined ? { sequence } : {})
  }
  writeFileSync(join(output, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`)
  return manifest
}

function arg(name) {
  const index = process.argv.indexOf(name)
  return index === -1 ? undefined : process.argv[index + 1]
}

function repeatableArg(name) {
  const values = []
  for (let index = process.argv.indexOf(name); index !== -1; index = process.argv.indexOf(name, index + 1)) {
    values.push(process.argv[index + 1])
  }
  return values
}

/** `--theme-json <path>` (repeatable): each becomes `themes/<basename>` in
 *  the artifact. Generic -- any embedding host may pass any file. */
function themeFilesFromArgs() {
  return repeatableArg('--theme-json').map(source => ({ source, destination: `${THEMES_DIR}/${basename(source)}` }))
}

/**
 * `--sequence` is optional: the factory build (`npm run build:rhythm-embedded`,
 * schemaVersion:1) never passes it and Rhythm's verifier never reads sequence
 * on that path, so an absent flag must produce `undefined` (buildEmbeddedArtifact
 * omits the field entirely rather than shipping a fake "1" forever). A future
 * installed-update release/packaging mode (schemaVersion 2, #1570-c/#1570-d)
 * MUST pass --sequence explicitly, since Rhythm refuses a replayed/older
 * installed artifact without it; when provided it is parsed as an integer and
 * buildEmbeddedArtifact's own validation rejects anything but a positive one.
 * Exported (and `argv`-injectable) for behavioral tests of this CLI parsing
 * without needing a full `dist/` build.
 */
export function sequenceFromArgs(argv = process.argv) {
  const index = argv.indexOf('--sequence')
  return index === -1 ? undefined : Number.parseInt(argv[index + 1], 10)
}

function currentCommit() {
  return execFileSync('git', ['rev-parse', 'HEAD'], { cwd: repositoryRoot, encoding: 'utf8' }).trim()
}

function sourceState({ allowDirty }) {
  const diff = execFileSync('git', ['diff', '--binary', 'HEAD', '--'], { cwd: repositoryRoot, encoding: 'utf8' })
  const untracked = execFileSync('git', ['ls-files', '--others', '--exclude-standard'], {
    cwd: repositoryRoot,
    encoding: 'utf8'
  })
  const dirty = Boolean(diff || untracked)
  if (dirty && !allowDirty) {
    throw new Error('Embedded artifact source is dirty. Commit it first, or use --allow-dirty for a non-release local proof.')
  }
  return dirty
    ? { sourceDirty: true, sourceDiffHash: createHash('sha256').update(`${diff}\n${untracked}`).digest('hex') }
    : {}
}

function resolvePackageRoot(packageName, packageJson = false) {
  const entry = require.resolve(packageJson ? `${packageName}/package.json` : packageName, {
    paths: [desktopRoot]
  })

  return dirname(entry)
}

/**
 * The Hermes *agent's* version (pyproject.toml), not this Desktop package's
 * own package.json (0.17.0 as of writing). Rhythm's HERMES_DESKTOP_MINIMUM_VERSION
 * (0.20.5) is written against this scheme -- apps/desktop/package.json would
 * never satisfy it -- so this is the value manifest.hermesVersion must carry.
 */
function hermesAgentVersion() {
  const pyproject = readFileSync(join(repositoryRoot, 'pyproject.toml'), 'utf8')
  const match = /^version\s*=\s*"([^"]+)"/m.exec(pyproject)
  if (!match) {
    throw new Error('Could not read the Hermes agent version from pyproject.toml')
  }
  return match[1]
}

/** The exact installed Electron version, so Rhythm can gate an installed
 *  artifact update on more than just the major (native addons are ABI-bound
 *  to the exact build, not the major). */
function installedElectronVersion() {
  return JSON.parse(readFileSync(join(resolvePackageRoot('electron', true), 'package.json'), 'utf8')).version
}

/** The compiled host module's own declared API version (#1543-b/#1570-b),
 *  read from the SAME bytes being packaged so the manifest can never drift
 *  from what actually ships. Exported for behavioral tests. */
export async function hostApiVersionOf(hostFile) {
  const source = readFileSync(hostFile, 'utf8')
  const match = /\b(?:const|let|var)\s+EMBEDDED_HOST_API_VERSION\s*=\s*(\d+)\b/.exec(source)
  const version = match ? Number.parseInt(match[1], 10) : undefined
  if (!Number.isInteger(version) || version < 1) {
    throw new Error(`Embedded host module does not export a valid EMBEDDED_HOST_API_VERSION: ${hostFile}`)
  }
  return version
}

function embeddedLicenseFiles(nativeDependenciesRoot) {
  const licenses = [
    { source: join(repositoryRoot, 'LICENSE'), destination: 'licenses/LICENSE' },
    {
      source: join(resolvePackageRoot('node-pty', true), 'LICENSE'),
      destination: 'licenses/node-pty/LICENSE'
    }
  ]

  // get-windows is optional on targets where it is not staged. Include its
  // license precisely when its executable payload is included.
  if (existsSync(join(nativeDependenciesRoot, 'get-windows'))) {
    licenses.push({
      source: join(resolvePackageRoot('get-windows'), 'license'),
      destination: 'licenses/get-windows/LICENSE'
    })
  }

  return licenses
}

async function main() {
  const artifactRoot = resolve(arg('--output') ?? join(desktopRoot, 'build', 'rhythm-embedded'))
  const electronMajor = Number.parseInt(arg('--electron-major') ?? '40', 10)
  const sourceCommit = arg('--source-commit') ?? currentCommit()
  const source = sourceState({ allowDirty: process.argv.includes('--allow-dirty') })
  const nativeDependenciesRoot = join(desktopRoot, 'dist', 'node_modules')
  const hostFile = join(desktopRoot, 'dist', 'embedded-host.mjs')
  const sequence = sequenceFromArgs()
  const manifest = buildEmbeddedArtifact({
    artifactRoot,
    rendererDir: join(desktopRoot, 'dist'),
    hostFile,
    installStampFile: join(desktopRoot, 'build', 'install-stamp.json'),
    preloadFile: join(desktopRoot, 'dist', 'electron-preload.js'),
    nativeDependencies: [{
      source: nativeDependenciesRoot,
      destination: 'electron/node_modules'
    }],
    licenseFiles: embeddedLicenseFiles(nativeDependenciesRoot),
    themeFiles: themeFilesFromArgs(),
    sourceCommit,
    electronMajor,
    hermesVersion: hermesAgentVersion(),
    hostApiVersion: await hostApiVersionOf(hostFile),
    electronVersion: installedElectronVersion(),
    sequence,
    ...source
  })
  console.log(`[embedded-artifact] wrote ${artifactRoot} (${Object.keys(manifest.integrity).length} verified files)`)
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(error => {
    console.error(error instanceof Error ? error.message : error)
    process.exitCode = 1
  })
}
