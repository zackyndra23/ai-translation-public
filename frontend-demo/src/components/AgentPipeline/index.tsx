import { Card } from '@/components/ui/card'
import { Activity } from 'lucide-react'
import { PipelineDiagram } from './PipelineDiagram'
import { AgentCard } from './AgentCard'
import { PipelineSummary } from './PipelineSummary'
import type { AgentStates } from '@/hooks/useTranslationFlow'
import type { TranslateResponse } from '@/services/types'
import { formatElapsedSeconds } from '@/lib/format'

interface Props {
  agents: AgentStates | null
  elapsed: number
  payload: TranslateResponse | null
}

export function AgentPipeline({ agents, elapsed, payload }: Props) {
  return (
    <Card className="bg-bg-card border-border-default">
      <div className="flex items-center justify-between border-b border-border-default px-6 py-4">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-accent-red" />
          <h2 className="text-base font-medium text-fg-primary">
            Agent Pipeline
          </h2>
          <span className="text-xs text-fg-muted">
            (parallel orchestration)
          </span>
        </div>
        {agents && (
          <div className="font-mono text-xs text-fg-muted">
            {formatElapsedSeconds(elapsed)}
          </div>
        )}
      </div>

      <div className="p-6">
        <PipelineDiagram agents={agents} />

        {agents && (
          <div className="mt-6 grid grid-cols-2 gap-4">
            <AgentCard name="lang_detect_input" state={agents.lang_detect_input} />
            <AgentCard name="translate" state={agents.translate} />
          </div>
        )}

        <div className="mt-6">
          <PipelineSummary payload={payload} elapsed={elapsed} />
        </div>
      </div>
    </Card>
  )
}
