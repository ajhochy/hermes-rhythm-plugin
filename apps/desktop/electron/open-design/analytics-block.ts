/**
 * Blocks Open Design's own outbound analytics/telemetry traffic for the
 * embedded guest, cross-checked against the pinned Open Design 0.20.0 source
 * (open-design-v0.20.0, commit fa3cb4cdf3d1703e984a5655bd9654f8d44c493b):
 *
 * - PostHog product-analytics ingest: apps/daemon/src/analytics.ts and
 *   apps/landing-page/app/_lib/posthog-analytics.ts default to
 *   `https://us.i.posthog.com`; tools/pack/src/config.ts documents the EU
 *   ingest host `eu.i.posthog.com` and the `-assets.i.posthog.com` asset
 *   host derived from it. `app.posthog.com` is PostHog's legacy ingest host.
 *   (The `posthogCliHost` / `us.posthog.com` management host is a build-time
 *   sourcemap-upload concern, not app runtime traffic, and is not blocked.)
 * - Open Design's own telemetry relay:
 *   apps/daemon/src/integrations/telemetry-relay.ts pins
 *   `telemetry.open-design.ai` (prod) and `telemetry-test.open-design.ai`
 *   (test) at path `/api/langfuse`, plus the legacy
 *   `telemetry-selfhost.open-design.ai` origin it normalizes from.
 *
 * Matching is by exact hostname equality (never `includes`/`endsWith`) so a
 * lookalike host that merely contains or is suffixed by a blocked name (e.g.
 * `us.i.posthog.com.evil.com`, `evilus.i.posthog.com`) is not treated as the
 * real thing. Normal Open Design API/cloud/image/update hosts (release/asset
 * buckets, the marketing domain, etc.) are deliberately not in this list.
 */
const BLOCKED_POSTHOG_INGEST_HOSTS = new Set([
  'us.i.posthog.com',
  'eu.i.posthog.com',
  'us-assets.i.posthog.com',
  'eu-assets.i.posthog.com',
  'app.posthog.com'
])

const BLOCKED_TELEMETRY_RELAY_HOSTS = new Set([
  'telemetry.open-design.ai',
  'telemetry-test.open-design.ai',
  'telemetry-selfhost.open-design.ai'
])

const BLOCKED_TELEMETRY_RELAY_PATH_PREFIX = '/api/langfuse'

export function isBlockedOpenDesignAnalyticsRequest(url: string): boolean {
  let parsed: URL

  try {
    parsed = new URL(url)
  } catch {
    return false
  }

  const hostname = parsed.hostname.toLowerCase()

  if (BLOCKED_POSTHOG_INGEST_HOSTS.has(hostname)) {
    return true
  }

  if (
    BLOCKED_TELEMETRY_RELAY_HOSTS.has(hostname) &&
    parsed.pathname.toLowerCase().startsWith(BLOCKED_TELEMETRY_RELAY_PATH_PREFIX)
  ) {
    return true
  }

  return false
}
