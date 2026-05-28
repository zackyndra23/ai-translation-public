import { Card } from '@/components/ui/card'
import { formatCost, formatLatency, formatTokens } from '@/lib/format'
import type { TranslateResponse } from '@/services/types'

interface Props {
  payload: TranslateResponse | null
  elapsed: number
}

export function PipelineSummary({ payload, elapsed }: Props) {
  if (!payload) {
    return (
      <Card className="border-border-default bg-bg-card px-4 py-3 text-xs text-fg-muted">
        Elapsed: <span className="font-mono">{(elapsed / 1000).toFixed(3)}s</span>
      </Card>
    )
  }

  const totalInputTokens = payload.agentic_activities.reduce(
    (s, a) => s + (a.input_tokens ?? 0),
    0,
  )
  const totalOutputTokens = payload.agentic_activities.reduce(
    (s, a) => s + (a.output_tokens ?? 0),
    0,
  )
  const totalCost = payload.agentic_activities.reduce(
    (s, a) => s + (a.cost_usd ? parseFloat(a.cost_usd) : 0),
    0,
  )
  // Parallel savings = sum(individual latencies) - max(latency)
  const latencies = payload.agentic_activities
    .map((a) => a.latency_ms ?? 0)
    .filter((n) => n > 0)
  const parallelSavings =
    latencies.reduce((s, n) => s + n, 0) - Math.max(...latencies, 0)

  return (
    <Card className="border-border-default bg-bg-card">
      <div className="grid grid-cols-4 divide-x divide-border-default px-2 py-3 text-xs">
        <Stat
          label="Total latency"
          value={formatLatency(payload.latency_ms)}
          sub={parallelSavings > 0 ? `parallel saved ${Math.round(parallelSavings)}ms` : undefined}
          mono
        />
        <Stat
          label="Total tokens"
          value={`${formatTokens(totalInputTokens)} in · ${formatTokens(totalOutputTokens)} out`}
        />
        <Stat label="Total cost" value={formatCost(totalCost)} mono />
        <Stat label="Agents executed" value={String(payload.agentic_activities.length)} />
      </div>
    </Card>
  )
}

function Stat({
  label,
  value,
  sub,
  mono,
}: {
  label: string
  value: string
  sub?: string
  mono?: boolean
}) {
  return (
    <div className="px-4">
      <div className="text-fg-muted uppercase tracking-wider text-[10px]">{label}</div>
      <div className={mono ? 'mt-0.5 font-mono text-fg-primary' : 'mt-0.5 text-fg-primary'}>
        {value}
      </div>
      {sub && <div className="mt-0.5 text-[10px] text-fg-muted">{sub}</div>}
    </div>
  )
}
