import { describe, it, expect, beforeEach } from 'vitest'
import { mockApi } from './mockApi'
import type { AgentEvent, TranslateRequest } from './types'

const baseReq: TranslateRequest = {
  text: 'Halo apa kabar hari ini',
  source_lang: 'id',
  target_lang: 'en',
  tenant_id: 'tnt_a3f9k2',
  profile_id: 'profile-default',
  model_id: 'claude-sonnet-4-6',
}

describe('mockApi.translate', () => {
  // Reset cache before each test so tests are isolated from each other.
  // Without this, test 1 caches the result and tests 2-3 get cache hits,
  // causing wrong cached/event assertions.
  beforeEach(() => {
    mockApi._resetCache()
  })
  it('fires agent_started events for both agents in parallel (within 100ms)', async () => {
    const events: AgentEvent[] = []
    const promise = mockApi.translate(baseReq, {
      onAgentEvent: (e) => events.push(e),
    })
    // wait for parallel-start window to elapse
    await new Promise((r) => setTimeout(r, 120))
    const starts = events.filter((e) => e.type === 'agent_started')
    expect(starts.length).toBe(2)
    expect(starts.map((e) => e.agent_name).sort()).toEqual([
      'lang_detect_input',
      'translate',
    ])
    await promise
  })

  it('lang_detect_input completes before translate', async () => {
    const order: string[] = []
    const promise = mockApi.translate(baseReq, {
      onAgentEvent: (e) => {
        if (e.type === 'agent_completed') order.push(e.agent_name)
      },
    })
    await promise
    expect(order).toEqual(['lang_detect_input', 'translate'])
  })

  it('returns a TranslateResponse with all required fields', async () => {
    const response = await mockApi.translate(baseReq, {
      onAgentEvent: () => {},
    })
    expect(response.translated_text).toBeTruthy()
    expect(response.source_lang).toBe('id')
    expect(response.target_lang).toBe('en')
    expect(response.cached).toBe(false)
    expect(response.model_id).toBe('claude-sonnet-4-6')
    expect(response.input_tokens).toBeGreaterThan(0)
    expect(response.output_tokens).toBeGreaterThan(0)
    expect(typeof response.cost_usd).toBe('string')
    expect(response.trace_id).toBeTruthy()
    expect(Array.isArray(response.agentic_activities)).toBe(true)
    expect(response.agentic_activities.length).toBe(2)
    expect(response.prompt_applied.length).toBeGreaterThan(0)
  })

  it('returns cached:true with low latency on repeat request', async () => {
    mockApi._resetCache()
    await mockApi.translate(baseReq, { onAgentEvent: () => {} })
    const r2 = await mockApi.translate(baseReq, { onAgentEvent: () => {} })
    expect(r2.cached).toBe(true)
    expect(r2.latency_ms).toBeLessThan(20)
  })
})
