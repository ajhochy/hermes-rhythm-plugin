import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { test } from 'vitest'

import { canImportHermesCli, execProbeSync, verifyHermesCli } from './backend-probes'
import { resolveVenvHermesCommand } from './windows-hermes-path'

const HOSTILE_KEYS = [
  'OPENAI_API_KEY',
  'ANTHROPIC_API_KEY',
  'HTTPS_PROXY',
  'NODE_OPTIONS',
  'NODE_PATH',
  'HERMES_DASHBOARD_SESSION_TOKEN'
] as const

function syntheticProbe() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'hermes-probe-env-contract-'))
  const names = path.join(root, 'observed-names')
  const executable = path.join(root, 'synthetic-hermes')
  fs.writeFileSync(executable, `#!/bin/sh
: > '${names}'
[ -n "$OPENAI_API_KEY" ] && echo OPENAI_API_KEY >> '${names}'
[ -n "$ANTHROPIC_API_KEY" ] && echo ANTHROPIC_API_KEY >> '${names}'
[ -n "$HTTPS_PROXY" ] && echo HTTPS_PROXY >> '${names}'
[ -n "$NODE_OPTIONS" ] && echo NODE_OPTIONS >> '${names}'
[ -n "$NODE_PATH" ] && echo NODE_PATH >> '${names}'
[ -n "$HERMES_DASHBOARD_SESSION_TOKEN" ] && echo HERMES_DASHBOARD_SESSION_TOKEN >> '${names}'
[ "$PYTHONPATH" = '${root}/hermes-source' ] && echo DERIVED_PYTHONPATH >> '${names}'
[ "$PATH" = '/usr/bin:/bin' ] && echo CLEAN_PATH >> '${names}'
exit 0
`)
  fs.chmodSync(executable, 0o755)
  return { executable, names, root, dispose: () => fs.rmSync(root, { recursive: true, force: true }) }
}

function withSyntheticAmbient<T>(body: () => T): T {
  const previous = Object.fromEntries([...HOSTILE_KEYS, 'PYTHONPATH'].map(key => [key, process.env[key]]))
  try {
    process.env.OPENAI_API_KEY = 'synthetic-credential-never-forward'
    process.env.ANTHROPIC_API_KEY = 'synthetic-credential-never-forward'
    process.env.HTTPS_PROXY = 'http://synthetic-proxy.invalid:9999'
    process.env.NODE_OPTIONS = '--synthetic-loader-option'
    process.env.NODE_PATH = '/synthetic-loader'
    process.env.HERMES_DASHBOARD_SESSION_TOKEN = 'synthetic-dashboard-token-never-forward'
    process.env.PYTHONPATH = '/synthetic-python-loader'
    return body()
  } finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key]
      else process.env[key] = value
    }
  }
}

test('embedded CLI version probe uses the explicit clean environment, not ambient credentials or loader/proxy settings', () => {
  const fixture = syntheticProbe()
  try {
    withSyntheticAmbient(() => {
      assert.equal(verifyHermesCli(fixture.executable, {
        env: { PATH: '/usr/bin:/bin', PYTHONPATH: `${fixture.root}/hermes-source` }
      }), true)
    })
    assert.deepEqual(fs.readFileSync(fixture.names, 'utf8').trim().split('\n'), ['DERIVED_PYTHONPATH', 'CLEAN_PATH'])
  } finally {
    fixture.dispose()
  }
})

test('embedded Python import probe replaces ambient environment while retaining the derived source import path', () => {
  const fixture = syntheticProbe()
  try {
    withSyntheticAmbient(() => {
      assert.equal(canImportHermesCli(fixture.executable, {
        baseEnv: { PATH: '/usr/bin:/bin' },
        env: { PYTHONPATH: `${fixture.root}/hermes-source` }
      }), true)
    })
    assert.deepEqual(fs.readFileSync(fixture.names, 'utf8').trim().split('\n'), ['DERIVED_PYTHONPATH', 'CLEAN_PATH'])
  } finally {
    fixture.dispose()
  }
})

test('embedded Windows venv shim probes the exact Python interpreter with clean derived import paths', () => {
  const fixture = syntheticProbe()
  const root = path.join(fixture.root, 'hermes-source')
  const venv = path.join(root, 'venv')
  const python = path.join(venv, 'Scripts', 'python.exe')
  const shim = path.join(venv, 'Scripts', 'hermes.exe')
  let backendEnvBase: NodeJS.ProcessEnv | undefined
  fs.mkdirSync(path.dirname(python), { recursive: true })
  fs.copyFileSync(fixture.executable, python)
  fs.chmodSync(python, 0o755)
  try {
    withSyntheticAmbient(() => {
      const backend = resolveVenvHermesCommand(shim, ['serve'], {
        isWindows: true,
        isCommandScript: () => false,
        fileExists: file => file === python,
        directoryExists: file => file === root,
        canImportHermesCli,
        getVenvPython: () => python,
        getVenvSitePackagesEntries: () => [path.join(venv, 'site-packages')],
        buildDesktopBackendEnv: options => {
          backendEnvBase = options.currentEnv
          return {}
        },
        probeBaseEnv: { PATH: '/usr/bin:/bin' },
        hermesHome: path.join(fixture.root, 'home'),
        resolvePath: path.resolve,
        dirname: path.dirname,
        basename: path.basename
      })
      assert.equal(backend?.command, python, 'the verified interpreter must remain the chosen backend')
      assert.deepEqual(backend?.args, ['-m', 'hermes_cli.main', 'serve'])
      assert.deepEqual(backendEnvBase, { PATH: '/usr/bin:/bin' }, 'Windows venv backend path derives from the clean base')
    })
    assert.deepEqual(fs.readFileSync(fixture.names, 'utf8').trim().split('\n'), ['DERIVED_PYTHONPATH', 'CLEAN_PATH'])
  } finally {
    fixture.dispose()
  }
})

test('timeout retry receives the same clean probe environment on both executions', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'hermes-probe-retry-'))
  const executable = path.join(root, 'probe')
  const observed = path.join(root, 'observed')
  const marker = path.join(root, 'first-run')
  fs.writeFileSync(executable, `#!/bin/sh
if [ -n "$OPENAI_API_KEY$ANTHROPIC_API_KEY$HTTPS_PROXY$NODE_OPTIONS$NODE_PATH$HERMES_DASHBOARD_SESSION_TOKEN" ]; then echo LEAK >> '${observed}'; else echo CLEAN >> '${observed}'; fi
if [ ! -e '${marker}' ]; then touch '${marker}'; sleep 1; fi
`)
  fs.chmodSync(executable, 0o755)
  try {
    withSyntheticAmbient(() => execProbeSync(executable, [], {
      env: { PATH: '/usr/bin:/bin' }, stdio: 'ignore', timeout: 500
    }))
    assert.deepEqual(fs.readFileSync(observed, 'utf8').trim().split('\n'), ['CLEAN', 'CLEAN'])
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})
