import assert from 'node:assert/strict'

import { test } from 'vitest'

import { isValidOpenDesignRuntimeOrigin } from './runtime-origin'

test('accepts exact IPv4 loopback origin with explicit port', () => {
  assert.equal(isValidOpenDesignRuntimeOrigin('http://127.0.0.1:5173'), true)
})

test('accepts exact IPv4 loopback origin with trailing root slash', () => {
  assert.equal(isValidOpenDesignRuntimeOrigin('http://127.0.0.1:5173/'), true)
})

test('accepts exact IPv6 loopback origin with explicit port', () => {
  assert.equal(isValidOpenDesignRuntimeOrigin('http://[::1]:5173'), true)
})

test('accepts exact IPv6 loopback origin with trailing root slash', () => {
  assert.equal(isValidOpenDesignRuntimeOrigin('http://[::1]:5173/'), true)
})

test('rejects https even against the exact loopback host', () => {
  assert.equal(isValidOpenDesignRuntimeOrigin('https://127.0.0.1:5173'), false)
})

test('rejects localhost', () => {
  assert.equal(isValidOpenDesignRuntimeOrigin('http://localhost:5173'), false)
})

test('rejects missing port', () => {
  assert.equal(isValidOpenDesignRuntimeOrigin('http://127.0.0.1'), false)
})

test('rejects non-root path', () => {
  assert.equal(isValidOpenDesignRuntimeOrigin('http://127.0.0.1:5173/api'), false)
})

test('rejects query string', () => {
  assert.equal(isValidOpenDesignRuntimeOrigin('http://127.0.0.1:5173?x=1'), false)
})

test('rejects fragment', () => {
  assert.equal(isValidOpenDesignRuntimeOrigin('http://127.0.0.1:5173#f'), false)
})

test('rejects embedded credentials', () => {
  assert.equal(isValidOpenDesignRuntimeOrigin('http://user:pass@127.0.0.1:5173'), false)
})

test('rejects short-form IPv4 lookalike 127.1', () => {
  assert.equal(isValidOpenDesignRuntimeOrigin('http://127.1:5173'), false)
})

test('rejects hex IPv4 lookalike', () => {
  assert.equal(isValidOpenDesignRuntimeOrigin('http://0x7f000001:5173'), false)
})

test('rejects DNS suffix lookalike of the loopback literal', () => {
  assert.equal(isValidOpenDesignRuntimeOrigin('http://127.0.0.1.evil.com:5173'), false)
})

test('rejects full-form IPv6 loopback spelled out', () => {
  assert.equal(isValidOpenDesignRuntimeOrigin('http://[0:0:0:0:0:0:0:1]:5173'), false)
})

test('rejects blob scheme', () => {
  assert.equal(isValidOpenDesignRuntimeOrigin('blob:http://127.0.0.1:5173/xyz'), false)
})

test('rejects file scheme', () => {
  assert.equal(isValidOpenDesignRuntimeOrigin('file:///etc/passwd'), false)
})

test('rejects data scheme', () => {
  assert.equal(isValidOpenDesignRuntimeOrigin('data:text/html,hi'), false)
})

test('rejects javascript scheme', () => {
  assert.equal(isValidOpenDesignRuntimeOrigin('javascript:alert(1)'), false)
})

test('rejects a port with a leading zero', () => {
  assert.equal(isValidOpenDesignRuntimeOrigin('http://127.0.0.1:05173'), false)
})

test('rejects a port outside the valid range', () => {
  assert.equal(isValidOpenDesignRuntimeOrigin('http://127.0.0.1:70000'), false)
})

test('rejects a non-string input', () => {
  assert.equal(isValidOpenDesignRuntimeOrigin(undefined as unknown as string), false)
})

test('rejects an empty string', () => {
  assert.equal(isValidOpenDesignRuntimeOrigin(''), false)
})
