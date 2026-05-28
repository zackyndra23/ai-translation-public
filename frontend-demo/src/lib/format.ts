export function formatCost(usd: number | string): string {
  const n = typeof usd === 'string' ? parseFloat(usd) : usd
  return `$${n.toFixed(6)}`
}

export function formatLatency(ms: number | null | undefined): string {
  if (ms == null) return '—'
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

export function formatTokens(n: number | null | undefined): string {
  if (n == null) return '—'
  return n.toLocaleString()
}

export function formatElapsedSeconds(ms: number): string {
  return `${(ms / 1000).toFixed(3)}s`
}

export function formatRelativeTime(iso: string): string {
  const date = new Date(iso)
  const diff = Date.now() - date.getTime()
  const days = Math.floor(diff / 86400000)
  if (days > 30) return date.toLocaleDateString()
  if (days > 0) return `${days}d ago`
  const hours = Math.floor(diff / 3600000)
  if (hours > 0) return `${hours}h ago`
  const mins = Math.floor(diff / 60000)
  if (mins > 0) return `${mins}m ago`
  return 'just now'
}
