import { describe, expect, it, vi, beforeEach } from 'vitest'
import { makeRealApi } from '@/services/realApi'
import type {
  BackendAgenticActivity,
  BackendTranslateResponse,
} from '@/services/responseAdapter'
import type { AgentEvent } from '@/services/types'

const backendActivity = (
  name: string,
  latency = 100,
  status: 'success' | 'failed' = 'success',
): BackendAgenticActivity => ({
  name,
  agent_type: name.includes('detect') ? 'language_detection' : 'translation',
  status,
  model_id: 'claude-sonnet-4-6',
  started_at: '2026-05-22T00:00:00Z',
  completed_at: new Date(Date.parse('2026-05-22T00:00:00Z') + latency).toISOString(),
  input_tokens: 10,
  output_tokens: 5,
  cost_usd: '0.0001',
  latency_ms: latency,
  prompt_applied: 'prompt',
  result: { translation: 'Hello' },
})

const backendResp = (
  overrides: Partial<BackendTranslateResponse> = {},
): BackendTranslateResponse => ({
  translation: 'Hello',
  source_lang: 'id',
  target_lang: 'en',
  cached: false,
  provider: 'claude',
  model: 'claude-sonnet-4-6',
  latency_ms: 200,
  cost_usd: '0.0001',
  glossary_compliance: 1.0,
  metadata: { trace_id: 't1' },
  log_id: 'log-1',
  prompt_applied: 'prompt',
  agentic_activities: [
    backendActivity('lang_detect_input', 50),
    backendActivity('translate', 150),
  ],
  detected_source_lang: 'id',
  detected_output_lang: 'en',
  source_lang_mismatch: false,
  output_lang_mismatch: false,
  ...overrides,
})

const mockFetch = (body: BackendTranslateResponse) =>
  vi.spyOn(globalThis, 'fetch').mockImplementation(
    async () =>
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
  )

beforeEach(() => {
  vi.restoreAllMocks()
  vi.useFakeTimers()
})

describe('realApi.translate', () => {
  it('fires agent_started for both agents before HTTP call resolves', async () => {
    mockFetch(backendResp())
    const events: AgentEvent[] = []
    const api = makeRealApi({ baseUrl: '/api', apiKey: 'aitkey_xyz' })

    const promise = api.translate(
      { text: 'Halo', source_lang: 'id', target_lang: 'en', tenant_id: 't', profile_id: 'p' },
      { onAgentEvent: (e) => events.push(e) },
    )
    // Advance microtask queue so synchronous agent_started events have been pushed.
    await vi.advanceTimersByTimeAsync(0)

    expect(events.slice(0, 2)).toEqual([
      { type: 'agent_started', agent_name: 'lang_detect_input' },
      { type: 'agent_started', agent_name: 'translate' },
    ])

    // Drain remaining timers to let the replay loop finish.
    await vi.advanceTimersByTimeAsync(500)
    await promise
  })

  it('replays agent_completed events spaced by latency_ms', async () => {
    mockFetch(backendResp())
    const events: AgentEvent[] = []
    const api = makeRealApi({ baseUrl: '/api', apiKey: 'aitkey_xyz' })
    const promise = api.translate(
      { text: 'Halo', source_lang: 'id', target_lang: 'en', tenant_id: 't', profile_id: 'p' },
      { onAgentEvent: (e) => events.push(e) },
    )

    // Drain the entire replay window
    await vi.advanceTimersByTimeAsync(500)
    await promise

    const completed = events.filter((e) => e.type === 'agent_completed')
    expect(completed).toHaveLength(2)
    expect(completed.map((e) => e.agent_name)).toEqual(['lang_detect_input', 'translate'])
  })

  it('cache-hit skips replay delay (events fire immediately)', async () => {
    mockFetch(backendResp({ cached: true }))
    const events: AgentEvent[] = []
    const api = makeRealApi({ baseUrl: '/api', apiKey: 'aitkey_xyz' })

    const promise = api.translate(
      { text: 'Halo', source_lang: 'id', target_lang: 'en', tenant_id: 't', profile_id: 'p' },
      { onAgentEvent: (e) => events.push(e) },
    )

    // Without advancing time, the fetch + immediate replay should both settle.
    await vi.advanceTimersByTimeAsync(0)
    const result = await promise

    expect(result.cached).toBe(true)
    // No setTimeout delay should have been needed — all completions present without time advance beyond microtask flush.
    expect(events.filter((e) => e.type === 'agent_completed')).toHaveLength(2)
  })

  it('fires agent_failed for both and throws on backend error', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      async () =>
        new Response(
          JSON.stringify({ error_code: 'rate_limited', detail: 'slow down', trace_id: 't1' }),
          { status: 429, headers: { 'Content-Type': 'application/json' } },
        ),
    )
    const events: AgentEvent[] = []
    const api = makeRealApi({ baseUrl: '/api', apiKey: 'aitkey_xyz' })

    await expect(
      api.translate(
        { text: 'Halo', source_lang: 'id', target_lang: 'en', tenant_id: 't', profile_id: 'p' },
        { onAgentEvent: (e) => events.push(e) },
      ),
    ).rejects.toMatchObject({ status: 429, errorCode: 'rate_limited' })

    const failed = events.filter((e) => e.type === 'agent_failed')
    expect(failed.map((e) => e.agent_name)).toEqual(['lang_detect_input', 'translate'])
  })
})
