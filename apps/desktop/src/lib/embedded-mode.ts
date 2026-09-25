/** Whether this renderer is running inside Rhythm's owned WebContentsView. */
export function isEmbeddedDesktop(search = typeof window === 'undefined' ? '' : window.location?.search ?? ''): boolean {
  try {
    const params = new URLSearchParams(search)

    // Helper surfaces are independent renderers and must retain their existing
    // standalone behavior even if a host accidentally forwards embedded=1.
    return params.get('embedded') === '1' && !params.has('win')
  } catch {
    return false
  }
}
