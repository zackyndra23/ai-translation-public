import type { AgenticActivity, LangCode, ModelId, TranslateResponse } from './types'

// Backend response shape mirror. Lives here because the only consumer is the
// adapter; co-located reduces "where does this type live?" friction.
// This is NOT the same as `types.ts::TranslateResponse` — they diverged after
// sub-proyek B/C/I/K backend evolution. Per ADR-059, adapter is the swap point:
// future backend changes update this file (not types.ts) so frontend components
// stay untouched.

export interface BackendAgenticActivity {
  name: string
  agent_type: string
  // Backend status is Literal["success", "failed", "skipped"] per
  // src/pipeline/agents/base.py — 'skipped' covers cache-hit short-circuits
  // and graceful-degraded agents (e.g. haiku rate-limited).
  status: 'success' | 'failed' | 'skipped'
  model_id: string
  started_at: string
  completed_at: string | null
  input_tokens: number | null
  output_tokens: number | null
  cost_usd: string | null
  latency_ms: number | null
  prompt_applied: string | null
  result: Record<string, unknown> | null
  // Per-agent error info — backend emits flat error_code + error_detail
  // (NOT nested object). Synthesize the nested shape in adaptActivity for
  // frontend type compatibility.
  error_code?: string | null
  error_detail?: string | null
}

export interface BackendTranslateResponse {
  translation: string
  source_lang: string
  target_lang: string
  cached: boolean
  provider: string
  model: string
  latency_ms: number
  cost_usd: string
  glossary_compliance: number
  metadata: Record<string, unknown>
  log_id: string | null
  prompt_applied: string | null
  agentic_activities: BackendAgenticActivity[]
  detected_source_lang: string | null
  detected_output_lang: string | null
  source_lang_mismatch: boolean | null
  output_lang_mismatch: boolean | null
}

const KNOWN_MODELS: ReadonlySet<ModelId> = new Set<ModelId>([
  'claude-haiku-4-5',
  'claude-sonnet-4-6',
  'claude-opus-4-7',
  'gpt-4o-mini',
])

const KNOWN_LANGS: ReadonlySet<LangCode> = new Set<LangCode>([
  'en',
  'id',
  'es',
  'fr',
  'de',
  'ja',
  'zh',
  'ar',
  'pt',
  'ru',
])

const KNOWN_AGENTS: ReadonlySet<AgenticActivity['agent_name']> = new Set([
  'lang_detect_input',
  'lang_detect_output',
  'translate',
])

// Defensive casts: backend may return values outside the frontend's
// closed-set unions (new model IDs, regional lang codes). Falling back to
// safe defaults keeps the UI from crashing on unknown values — better to
// show "sonnet" + "en" than blow up the AgentPipeline / LanguageBar render.
function castModel(raw: string): ModelId {
  return KNOWN_MODELS.has(raw as ModelId) ? (raw as ModelId) : 'claude-sonnet-4-6'
}

function castLang(raw: string): LangCode {
  return KNOWN_LANGS.has(raw as LangCode) ? (raw as LangCode) : 'en'
}

// Fallback to 'translate' — the canonical primary agent — if backend ships an
// unrecognized agent (e.g. a future 'reviewer' / 'qa_check'). Without this
// guard, a raw cast lets unknown values slip into the union; downstream switch
// statements (AgentPipeline) would silently miss the case and render a broken
// card. 'translate' is the safest default because it's the one agent the UI
// always renders.
function castAgent(raw: string): AgenticActivity['agent_name'] {
  return KNOWN_AGENTS.has(raw as AgenticActivity['agent_name'])
    ? (raw as AgenticActivity['agent_name'])
    : 'translate'
}

export function adaptActivity(backend: BackendAgenticActivity): AgenticActivity {
  // Map backend status to frontend's narrower set. 'skipped' is treated as
  // 'completed' visually (not 'failed') so AgentPipeline doesn't show red
  // for an agent that was deliberately not invoked (e.g. lang_detect_output
  // skipped on cache hit, or haiku rate-limited graceful-degraded).
  const frontendStatus: AgenticActivity['status'] =
    backend.status === 'success'
      ? 'completed'
      : backend.status === 'skipped'
        ? 'completed'
        : 'failed'

  // Synthesize nested {code, detail} from backend's flat error_code +
  // error_detail. error_detail can legitimately be null even when error_code
  // is set (agent failed but produced no human-readable string).
  const errorInfo =
    backend.error_code && backend.error_detail
      ? { code: backend.error_code, detail: backend.error_detail }
      : backend.error_code
        ? { code: backend.error_code, detail: '' }
        : undefined

  return {
    agent_name: castAgent(backend.name),
    agent_type: backend.agent_type,
    status: frontendStatus,
    model: castModel(backend.model_id),
    started_at: backend.started_at,
    completed_at: backend.completed_at,
    input_tokens: backend.input_tokens,
    output_tokens: backend.output_tokens,
    cost_usd: backend.cost_usd,
    latency_ms: backend.latency_ms,
    text_input: backend.prompt_applied ?? '',
    result: backend.result ?? {},
    error: errorInfo,
  }
}

export function adaptResponse(backend: BackendTranslateResponse): TranslateResponse {
  // Backend only exposes a violation COUNT in metadata.glossary_violations,
  // not the actual text. Returning the count as fake placeholder strings
  // ("violation_1", "violation_2") would mislead operators reading the
  // PayloadViewer JSON — they'd think those are real violation labels.
  // Empty array is honest; the score field (0..1) conveys the magnitude.
  const violations: string[] = []
  const traceId =
    typeof backend.metadata?.trace_id === 'string' ? (backend.metadata.trace_id as string) : ''

  return {
    translated_text: backend.translation,
    source_lang: castLang(backend.source_lang),
    target_lang: castLang(backend.target_lang),
    cached: backend.cached,
    model_id: castModel(backend.model),
    input_tokens:
      typeof backend.metadata?.tokens_input === 'number'
        ? (backend.metadata.tokens_input as number)
        : 0,
    output_tokens:
      typeof backend.metadata?.tokens_output === 'number'
        ? (backend.metadata.tokens_output as number)
        : 0,
    cost_usd: backend.cost_usd,
    latency_ms: backend.latency_ms,
    trace_id: traceId,
    log_id: backend.log_id,
    prompt_applied: backend.prompt_applied ? [backend.prompt_applied] : [],
    agentic_activities: backend.agentic_activities.map(adaptActivity),
    glossary_compliance: { score: backend.glossary_compliance, violations },
  }
}
