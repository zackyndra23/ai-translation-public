import { computeCostUsd } from './pricing'
import { detectLanguage } from './languageDetector'
import { fallbackTranslation, lookupTranslation } from '@/mocks/translations'
import type {
  AgenticActivity,
  ModelId,
  TranslateApi,
  TranslateRequest,
  TranslateResponse,
} from './types'

interface InternalApi extends TranslateApi {
  _resetCache(): void
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

const randInt = (min: number, max: number) =>
  Math.floor(Math.random() * (max - min + 1)) + min

const uuid = (): string => {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

const cache = new Map<string, TranslateResponse>()

function cacheKey(req: TranslateRequest): string {
  return `${req.source_lang ?? 'auto'}:${req.target_lang}:${req.text.trim().toLowerCase()}:${req.model_id ?? 'default'}`
}

function estimateTokens(text: string): number {
  // Rough ~3.7 chars per token estimate
  return Math.max(1, Math.round(text.length / 3.7))
}

function pickLatencyMs(model: ModelId, agentName: string): number {
  if (agentName === 'lang_detect_input') return randInt(120, 280)
  // translate latency scales with model
  switch (model) {
    case 'claude-haiku-4-5':
      return randInt(500, 900)
    case 'claude-sonnet-4-6':
      return randInt(800, 1500)
    case 'claude-opus-4-7':
      return randInt(1400, 2200)
    case 'gpt-4o-mini':
      return randInt(600, 1100)
  }
}

export const mockApi: InternalApi = {
  _resetCache() {
    cache.clear()
  },

  async translate(req, { onAgentEvent }) {
    const key = cacheKey(req)

    // Cache hit short-circuit
    const hit = cache.get(key)
    if (hit) {
      return { ...hit, cached: true, latency_ms: 3, trace_id: uuid() }
    }

    const startedAt = Date.now()
    const translateModel: ModelId = req.model_id ?? 'claude-sonnet-4-6'
    const detectModel: ModelId = 'claude-haiku-4-5'

    // Pick agent latencies upfront so we can schedule completion order
    const detectLatency = pickLatencyMs(detectModel, 'lang_detect_input')
    const translateLatency = pickLatencyMs(translateModel, 'translate')

    // Fire both agent_started events within ~50ms (parallel feel)
    onAgentEvent({ type: 'agent_started', agent_name: 'lang_detect_input' })
    await sleep(randInt(20, 60))
    onAgentEvent({ type: 'agent_started', agent_name: 'translate' })

    // Schedule completions
    const detectActivity = makeDetectActivity(
      req,
      detectModel,
      detectLatency,
      startedAt,
    )
    const translateActivity = makeTranslateActivity(
      req,
      translateModel,
      translateLatency,
      startedAt,
    )

    // Wait for detect to finish (it's faster)
    const remainingDetect = detectLatency - (Date.now() - startedAt)
    if (remainingDetect > 0) await sleep(remainingDetect)
    onAgentEvent({
      type: 'agent_completed',
      agent_name: 'lang_detect_input',
      activity: detectActivity,
    })

    // Wait for translate to finish
    const remainingTranslate = translateLatency - (Date.now() - startedAt)
    if (remainingTranslate > 0) await sleep(remainingTranslate)
    onAgentEvent({
      type: 'agent_completed',
      agent_name: 'translate',
      activity: translateActivity,
    })

    const response: TranslateResponse = {
      translated_text: translateActivity.result as string,
      source_lang: req.source_lang ?? 'en',
      target_lang: req.target_lang,
      cached: false,
      model_id: translateModel,
      input_tokens: translateActivity.input_tokens ?? 0,
      output_tokens: translateActivity.output_tokens ?? 0,
      cost_usd: translateActivity.cost_usd ?? '0',
      latency_ms: translateLatency,
      trace_id: uuid(),
      log_id: uuid(),
      prompt_applied: [
        'prompt-translate-default',
        'prompt-lang-detect-input',
      ],
      agentic_activities: [detectActivity, translateActivity],
      glossary_compliance: { score: 1.0, violations: [] },
    }

    cache.set(key, response)
    return response
  },
}

function makeDetectActivity(
  req: TranslateRequest,
  model: ModelId,
  latencyMs: number,
  startedAt: number,
): AgenticActivity {
  const input_tokens = estimateTokens(req.text)
  const output_tokens = randInt(4, 12)
  const detected = detectLanguage(req.text)
  const completedAt = startedAt + latencyMs

  return {
    agent_name: 'lang_detect_input',
    agent_type: 'lang_detection',
    status: 'completed',
    model,
    started_at: new Date(startedAt).toISOString(),
    completed_at: new Date(completedAt).toISOString(),
    input_tokens,
    output_tokens,
    cost_usd: computeCostUsd(model, input_tokens, output_tokens).toFixed(6),
    latency_ms: latencyMs,
    text_input: req.text,
    result: {
      detected_language: detected?.lang ?? req.source_lang ?? 'en',
      confidence: detected?.confidence ?? 0.5,
      alternatives: detected?.alternatives ?? [],
    },
  }
}

function makeTranslateActivity(
  req: TranslateRequest,
  model: ModelId,
  latencyMs: number,
  startedAt: number,
): AgenticActivity {
  const source = req.source_lang ?? 'en'
  const translated =
    lookupTranslation(source, req.target_lang, req.text) ??
    fallbackTranslation(req.target_lang, req.text)

  const input_tokens = estimateTokens(req.text) + 30 // + system prompt
  const output_tokens = estimateTokens(translated)
  const completedAt = startedAt + latencyMs

  return {
    agent_name: 'translate',
    agent_type: 'translation',
    status: 'completed',
    model,
    started_at: new Date(startedAt).toISOString(),
    completed_at: new Date(completedAt).toISOString(),
    input_tokens,
    output_tokens,
    cost_usd: computeCostUsd(model, input_tokens, output_tokens).toFixed(6),
    latency_ms: latencyMs,
    text_input: `Translate from ${source} to ${req.target_lang}:\n${req.text}`,
    result: translated,
  }
}
