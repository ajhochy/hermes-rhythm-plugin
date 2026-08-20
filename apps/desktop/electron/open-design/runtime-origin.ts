/**
 * The Open Design runtime is only ever addressed at an exact loopback origin
 * that Hermes itself resolved (see the packaging/supervisor contract in
 * apps/desktop/docs/open-design-integration.contract.json). This validator is
 * intentionally a literal-string match rather than a `new URL()` host check:
 * the URL parser normalizes lookalikes such as `127.1`, `0x7f000001`, or a
 * fully-expanded `::0:1` down to the real loopback address, which would let
 * those lookalikes slip through a `hostname === '127.0.0.1'` comparison.
 * Matching the exact literal closes that gap.
 */
const LOOPBACK_ORIGIN_PATTERN = /^http:\/\/(127\.0\.0\.1|\[::1\]):(\d{1,5})\/?$/

export function isValidOpenDesignRuntimeOrigin(value: string): boolean {
  if (typeof value !== 'string' || value.length === 0) {
    return false
  }

  const match = LOOPBACK_ORIGIN_PATTERN.exec(value)

  if (!match) {
    return false
  }

  const portText = match[2]
  const port = Number(portText)

  if (String(port) !== portText) {
    return false
  } // rejects leading-zero forms like "05173"

  return port >= 1 && port <= 65535
}
