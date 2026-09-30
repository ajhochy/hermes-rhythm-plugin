import assert from 'node:assert/strict'

import { test } from 'vitest'

import { isBlockedOpenDesignAnalyticsRequest } from './analytics-block'

// PostHog ingest hosts — apps/daemon/src/analytics.ts DEFAULT_HOST and the
// EU/asset variants documented in tools/pack/src/config.ts.
test('blocks the US PostHog ingest host', () => {
  assert.equal(isBlockedOpenDesignAnalyticsRequest('https://us.i.posthog.com/e/'), true)
})

test('blocks the EU PostHog ingest host', () => {
  assert.equal(isBlockedOpenDesignAnalyticsRequest('https://eu.i.posthog.com/capture/'), true)
})

test('blocks the PostHog asset host', () => {
  assert.equal(isBlockedOpenDesignAnalyticsRequest('https://us-assets.i.posthog.com/static/array.js'), true)
})

test('blocks the legacy PostHog ingest host', () => {
  assert.equal(isBlockedOpenDesignAnalyticsRequest('https://app.posthog.com/decide/'), true)
})

// Open Design's own telemetry relay — apps/daemon/src/integrations/telemetry-relay.ts
// OPEN_DESIGN_TELEMETRY_RELAY_URLS + legacy self-host origin, path /api/langfuse.
test('blocks the production Open Design telemetry relay', () => {
  assert.equal(isBlockedOpenDesignAnalyticsRequest('https://telemetry.open-design.ai/api/langfuse'), true)
})

test('blocks the test Open Design telemetry relay', () => {
  assert.equal(isBlockedOpenDesignAnalyticsRequest('https://telemetry-test.open-design.ai/api/langfuse'), true)
})

test('blocks the legacy self-hosted Open Design telemetry relay', () => {
  assert.equal(isBlockedOpenDesignAnalyticsRequest('https://telemetry-selfhost.open-design.ai/api/langfuse'), true)
})

test('blocks a sub-path under the telemetry relay route', () => {
  assert.equal(isBlockedOpenDesignAnalyticsRequest('https://telemetry.open-design.ai/api/langfuse/ingest'), true)
})

// Lookalike / suffix tricks must not be treated as the real blocked host.
test('does not block a domain that merely has the PostHog host as a suffix', () => {
  assert.equal(isBlockedOpenDesignAnalyticsRequest('https://evilus.i.posthog.com/e/'), false)
})

test('does not block a domain that appends attacker text after the PostHog host', () => {
  assert.equal(isBlockedOpenDesignAnalyticsRequest('https://us.i.posthog.com.evil.com/e/'), false)
})

test('does not block a domain that has the telemetry relay host as a suffix', () => {
  assert.equal(isBlockedOpenDesignAnalyticsRequest('https://not-telemetry.open-design.ai/api/langfuse'), false)
})

test('does not block the telemetry relay host on an unrelated path', () => {
  assert.equal(isBlockedOpenDesignAnalyticsRequest('https://telemetry.open-design.ai/health'), false)
})

// Normal Open Design product traffic must stay reachable.
test('does not block the release/update bucket', () => {
  assert.equal(isBlockedOpenDesignAnalyticsRequest('https://s3.nexu.space/releases/open-design-0.20.0.dmg'), false)
})

test('does not block the project storage bucket', () => {
  assert.equal(
    isBlockedOpenDesignAnalyticsRequest('https://od-bucket.s3.us-east-1.amazonaws.com/projects/abc.png'),
    false
  )
})

test('does not block the marketing/apex Open Design domain', () => {
  assert.equal(isBlockedOpenDesignAnalyticsRequest('https://open-design.ai/'), false)
})

test('does not block the Open Design dev domain', () => {
  assert.equal(isBlockedOpenDesignAnalyticsRequest('https://opendesign.dev/'), false)
})

test('does not block the loopback runtime origin itself', () => {
  assert.equal(isBlockedOpenDesignAnalyticsRequest('http://127.0.0.1:5173/api/app-config'), false)
})

test('treats a malformed URL as not analytics rather than throwing', () => {
  assert.equal(isBlockedOpenDesignAnalyticsRequest('not-a-url'), false)
})

test('treats an empty string as not analytics rather than throwing', () => {
  assert.equal(isBlockedOpenDesignAnalyticsRequest(''), false)
})
