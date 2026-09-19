#!/usr/bin/env node
// Rebuild the one native dependency used by the embedded host for Rhythm's
// Electron ABI, then stage exactly that output for artifact assembly.

import { rebuild } from '@electron/rebuild'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { stageNodePty } from './stage-native-deps.mjs'

const desktopRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const electronVersion = process.argv[2] ?? '40.10.2'

if (electronVersion !== '40.10.2') {
  throw new Error(`Rhythm embedded artifact requires Electron 40.10.2, received ${electronVersion}`)
}

await rebuild({
  buildPath: desktopRoot,
  electronVersion,
  arch: process.arch,
  onlyModules: ['node-pty'],
  force: true
})
stageNodePty()
console.log(`[embedded-native] rebuilt and staged node-pty for Electron ${electronVersion} (${process.platform}-${process.arch})`)
