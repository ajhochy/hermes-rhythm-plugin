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
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path'
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
export function buildEmbeddedArtifact({
  artifactRoot,
  rendererDir,
  hostFile,
  installStampFile,
  preloadFile,
  nativeDependencies = [],
  licenseFiles = [],
  sourceCommit,
  electronMajor,
  sourceDirty = false,
  sourceDiffHash
}) {
  assertSourceCommit(sourceCommit)
  if (!Number.isInteger(electronMajor) || electronMajor < 1) {
    throw new Error(`Embedded artifact requires a positive Electron major, received: ${electronMajor}`)
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

  const manifest = {
    schemaVersion: 1,
    product: 'hermes-desktop',
    sourceCommit,
    electronMajor,
    files: REQUIRED_FILES,
    integrity: collectIntegrity(output),
    ...(sourceDirty ? { sourceDirty: true, sourceDiffHash } : {})
  }
  writeFileSync(join(output, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`)
  return manifest
}

function arg(name) {
  const index = process.argv.indexOf(name)
  return index === -1 ? undefined : process.argv[index + 1]
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

function main() {
  const artifactRoot = resolve(arg('--output') ?? join(desktopRoot, 'build', 'rhythm-embedded'))
  const electronMajor = Number.parseInt(arg('--electron-major') ?? '40', 10)
  const sourceCommit = arg('--source-commit') ?? currentCommit()
  const source = sourceState({ allowDirty: process.argv.includes('--allow-dirty') })
  const nativeDependenciesRoot = join(desktopRoot, 'dist', 'node_modules')
  const manifest = buildEmbeddedArtifact({
    artifactRoot,
    rendererDir: join(desktopRoot, 'dist'),
    hostFile: join(desktopRoot, 'dist', 'embedded-host.mjs'),
    installStampFile: join(desktopRoot, 'build', 'install-stamp.json'),
    preloadFile: join(desktopRoot, 'dist', 'electron-preload.js'),
    nativeDependencies: [{
      source: nativeDependenciesRoot,
      destination: 'electron/node_modules'
    }],
    licenseFiles: embeddedLicenseFiles(nativeDependenciesRoot),
    sourceCommit,
    electronMajor,
    ...source
  })
  console.log(`[embedded-artifact] wrote ${artifactRoot} (${Object.keys(manifest.integrity).length} verified files)`)
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main()
}
