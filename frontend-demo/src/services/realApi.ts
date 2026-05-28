import { ApiClient } from './apiClient'
import { adaptResponse, type BackendTranslateResponse } from './responseAdapter'
import type { AgentEvent, TranslateApi, TranslateRequest, TranslateResponse } from './types'

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

// Factory so the caller can inject baseUrl + apiKey from useApiSettings.
// Returning a TranslateApi keeps the swap with mockApi clean (apiSelector.ts).
//
// Synthetic streaming rationale (ADR-060): backend /translate is one-shot
// request-response. AgentPipeline in the UI invests in progressive parallel
// agent animation — we preserve that experience by replaying agent_completed
// events spaced by activity.latency_ms. Cache hit (cached=true) short-circuits
// the replay since no agent actually ran. Future SSE upgrade replaces this
// loop with real streamed events without touching the consumer.
export function makeRealApi(opts: { baseUrl: string; apiKey: string }): TranslateApi {
  const client = new ApiClient(opts)

  return {
    async translate(
      req: TranslateRequest,
      { onAgentEvent }: { onAgentEvent: (e: AgentEvent) => void },
    ): Promise<TranslateResponse> {
      // Fire both agent_started immediately — preserves the "parallel agents"
      // visual narrative even though the backend call is one-shot.
      onAgentEvent({ type: 'agent_started', agent_name: 'lang_detect_input' })
      onAgentEvent({ type: 'agent_started', agent_name: 'translate' })

      // Map frontend req → backend payload shape. Backend reads source_lang /
      // target_lang at the top level; model_id (if present) goes into options.
      const body: Record<string, unknown> = {
        text: req.text,
        source_lang: req.source_lang,
        target_lang: req.target_lang,
        tenant_id: req.tenant_id,
        profile_id: req.profile_id,
      }
      if (req.model_id) {
        body.options = { model_id: req.model_id }
      }

      let backendResp: BackendTranslateResponse
      try {
        backendResp = await client.post<BackendTranslateResponse>('/translate', body)
      } catch (e) {
        // Fire failure events so AgentPipeline shows red state on both agents.
        // Then re-throw so TranslationPlayground can map error_code → banner.
        onAgentEvent({ type: 'agent_failed', agent_name: 'lang_detect_input' })
        onAgentEvent({ type: 'agent_failed', agent_name: 'translate' })
        throw e
      }

      const adapted = adaptResponse(backendResp)

      // Sort once — used by both cache-hit (immediate firing) and cache-miss
      // (replay) branches. Backend doesn't guarantee chronological ordering;
      // without this, a cached response with activities in [translate,
      // lang_detect_input] order would animate out-of-order in the UI.
      const sortedActivities = [...adapted.agentic_activities].sort((a, b) => {
        const aTime = a.completed_at ? new Date(a.completed_at).getTime() : 0
        const bTime = b.completed_at ? new Date(b.completed_at).getTime() : 0
        return aTime - bTime
      })

      if (backendResp.cached) {
        // Cache hit: no real agent ran. Fire completions immediately so the
        // UI snaps to the result without artificial replay delay.
        for (const activity of sortedActivities) {
          onAgentEvent({
            type: 'agent_completed',
            agent_name: activity.agent_name,
            activity,
          })
        }
        return adapted
      }

      // Cache miss: replay agent_completed events spaced by activity.latency_ms.
      // Ordering by completed_at (chronological). If two activities finish at
      // the same time we keep the input order from agentic_activities.
      const replayStart = Date.now()
      for (const activity of sortedActivities) {
        const targetDelay = activity.latency_ms ?? 0
        const elapsed = Date.now() - replayStart
        if (targetDelay > elapsed) {
          await sleep(targetDelay - elapsed)
        }
        onAgentEvent({
          type: activity.status === 'completed' ? 'agent_completed' : 'agent_failed',
          agent_name: activity.agent_name,
          activity,
        })
      }

      return adapted
    },
  }
}
