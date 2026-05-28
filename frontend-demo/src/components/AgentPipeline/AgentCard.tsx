import { useState } from 'react'
import { motion } from 'framer-motion'
import { ChevronDown } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { formatCost, formatLatency, formatTokens } from '@/lib/format'
import { MODEL_LABELS } from '@/services/types'
import { cn } from '@/lib/cn'
import type { AgentState } from '@/hooks/useTranslationFlow'

interface Props {
  name: string
  state: AgentState | undefined
}

export function AgentCard({ name, state }: Props) {
  const [expanded, setExpanded] = useState(false)
  const status = state?.status ?? 'idle'

  const statusColor = {
    idle: 'text-fg-muted',
    pending: 'text-fg-muted',
    running: 'text-accent-red',
    completed: 'text-accent-emerald',
    failed: 'text-accent-crimson',
  }[status]

  return (
    <Card
      className={cn(
        'border-border-default bg-bg-card transition-shadow',
        status === 'running' &&
          'shadow-[0_0_0_1px_#b91c1c_inset,0_0_20px_#b91c1c44]',
      )}
    >
      <div className="flex items-center justify-between border-b border-border-default px-4 py-3">
        <div className="font-mono text-sm text-fg-primary">{name}</div>
        <div className="flex items-center gap-2">
          {state?.model && (
            <Badge variant="outline" className="border-border-default font-mono text-[10px] text-fg-muted">
              {state.model}
            </Badge>
          )}
          <span className={cn('text-xs font-medium uppercase tracking-wider', statusColor)}>
            {status}
          </span>
        </div>
      </div>

      <div className="px-4 py-3">
        <div className="mb-3 h-1 overflow-hidden rounded-full bg-bg-base">
          <motion.div
            className={cn(
              'h-full',
              status === 'completed' ? 'bg-accent-emerald' : 'bg-accent-red',
            )}
            animate={
              status === 'running'
                ? { width: ['10%', '90%', '10%'] }
                : status === 'completed'
                  ? { width: '100%' }
                  : { width: '0%' }
            }
            transition={
              status === 'running'
                ? { duration: 1.5, repeat: Infinity, ease: 'easeInOut' }
                : { duration: 0.3 }
            }
          />
        </div>

        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
          <Metric label="input tokens" value={formatTokens(state?.tokens?.input)} />
          <Metric label="output tokens" value={formatTokens(state?.tokens?.output)} />
          <Metric label="latency" value={formatLatency(state?.latency_ms)} mono />
          <Metric
            label="cost (USD)"
            value={state?.cost_usd != null ? formatCost(state.cost_usd) : '—'}
            mono
          />
          <Metric
            label="model"
            value={state?.model ? MODEL_LABELS[state.model] : '—'}
          />
          <Metric label="status" value={status} />
        </div>

        <button
          onClick={() => setExpanded((x) => !x)}
          className="mt-3 flex items-center gap-1 text-xs text-fg-muted hover:text-fg-body"
        >
          <ChevronDown
            className={cn('h-3 w-3 transition-transform', expanded && 'rotate-180')}
          />
          View I/O
        </button>

        {expanded && (
          <div className="mt-3 space-y-2">
            <CodeBlock label="text_input" content={state?.text_input ?? '(none)'} />
            <CodeBlock
              label="llm_output"
              content={
                state?.llm_output != null
                  ? JSON.stringify(state.llm_output, null, 2)
                  : '(none)'
              }
            />
          </div>
        )}
      </div>
    </Card>
  )
}

function Metric({
  label,
  value,
  mono,
}: {
  label: string
  value: string
  mono?: boolean
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-fg-muted">{label}</span>
      <span className={cn('text-fg-body', mono && 'font-mono')}>{value}</span>
    </div>
  )
}

function CodeBlock({ label, content }: { label: string; content: string }) {
  return (
    <div>
      <div className="mb-1 text-[10px] uppercase tracking-wider text-fg-muted">
        {label}
      </div>
      <pre className="overflow-x-auto rounded-lg border border-border-default bg-bg-base p-2 font-mono text-[11px] text-fg-body">
        {content}
      </pre>
    </div>
  )
}
