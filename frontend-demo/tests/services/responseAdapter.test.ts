import { describe, expect, it } from 'vitest'
import {
  adaptActivity,
  adaptResponse,
  type BackendAgenticActivity,
  type BackendTranslateResponse,
} from '@/services/responseAdapter'

const backendActivity = (
  overrides: Partial<BackendAgenticActivity> = {},
): BackendAgenticActivity => ({
  name: 'translate',
  agent_type: 'translation',
  status: 'success',
  model_id: 'claude-sonnet-4-6',
  started_at: '2026-05-22T00:00:00Z',
  completed_at: '2026-05-22T00:00:01Z',
  input_tokens: 100,
  output_tokens: 20,
  cost_usd: '0.000837',
  latency_ms: 1000,
  prompt_applied: '<rendered prompt>',
  result: { translation: 'Hello' },
  ...overrides,
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
  latency_ms: 1234,
  cost_usd: '0.000837',
  glossary_compliance: 0.95,
  metadata: { trace_id: 'trace-xyz', tokens_input: 100, tokens_output: 20 },
  log_id: 'log-uuid-1',
  prompt_applied: '<rendered prompt>',
  agentic_activities: [backendActivity()],
  detected_source_lang: 'id',
  detected_output_lang: 'en',
  source_lang_mismatch: false,
  output_lang_mismatch: false,
  ...overrides,
})

describe('adaptActivity', () => {
  it('maps backend success activity to frontend completed', () => {
    const adapted = adaptActivity(backendActivity())
    expect(adapted.agent_name).toBe('translate')
    expect(adapted.status).toBe('completed')
    expect(adapted.model).toBe('claude-sonnet-4-6')
    expect(adapted.text_input).toBe('<rendered prompt>')
  })

  it('maps failed status correctly', () => {
    const adapted = adaptActivity(backendActivity({ status: 'failed' }))
    expect(adapted.status).toBe('failed')
  })

  it('falls back to sonnet when model_id is unknown', () => {
    const adapted = adaptActivity(backendActivity({ model_id: 'some-unknown-model' }))
    expect(adapted.model).toBe('claude-sonnet-4-6')
  })

  it('uses empty string for text_input when prompt_applied is null', () => {
    const adapted = adaptActivity(backendActivity({ prompt_applied: null }))
    expect(adapted.text_input).toBe('')
  })

  it('falls back unknown agent name to translate', () => {
    const adapted = adaptActivity(backendActivity({ name: 'future_agent_xyz' }))
    expect(adapted.agent_name).toBe('translate')
  })

  it('maps skipped status to completed (visual)', () => {
    const adapted = adaptActivity(backendActivity({ status: 'skipped' }))
    expect(adapted.status).toBe('completed')
  })

  it('synthesizes nested error from flat error_code + error_detail', () => {
    const adapted = adaptActivity(
      backendActivity({
        status: 'failed',
        error_code: 'provider_timeout',
        error_detail: 'Anthropic took >60s',
      }),
    )
    expect(adapted.error).toEqual({ code: 'provider_timeout', detail: 'Anthropic took >60s' })
  })

  it('error field is undefined when no error_code present', () => {
    const adapted = adaptActivity(backendActivity({ status: 'success' }))
    expect(adapted.error).toBeUndefined()
  })
})

describe('adaptResponse', () => {
  it('maps full happy backend response to frontend shape', () => {
    const adapted = adaptResponse(backendResp())
    expect(adapted.translated_text).toBe('Hello')
    expect(adapted.source_lang).toBe('id')
    expect(adapted.target_lang).toBe('en')
    expect(adapted.model_id).toBe('claude-sonnet-4-6')
    expect(adapted.trace_id).toBe('trace-xyz')
    expect(adapted.input_tokens).toBe(100)
    expect(adapted.output_tokens).toBe(20)
    expect(adapted.log_id).toBe('log-uuid-1')
    expect(adapted.prompt_applied).toEqual(['<rendered prompt>'])
    expect(adapted.agentic_activities).toHaveLength(1)
    expect(adapted.glossary_compliance).toEqual({ score: 0.95, violations: [] })
  })

  it('wraps null prompt_applied as empty array', () => {
    const adapted = adaptResponse(backendResp({ prompt_applied: null }))
    expect(adapted.prompt_applied).toEqual([])
  })

  it('falls back unknown lang code to en', () => {
    const adapted = adaptResponse(backendResp({ source_lang: 'xx', target_lang: 'yy' }))
    expect(adapted.source_lang).toBe('en')
    expect(adapted.target_lang).toBe('en')
  })

  it('emits empty violations array — backend only provides count', () => {
    // Even when metadata.glossary_violations is a count, the adapter intentionally
    // returns an empty array (not fake "violation_N" strings) so operators reading
    // PayloadViewer aren't misled into thinking they're real violation labels.
    // The count's magnitude is preserved via the score field.
    const adapted = adaptResponse(
      backendResp({
        metadata: { trace_id: 't', tokens_input: 0, tokens_output: 0, glossary_violations: 3 },
      }),
    )
    expect(adapted.glossary_compliance?.violations).toHaveLength(0)
  })

  it('uses 0 tokens when metadata missing token counts', () => {
    const adapted = adaptResponse(backendResp({ metadata: { trace_id: 't' } }))
    expect(adapted.input_tokens).toBe(0)
    expect(adapted.output_tokens).toBe(0)
  })

  it('returns empty trace_id when metadata has none', () => {
    const adapted = adaptResponse(backendResp({ metadata: {} }))
    expect(adapted.trace_id).toBe('')
  })
})
