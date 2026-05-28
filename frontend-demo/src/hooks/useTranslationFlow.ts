import { useCallback, useRef, useState } from 'react'
import { getTranslateApi } from '@/services/apiSelector'
import type {
  AgentName,
  AgentStatus,
  ModelId,
  TranslateApi,
  TranslateRequest,
  TranslateResponse,
} from '@/services/types'
import { useElapsedTimer } from './useElapsedTimer'

export interface AgentState {
  status: AgentStatus | 'idle'
  model?: ModelId
  startedAt?: number
  completedAt?: number
  tokens?: { input: number; output: number }
  cost_usd?: number
  latency_ms?: number
  text_input?: string
  llm_output?: unknown
}

export interface AgentStates {
  lang_detect_input: AgentState
  translate: AgentState
}

export type FlowState =
  | { status: 'idle' }
  | { status: 'running'; startedAt: number; agents: AgentStates }
  | { status: 'done'; payload: TranslateResponse; agents: AgentStates }
  | { status: 'error'; message: string; error: unknown }

const IDLE_AGENTS: AgentStates = {
  lang_detect_input: { status: 'idle' },
  translate: { status: 'idle' },
}

export interface TranslationFlow {
  state: FlowState
  elapsed: number
  start: (req: TranslateRequest) => void
}

// The hook accepts an injected `api` for testability (existing tests pass a
// rejecting stub). When omitted, we resolve via `getTranslateApi()` at start
// time (not at hook-construction) so a Save in SettingsModal takes effect
// without remounting the consumer — ADR-062 demands "no page reload" UX.
export function useTranslationFlow(api?: TranslateApi): TranslationFlow {
  const [state, setState] = useState<FlowState>({ status: 'idle' })
  const reqIdRef = useRef(0)

  const elapsed = useElapsedTimer(state.status === 'running')

  const start = useCallback(
    (req: TranslateRequest) => {
      const myReqId = ++reqIdRef.current
      const startedAt = Date.now()

      setState({
        status: 'running',
        startedAt,
        agents: structuredClone(IDLE_AGENTS),
      })

      const updateAgent = (name: AgentName, patch: Partial<AgentState>) => {
        setState((prev) => {
          if (prev.status !== 'running') return prev
          if (myReqId !== reqIdRef.current) return prev
          if (name === 'lang_detect_output') return prev
          return {
            ...prev,
            agents: {
              ...prev.agents,
              [name]: { ...prev.agents[name], ...patch },
            },
          }
        })
      }

      const activeApi = api ?? getTranslateApi()

      activeApi
        .translate(req, {
          onAgentEvent: (e) => {
            if (e.agent_name === 'lang_detect_output') return
            if (e.type === 'agent_started') {
              updateAgent(e.agent_name, { status: 'running', startedAt: Date.now() })
            } else if (e.type === 'agent_completed' && e.activity) {
              updateAgent(e.agent_name, {
                status: 'completed',
                model: e.activity.model,
                completedAt: Date.now(),
                tokens: {
                  input: e.activity.input_tokens ?? 0,
                  output: e.activity.output_tokens ?? 0,
                },
                cost_usd: e.activity.cost_usd
                  ? parseFloat(e.activity.cost_usd)
                  : 0,
                latency_ms: e.activity.latency_ms ?? 0,
                text_input: e.activity.text_input,
                llm_output: e.activity.result,
              })
            } else if (e.type === 'agent_failed' && e.activity) {
              updateAgent(e.agent_name, { status: 'failed' })
            }
          },
        })
        .then((payload) => {
          if (myReqId !== reqIdRef.current) return
          setState((prev) => {
            if (prev.status !== 'running') return prev
            return { status: 'done', payload, agents: prev.agents }
          })
        })
        .catch((err) => {
          if (myReqId !== reqIdRef.current) return
          // Keep the typed error in state alongside the message string so the
          // playground banner mapper (bannerCopyForError) can branch on
          // ApiError predicates / NetworkError instance without losing fidelity.
          setState({
            status: 'error',
            message: String(err?.message ?? err),
            error: err,
          })
        })
    },
    [api],
  )

  return { state, elapsed, start }
}
