import { motion } from 'framer-motion'
import type { AgentStates } from '@/hooks/useTranslationFlow'

interface Props {
  agents: AgentStates | null
}

// Simple SVG diagram:
//                ┌─→ [lang_detect_input] ─┐
//   [Input] ─────┤                         ├──→ [Output]
//                └─→ [translate] ──────────┘
export function PipelineDiagram({ agents }: Props) {
  const detect = agents?.lang_detect_input
  const translate = agents?.translate

  return (
    <div className="relative h-48 w-full">
      <svg viewBox="0 0 800 200" className="h-full w-full">
        {/* Connection paths */}
        <Path d="M 120 100 Q 200 100 240 50 L 320 50" running={detect?.status === 'running'} />
        <Path d="M 120 100 Q 200 100 240 150 L 320 150" running={translate?.status === 'running'} />
        <Path d="M 560 50 L 640 50 Q 680 100 680 100" running={detect?.status === 'completed' && translate?.status === 'running'} />
        <Path d="M 560 150 L 640 150 Q 680 100 680 100" running={translate?.status === 'completed'} />

        {/* Nodes */}
        <Node x={60} y={100} label="Input" tone="muted" />
        <Node
          x={440}
          y={50}
          label="lang_detect_input"
          tone={statusTone(detect?.status)}
          width={240}
        />
        <Node
          x={440}
          y={150}
          label="translate"
          tone={statusTone(translate?.status)}
          width={240}
        />
        <Node x={740} y={100} label="Output" tone={translate?.status === 'completed' ? 'done' : 'muted'} />
      </svg>

      {!agents && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="rounded-full border border-border-default bg-bg-card px-4 py-1.5 text-xs text-fg-muted">
            Run a translation to see the pipeline in action
          </div>
        </div>
      )}
    </div>
  )
}

type Tone = 'muted' | 'running' | 'done' | 'failed'

function statusTone(s?: string): Tone {
  if (s === 'running') return 'running'
  if (s === 'completed') return 'done'
  if (s === 'failed') return 'failed'
  return 'muted'
}

function Node({
  x,
  y,
  label,
  tone,
  width = 120,
}: {
  x: number
  y: number
  label: string
  tone: Tone
  width?: number
}) {
  const colors: Record<Tone, { stroke: string; fill: string; text: string }> = {
    muted: { stroke: 'rgba(255,255,255,0.12)', fill: '#16161d', text: '#71717a' },
    running: { stroke: '#b91c1c', fill: '#16161d', text: '#b91c1c' },
    done: { stroke: '#10b981', fill: '#16161d', text: '#10b981' },
    failed: { stroke: '#ef4444', fill: '#16161d', text: '#ef4444' },
  }
  const c = colors[tone]
  const w = width
  const h = 36

  return (
    <g>
      {tone === 'running' && (
        <motion.rect
          x={x - w / 2}
          y={y - h / 2}
          width={w}
          height={h}
          rx={8}
          fill="none"
          stroke={c.stroke}
          strokeWidth={2}
          animate={{ opacity: [0.4, 1, 0.4] }}
          transition={{ duration: 1.2, repeat: Infinity }}
        />
      )}
      <rect
        x={x - w / 2}
        y={y - h / 2}
        width={w}
        height={h}
        rx={8}
        fill={c.fill}
        stroke={c.stroke}
        strokeWidth={1.5}
      />
      <text
        x={x}
        y={y}
        textAnchor="middle"
        dominantBaseline="middle"
        fill={c.text}
        fontSize={12}
        fontFamily="JetBrains Mono, monospace"
      >
        {label}
      </text>
    </g>
  )
}

function Path({ d, running }: { d: string; running: boolean }) {
  return (
    <g>
      <path d={d} fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth={1.5} />
      {running && (
        <motion.circle
          r={3}
          fill="#b91c1c"
          initial={{ offsetDistance: '0%' }}
          animate={{ offsetDistance: '100%' }}
          transition={{ duration: 1.2, repeat: Infinity, ease: 'linear' }}
          style={{ offsetPath: `path('${d}')` } as React.CSSProperties}
        />
      )}
    </g>
  )
}
