// All API contract types. Mirrors the expected sub-proyek I /translate response
// shape so swapping mockApi → realApi later is a single-file replacement
// (spec §3.2, ADR-048).

export type LangCode =
  | 'en' | 'id' | 'es' | 'fr' | 'de'
  | 'ja' | 'zh' | 'ar' | 'pt' | 'ru'

export type ModelId =
  | 'claude-haiku-4-5'
  | 'claude-sonnet-4-6'
  | 'claude-opus-4-7'
  | 'gpt-4o-mini'

export type AgentName = 'lang_detect_input' | 'lang_detect_output' | 'translate'

export type AgentStatus = 'pending' | 'running' | 'completed' | 'failed'

export type ModelTier = 'Standard' | 'Premium' | 'Enterprise'

export interface Tenant {
  id: string
  name: string
  source_lang: LangCode
  target_lang: LangCode
  model_tier: ModelTier
  language_detection: boolean
  output_streaming: boolean
  log_payloads: boolean
  created_at: string // ISO 8601
  status: 'active' | 'inactive'
}

export interface TranslateRequest {
  text: string
  source_lang: LangCode | null
  target_lang: LangCode
  tenant_id: string
  profile_id: string
  model_id?: ModelId
}

export interface AgenticActivity {
  agent_name: AgentName
  agent_type: string
  status: AgentStatus
  model: ModelId
  started_at: string
  completed_at: string | null
  input_tokens: number | null
  output_tokens: number | null
  cost_usd: string | null
  latency_ms: number | null
  text_input: string
  result: unknown
  error?: { code: string; detail: string }
}

export interface TranslateResponse {
  translated_text: string
  source_lang: LangCode
  target_lang: LangCode
  cached: boolean
  model_id: ModelId
  input_tokens: number
  output_tokens: number
  cost_usd: string
  latency_ms: number
  trace_id: string
  log_id: string | null
  prompt_applied: string[]
  agentic_activities: AgenticActivity[]
  glossary_compliance?: { score: number; violations: string[] }
}

export interface AgentEvent {
  type: 'agent_started' | 'agent_completed' | 'agent_failed'
  agent_name: AgentName
  activity?: AgenticActivity
}

export interface TranslateApi {
  translate(
    req: TranslateRequest,
    opts: { onAgentEvent: (e: AgentEvent) => void },
  ): Promise<TranslateResponse>
}

export const LANGUAGE_LABELS: Record<LangCode, { name: string; flag: string }> = {
  en: { name: 'English', flag: '🇬🇧' },
  id: { name: 'Indonesian', flag: '🇮🇩' },
  es: { name: 'Spanish', flag: '🇪🇸' },
  fr: { name: 'French', flag: '🇫🇷' },
  de: { name: 'German', flag: '🇩🇪' },
  ja: { name: 'Japanese', flag: '🇯🇵' },
  zh: { name: 'Mandarin', flag: '🇨🇳' },
  ar: { name: 'Arabic', flag: '🇸🇦' },
  pt: { name: 'Portuguese', flag: '🇵🇹' },
  ru: { name: 'Russian', flag: '🇷🇺' },
}

export const MODEL_LABELS: Record<ModelId, string> = {
  'claude-haiku-4-5': 'Claude Haiku 4.5',
  'claude-sonnet-4-6': 'Claude Sonnet 4.6',
  'claude-opus-4-7': 'Claude Opus 4.7',
  'gpt-4o-mini': 'GPT-4o mini',
}
