// Login remembers where the visitor was headed. That value comes from router
// state we set ourselves, but treat it as untrusted anyway: only same-site
// paths are allowed, so it can never become an open redirect.
export function safeRedirect(value: unknown): string | null {
  if (typeof value !== 'string') return null
  // Must be an absolute path on this site, not "//evil.com" or "/\evil.com"
  if (
    !value.startsWith('/') ||
    value.startsWith('//') ||
    value.includes('\\')
  ) {
    return null
  }
  return value
}
