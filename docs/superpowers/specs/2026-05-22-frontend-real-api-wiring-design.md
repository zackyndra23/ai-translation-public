# Design — Frontend-Demo ↔ Real Backend API Wiring (Sub-proyek L)

> **Tanggal**: 2026-05-22
> **Status**: Approved (brainstorm), pending implementation plan
> **Author**: zaky + Claude (brainstorm session)
> **Sub-proyek**: L — minimum-viable wiring of `frontend-demo/` React SPA ke real `/translate` backend, replacing `mockApi.ts` dengan `realApi.ts` adapter
> **Depends on**: sub-proyek I (tenant junction + auth middleware), K (denormalized schema + Jinja context + allowed_language enforcement)
> **Unblocks**: stakeholder demos against real LLM responses; future sub-projects for cascade UI / JWT login / streaming agentic events

---

## 1. Konteks & motivasi

Sub-proyek J (commit `257ec4e`) menghasilkan `frontend-demo/` SPA dengan mock-only API layer (`src/services/mockApi.ts`). ADR-048 (sub-proyek J spec) menjanjikan "cheap mock-to-real swap (single file replacement at integration phase — `realApi.ts` implements same `TranslateApi` interface)". Saat itu mock dibangun sebelum backend stabil; sekarang backend sudah end-to-end verified (sub-proyek K smoke run), waktunya merealisasikan swap.

Beberapa fakta yang shift sejak ADR-048:

- **Contract drift**: `types.ts` `TranslateResponse` punya field `translated_text`/`model_id`/`prompt_applied: string[]`/`glossary_compliance: { score, violations }`. Real backend `TranslateResponse` (di `src/api/schemas.py` + `src/pipeline/schemas.py`) return `translation`/`model`/`prompt_applied: string | None`/`glossary_compliance: float`. Adapter pattern dibutuhkan.
- **No streaming**: backend `POST /translate` adalah one-shot request-response. Mock simulates streaming agentic events with `setTimeout`. Real adapter harus synthesize streaming dari response timing untuk preserve AgentPipeline animation UX.
- **Tenant model divergence**: per ADR-049, frontend Tab 1 tenant management forever mock — tapi sekarang user butuh map mock tenant ke real `{api_key, profile_id, tenant_id}` triple supaya Tab 2 bisa kerja. Setting modal route picked (per §4) instead of mock-tenant embedding.
- **No `.env.local`, no Vite proxy** di frontend-demo. CORS allowlist backend cuma `localhost:8501` (Streamlit defunct) + `localhost:8001` (SDK landing page). Dev proxy + CORS update both needed.
- **No auth UX**: TopBar punya tenant dropdown tapi gak ada API key concept.

Sub-proyek L addresses semua itu dalam minimum-viable scope.

---

## 2. Goals & non-goals

**Goals:**
- `realApi.ts` implements `TranslateApi` interface, hits real `POST /translate` with `X-Tenant-API-Key` auth.
- Adapter layer (`responseAdapter.ts`) maps backend response shape → frontend type without forcing types.ts canonical rewrite.
- Synthetic streaming: real backend's one-shot response replayed as agentic events to preserve AgentPipeline UX.
- Settings modal: API key + profile_id + tenant_id + base URL inputs persisted to localStorage.
- Vite dev proxy `/api/*` → `http://localhost:8000` (no CORS hack).
- Backend CORS allowlist extended to include `localhost:5173`.
- `VITE_API_MODE` env var toggle (mock | real), default `mock` for out-of-box demo.
- Error mapping: backend `error_code` → user-friendly inline banner di output box.
- Sub-proyek K language_not_allowed enforcement surfaced visibly.
- 15-20 new tests + 22 pre-existing pass.
- Manual smoke checklist verified.

**Non-goals:**
- Cascade UI replacing Tab 1 (per ADR-049, deferred).
- JWT login + refresh flow UI.
- SSE/WebSocket real streaming (current adapter pattern future-proof; this sub-proyek synthesizes streaming).
- Production-grade error reporting (Sentry, etc).
- Profile/tenant discovery via `/tenant-profiles` endpoint (user pastes IDs manually).
- Multi-account support (one set of credentials in localStorage).
- Backend updates beyond CORS allowlist extension.
- Updating `types.ts` to match backend canonically (adapter handles drift).

---

## 3. Keputusan utama

### 3.1 Adapter pattern, jangan ubah `types.ts`

Frontend `types.ts` `TranslateResponse` mirrors backend's *expected* shape per ADR-048. Backend evolved differently. Two paths:

- **Path A (chosen):** keep `types.ts` as frontend-canonical; adapter layer `responseAdapter.ts` maps backend → frontend. Components stay unchanged (no cascading edits).
- **Path B:** update `types.ts` to mirror backend reality. All components/tests/hooks that reference old field names must update.

Path A is minimum-disruption. Path B is "more correct" but blows up scope (LanguageMismatchBanner, PayloadViewer, AgentPipeline all depend on existing field names). Adapter layer is well-bounded — single file, well-tested, isolated.

**Trade-off:** future sub-projects that swap backend will need to update adapter not types. Acceptable — adapter is the swap point.

### 3.2 Synthetic streaming from response timing

Backend `/translate` is request-response. Mock simulates streaming via `setTimeout` chains for AgentPipeline animation. Real adapter must preserve that UX:

- Fire `agent_started` events for both `lang_detect_input` + `translate` immediately on request start (parallel agent narrative)
- POST request goes out, response arrives with all `agentic_activities`
- Sort activities by `completed_at`, replay `agent_completed` events spaced by `latency_ms` from request start
- Cache hit (`response.cached === true`) fires all `agent_completed` immediately (skip replay — no real agent ran)

Per-event latency derived from `activity.latency_ms` in response. Total perceived latency = real API call duration + max activity latency. Slight increase vs raw response display, but preserves "parallel completion" visual narrative.

**Alternative rejected:** fire all events immediately upon response. Snappier but loses progressive parallel completion visualization. AgentPipeline component already invests in animation; preserving it matters for stakeholder demo polish (sub-proyek J's purpose).

### 3.3 Settings modal route, not embedded in Tab 1 tenant management

Tab 1 mock tenant management stays mock-only per ADR-049. User configures backend credentials separately via a Settings dialog accessible from TopBar (gear icon next to tenant Select).

**Trade-off:** mock tenant + real backend credentials are two unlinked concepts. UX-wise user sees "active mock tenant X" in TopBar AND "real backend credentials Y" in Settings — could be confusing. Mitigated by clear modal copy ("Backend Connection") and gear icon framing.

**Alternative rejected:** embed API key + profile_id fields into each mock tenant in Tab 1. Tighter coupling but requires Tab 1 schema changes, contradicts ADR-049 spirit ("Tab 1 mock-only forever"), and creates illusion that mock tenant is a real entity.

### 3.4 localStorage persistence, single credentials set

`localStorage` key `aitegrity_api_settings` holds `{baseUrl, apiKey, profileId, tenantId}`. One set of credentials per browser session. No multi-account.

**Trade-off:** API key in localStorage is XSS-exposed. For development/demo context, acceptable per ADR-026 PII trade-off precedent. Production rollout (operator portal sub-project) will need proper session-based auth.

### 3.5 Vite proxy `/api/*` → `localhost:8000`

Frontend code calls `/api/translate` (relative). Vite dev server proxies to backend. Trade-offs:

- **Pro:** no CORS in dev, code identical for dev/prod, base URL configurable via setting.
- **Con:** still need backend CORS allowlist extension for production deployment (when frontend served from different origin).

Backend `src/api/main.py` CORS allowlist gets `localhost:5173` added for direct-hit fallback (e.g. user overrides base URL to `http://localhost:8000` in Settings).

### 3.6 Env var toggle, default mock

`VITE_API_MODE` env var read at build/dev start:
- `mock` (default): `apiSelector.ts` exports `mockApi`
- `real`: exports `realApi`

`.env.local` not committed. `.env.local.example` template committed. Operator runs `cp .env.local.example .env.local; edit VITE_API_MODE=real` to switch.

**Trade-off:** can't toggle at runtime without Vite reload. Acceptable for demo workflow (operator picks mode once per session). Future UI toggle deferred.

### 3.7 Error mapping: 5 explicit codes + generic fallback

Backend errors return `{error_code, detail, trace_id}` per ADR-019. Frontend maps:

| `error_code` | UI display | Severity color |
|---|---|---|
| `language_not_allowed` | "Target language [X] not allowed. Allowed: [...]" | accent-amber (matches LanguageMismatchBanner) |
| `authentication_failed` / `tenant_not_found` | "Authentication failed. Check API key in Settings." | accent-crimson |
| `rate_limited` | "Rate limited. Retry in N seconds." (countdown auto-retry) | accent-amber |
| `upstream_transient` | "Translation service temporarily unavailable. Retry." | accent-crimson |
| (other / network) | "Translation request failed: [detail]. Trace ID: [...]" | accent-crimson |

Banner positioned ABOVE output box. Copy-on-click trace_id for debugging support. Banner auto-dismisses on next successful translate.

---

## 4. File structure

### 4.1 New files

```
frontend-demo/
├── .env.local.example                    # template with VITE_API_MODE + VITE_API_BASE_URL
├── src/
│   ├── services/
│   │   ├── apiClient.ts                  # fetch wrapper + auth header + error mapping
│   │   ├── apiSelector.ts                # picks mock | real per VITE_API_MODE
│   │   ├── errors.ts                     # ApiError class
│   │   ├── realApi.ts                    # implements TranslateApi against real backend
│   │   └── responseAdapter.ts            # backend response → frontend type
│   ├── hooks/
│   │   └── useApiSettings.ts             # localStorage read/write hook
│   └── components/
│       └── SettingsModal.tsx             # API key + profile_id + tenant_id + URL form
└── tests/
    ├── services/
    │   ├── apiClient.test.ts
    │   ├── apiSelector.test.ts
    │   ├── realApi.test.ts
    │   └── responseAdapter.test.ts
    ├── hooks/
    │   └── useApiSettings.test.ts
    └── components/
        └── SettingsModal.test.tsx
```

### 4.2 Modified files

```
frontend-demo/
├── vite.config.ts                        # add /api/* proxy
├── src/
│   ├── App.tsx                           # replace mockApi import → translateApi from apiSelector
│   ├── components/
│   │   ├── TopBar.tsx                    # add Settings gear icon button
│   │   └── TranslationPlayground.tsx     # error banner display, ApiError handling
│   └── services/
│       └── types.ts                      # add ApiSettings type only (no canonical rewrite)
```

### 4.3 Backend modifications

```
src/api/main.py                           # extend CORS allowlist: localhost:5173
```

---

## 5. Component interfaces

### 5.1 `errors.ts`

```typescript
export class ApiError extends Error {
  status: number
  errorCode: string  // backend error_code
  detail: string
  traceId?: string

  constructor(opts: { status: number; errorCode: string; detail: string; traceId?: string }) {
    super(`${opts.errorCode}: ${opts.detail}`)
    this.status = opts.status
    this.errorCode = opts.errorCode
    this.detail = opts.detail
    this.traceId = opts.traceId
  }

  isLanguageNotAllowed(): boolean { return this.errorCode === 'language_not_allowed' }
  isAuth(): boolean { return this.errorCode === 'authentication_failed' || this.errorCode === 'tenant_not_found' }
  isRateLimited(): boolean { return this.errorCode === 'rate_limited' }
  isTransient(): boolean { return this.errorCode === 'upstream_transient' || this.status >= 500 }
}

export class NetworkError extends Error {
  cause: unknown
  constructor(cause: unknown) { super('Network error'); this.cause = cause }
}
```

### 5.2 `apiClient.ts`

```typescript
import { ApiError, NetworkError } from './errors'

export interface ApiClientOptions {
  baseUrl: string  // e.g. '/api' or 'http://localhost:8000'
  apiKey: string   // aitkey_...
}

export class ApiClient {
  constructor(private opts: ApiClientOptions) {}

  async post<TResp>(path: string, body: unknown): Promise<TResp> {
    let resp: Response
    try {
      resp = await fetch(`${this.opts.baseUrl}${path}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Tenant-API-Key': this.opts.apiKey,
        },
        body: JSON.stringify(body),
      })
    } catch (e) {
      throw new NetworkError(e)
    }

    if (!resp.ok) {
      // Try to parse ErrorResponse envelope; fallback to raw text.
      let errorCode = 'unknown'
      let detail = resp.statusText
      let traceId: string | undefined
      try {
        const errBody = await resp.json()
        errorCode = errBody.error_code ?? errorCode
        detail = errBody.detail ?? detail
        traceId = errBody.trace_id
      } catch { /* not JSON */ }
      throw new ApiError({ status: resp.status, errorCode, detail, traceId })
    }

    return (await resp.json()) as TResp
  }
}
```

### 5.3 `responseAdapter.ts`

```typescript
import type { AgenticActivity, ModelId, LangCode, TranslateResponse } from './types'

interface BackendAgenticActivity {
  name: string
  agent_type: string
  status: 'success' | 'failed'
  model_id: string
  started_at: string
  completed_at: string | null
  input_tokens: number | null
  output_tokens: number | null
  cost_usd: string | null
  latency_ms: number | null
  prompt_applied: string | null
  result: Record<string, unknown> | null
  error?: { code: string; detail: string }
}

interface BackendTranslateResponse {
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

const KNOWN_MODELS: ReadonlySet<ModelId> = new Set([
  'claude-haiku-4-5', 'claude-sonnet-4-6', 'claude-opus-4-7', 'gpt-4o-mini',
])

const KNOWN_LANGS: ReadonlySet<LangCode> = new Set([
  'en', 'id', 'es', 'fr', 'de', 'ja', 'zh', 'ar', 'pt', 'ru',
])

function castModel(raw: string): ModelId {
  return KNOWN_MODELS.has(raw as ModelId) ? (raw as ModelId) : 'claude-sonnet-4-6'
}

function castLang(raw: string): LangCode {
  return KNOWN_LANGS.has(raw as LangCode) ? (raw as LangCode) : 'en'
}

export function adaptActivity(backend: BackendAgenticActivity): AgenticActivity {
  return {
    agent_name: backend.name as AgenticActivity['agent_name'],
    agent_type: backend.agent_type,
    status: backend.status === 'success' ? 'completed' : 'failed',
    model: castModel(backend.model_id),
    started_at: backend.started_at,
    completed_at: backend.completed_at,
    input_tokens: backend.input_tokens,
    output_tokens: backend.output_tokens,
    cost_usd: backend.cost_usd,
    latency_ms: backend.latency_ms,
    text_input: backend.prompt_applied ?? '',
    result: backend.result ?? {},
    error: backend.error,
  }
}

export function adaptResponse(backend: BackendTranslateResponse): TranslateResponse {
  const violationsRaw = backend.metadata?.glossary_violations
  const violations = typeof violationsRaw === 'number'
    ? Array.from({ length: violationsRaw }, (_, i) => `violation_${i + 1}`)  // backend stores count only
    : []
  const traceId = (backend.metadata?.trace_id as string) ?? ''

  return {
    translated_text: backend.translation,
    source_lang: castLang(backend.source_lang),
    target_lang: castLang(backend.target_lang),
    cached: backend.cached,
    model_id: castModel(backend.model),
    input_tokens: (backend.metadata?.tokens_input as number) ?? 0,
    output_tokens: (backend.metadata?.tokens_output as number) ?? 0,
    cost_usd: backend.cost_usd,
    latency_ms: backend.latency_ms,
    trace_id: traceId,
    log_id: backend.log_id,
    prompt_applied: backend.prompt_applied ? [backend.prompt_applied] : [],
    agentic_activities: backend.agentic_activities.map(adaptActivity),
    glossary_compliance: { score: backend.glossary_compliance, violations },
  }
}
```

### 5.4 `realApi.ts`

```typescript
import { ApiClient } from './apiClient'
import { adaptActivity, adaptResponse, type BackendTranslateResponse } from './responseAdapter'
import type { TranslateApi, TranslateRequest, TranslateResponse, AgentEvent } from './types'

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

export function makeRealApi(opts: { baseUrl: string; apiKey: string }): TranslateApi {
  const client = new ApiClient(opts)
  return {
    async translate(
      req: TranslateRequest,
      { onAgentEvent }: { onAgentEvent: (e: AgentEvent) => void },
    ): Promise<TranslateResponse> {
      // Fire agent_started for both immediately (parallel feel).
      onAgentEvent({ type: 'agent_started', agent_name: 'lang_detect_input' })
      onAgentEvent({ type: 'agent_started', agent_name: 'translate' })

      // Build backend-shape payload.
      const body = {
        text: req.text,
        source_lang: req.source_lang,
        target_lang: req.target_lang,
        tenant_id: req.tenant_id,
        profile_id: req.profile_id,
        options: req.model_id ? { model_id: req.model_id } : undefined,
      }

      let backendResp: BackendTranslateResponse
      try {
        backendResp = await client.post<BackendTranslateResponse>('/translate', body)
      } catch (e) {
        // Fire agent_failed for both before propagating.
        onAgentEvent({ type: 'agent_failed', agent_name: 'lang_detect_input' })
        onAgentEvent({ type: 'agent_failed', agent_name: 'translate' })
        throw e
      }

      const adapted = adaptResponse(backendResp)

      if (backendResp.cached) {
        // Cache hit: fire completions immediately.
        for (const activity of adapted.agentic_activities) {
          onAgentEvent({
            type: 'agent_completed',
            agent_name: activity.agent_name,
            activity,
          })
        }
        return adapted
      }

      // Replay events spaced by latency_ms from request start.
      const sortedActivities = [...adapted.agentic_activities].sort((a, b) => {
        const aTime = a.completed_at ? new Date(a.completed_at).getTime() : 0
        const bTime = b.completed_at ? new Date(b.completed_at).getTime() : 0
        return aTime - bTime
      })

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
```

### 5.5 `apiSelector.ts`

```typescript
import { mockApi } from './mockApi'
import { makeRealApi } from './realApi'
import type { TranslateApi } from './types'

function readSettings(): { baseUrl: string; apiKey: string } | null {
  if (typeof window === 'undefined') return null
  const raw = window.localStorage.getItem('aitegrity_api_settings')
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    return { baseUrl: parsed.baseUrl ?? '/api', apiKey: parsed.apiKey ?? '' }
  } catch {
    return null
  }
}

export function getTranslateApi(): TranslateApi {
  const mode = import.meta.env.VITE_API_MODE
  if (mode !== 'real') return mockApi

  const settings = readSettings()
  if (!settings || !settings.apiKey) {
    // No credentials configured — fall back to mock and let SettingsModal prompt.
    return mockApi
  }
  return makeRealApi(settings)
}
```

App.tsx calls `getTranslateApi()` once per render (or via a hook that re-evaluates when settings change). For MVP, callsite re-evaluates on each translate request — settings rarely change mid-session.

### 5.6 `useApiSettings.ts`

```typescript
import { useEffect, useState } from 'react'

export interface ApiSettings {
  baseUrl: string
  apiKey: string
  profileId: string
  tenantId: string
}

const STORAGE_KEY = 'aitegrity_api_settings'
const DEFAULTS: ApiSettings = {
  baseUrl: '/api',
  apiKey: '',
  profileId: '',
  tenantId: '',
}

function readFromStorage(): ApiSettings {
  if (typeof window === 'undefined') return DEFAULTS
  const raw = window.localStorage.getItem(STORAGE_KEY)
  if (!raw) return DEFAULTS
  try {
    return { ...DEFAULTS, ...JSON.parse(raw) }
  } catch {
    return DEFAULTS
  }
}

export function useApiSettings() {
  const [settings, setSettings] = useState<ApiSettings>(readFromStorage)

  const save = (next: Partial<ApiSettings>) => {
    setSettings((prev) => {
      const merged = { ...prev, ...next }
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(merged))
      }
      return merged
    })
  }

  const isConfigured = settings.apiKey.startsWith('aitkey_')
    && settings.profileId.length > 0
    && settings.tenantId.length > 0

  return { settings, save, isConfigured }
}
```

### 5.7 `SettingsModal.tsx`

shadcn/ui `Dialog`. Form with 4 inputs (base URL, API key masked, profile ID, tenant ID). Save button writes to localStorage via `useApiSettings`. Clear button resets to defaults.

Validation client-side:
- baseUrl: non-empty, valid URL or relative path
- apiKey: starts with `aitkey_`
- profileId: matches `/^profile-[0-9a-f]{8}-[0-9a-f]{4}$/`
- tenantId: matches `/^tenant-[0-9a-f]{8}-[0-9a-f]{4}$/`

Helper text under profileId + tenantId:
> "Get this from your backend. PSQL: `SELECT profile_id, tenant_name FROM tenant_profile LIMIT 5;` and `SELECT tenant_id, tenant_name FROM tenant LIMIT 5;`"

API key field: password-input type with show/hide eye icon. Helper: "Output from `scripts/seed_tenant_data.py` first run (stdout `API_KEY=aitkey_...`)."

Modal trigger: gear icon `Settings` from `lucide-react` in TopBar, between current tenant Select dropdown dan owl mark. Red dot indicator on the icon when `!isConfigured` AND `VITE_API_MODE === 'real'`.

Auto-open on first launch if `VITE_API_MODE === 'real'` AND `!isConfigured`. Modal has copy explaining: "Configure backend connection to use real API. Or set `VITE_API_MODE=mock` in `.env.local` for in-memory demo."

### 5.8 `TranslationPlayground.tsx` updates

Add state:
```typescript
const [apiError, setApiError] = useState<ApiError | null>(null)
```

In `handleTranslate`:
```typescript
try {
  setApiError(null)
  await translationFlow.start(req)
} catch (e) {
  if (e instanceof ApiError) {
    setApiError(e)
  } else {
    setApiError(new ApiError({
      status: 0,
      errorCode: 'network_error',
      detail: e instanceof Error ? e.message : String(e),
    }))
  }
}
```

Render banner ABOVE OutputBox when `apiError !== null`. Banner copy + color per §3.7 table. Trace ID line (`text-xs text-muted-foreground`) with copy-on-click icon. Auto-dismiss when new translation succeeds.

---

## 6. Backend CORS update

`src/api/main.py`:

```python
ALLOWED_ORIGINS = [
    "http://localhost:8001",   # SDK landing page (Phase 7)
    "http://localhost:5173",   # frontend-demo Vite dev server (sub-proyek L)
]
```

`localhost:8501` (defunct Streamlit) removed at the same time to clean up. No other changes.

---

## 7. Tests

**~16 new tests:**

| File | Tests | What |
|---|---|---|
| `tests/services/apiClient.test.ts` | 4 | success JSON parse, error envelope mapping (400/401/429/500), network error wrapping, auth header injection |
| `tests/services/responseAdapter.test.ts` | 5 | full happy mapping, unknown model fallback, unknown lang fallback, null prompt_applied → empty array, glossary_compliance number→object wrap |
| `tests/services/realApi.test.ts` | 4 | event sequence on success, event sequence on cache hit (no replay delay), event sequence on backend error (agent_failed before throw), POST body shape |
| `tests/services/apiSelector.test.ts` | 2 | env=mock returns mockApi, env=real + valid settings returns realApi |
| `tests/hooks/useApiSettings.test.ts` | 1 | save persists + isConfigured boolean |
| `tests/components/SettingsModal.test.tsx` | 1 | form validates API key + saves to localStorage |

**Existing 22 tests still pass.** Total ~38.

---

## 8. Manual smoke checklist

After implementation:
1. Start backend: `uv run uvicorn src.api.main:app --port 8000`
2. `cp frontend-demo/.env.local.example frontend-demo/.env.local`; edit `VITE_API_MODE=real`
3. `cd frontend-demo && npm run dev` (or `pwsh scripts/run-demo.ps1`)
4. SettingsModal auto-opens on first visit (no credentials). Paste API key + profile_id + tenant_id from sub-proyek K seed stdout. Save.
5. Navigate to Translation Playground tab. Type "Halo, selamat pagi". Source=Indonesian, target=English. Click Translate.
6. AgentPipeline animates: both agents start → lang_detect completes → translate completes (sequenced by real backend timing).
7. OutputBox shows real translation ("Hello, good morning" or similar).
8. Cost shown (e.g. $0.0008). Latency shown (e.g. 2400ms).
9. PayloadViewer expandable, shows real JSON response (adapted shape).
10. Change target to Japanese (not in tenant's allowed_language). Click Translate. Banner appears: "Target language [ja] not allowed for this profile. Allowed: [id, en]". Copy trace ID button works.
11. Click Translate again with valid target. Banner dismisses. Second translate hits cache (cached=true badge visible). Latency drops < 100ms.
12. Reload browser. Settings persist (no re-paste needed).
13. Edit `.env.local` `VITE_API_MODE=mock`. Reload. Translate hits mock (instant fake response). No real backend call.

---

## 9. ADRs (new)

- **ADR-059:** Frontend adapter pattern over types.ts rewrite. `responseAdapter.ts` maps backend response → frontend `TranslateResponse` type without forcing canonical alignment. Trade-off: future backend swap edits adapter, not types. Acceptable — adapter is the swap point.
- **ADR-060:** Synthetic streaming for agentic events. Real `/translate` is one-shot; frontend replays `agent_completed` events spaced by `activity.latency_ms` to preserve AgentPipeline progressive-parallel animation. Cache hit short-circuits replay. Future SSE upgrade replaces the replay loop.
- **ADR-061:** Settings modal route over Tab 1 tenant embedding. Backend credentials (API key + tenant_id + profile_id) configured separately from mock tenant management. Honors ADR-049 "Tab 1 mock-only forever". Trade-off: two unlinked entities visible (mock tenant + real credentials); mitigated by gear icon framing.
- **ADR-062:** `VITE_API_MODE` env var toggle, default `mock`. Demo runs out-of-box without backend; operator sets `=real` in `.env.local` (gitignored) when ready. No runtime UI toggle (deferred).
- **ADR-063:** Vite dev proxy `/api/*` → `localhost:8000`. Frontend code uses relative `/api/translate` paths. Backend CORS allowlist extends to `localhost:5173` for direct-hit fallback. Production deployment uses reverse proxy with identical path mapping.
- **ADR-064:** 5 explicit error_code → UI mapping (language_not_allowed, authentication_failed/tenant_not_found, rate_limited, upstream_transient, generic). Banner above OutputBox with severity-tinted color (amber for soft errors, crimson for auth/transient). Copy-on-click trace_id for support correlation.

ADRs di-promote ke `docs/adrs.md` saat implementation Batch F-equivalent.

---

## 10. Out of scope / future sub-projects

- Real cascade UI replacing Tab 1 tenant management (per ADR-049).
- JWT login + refresh flow + token rotation cron.
- SSE/WebSocket real streaming of agentic events.
- Operator-editable tenant_prompts templates (admin UI).
- Profile/tenant discovery via `/tenant-profiles` endpoint (auto-list instead of paste).
- Multi-account / credential switching UI.
- Production-grade error reporting (Sentry, Datadog, etc).
- Glossary management UI for service-level glossary terms.

---

## 11. Risks & mitigations

| Risk | Mitigation |
|---|---|
| API key in localStorage XSS-exposed | Demo/dev context per ADR-026 PII trade-off precedent. Production rollout will need session-based auth. |
| Frontend types.ts drift from backend evolves further | Adapter is the canonical translation layer; tests for adapter cover the contract. |
| Synthetic streaming feels "fake" if backend timing weird | Use actual `latency_ms` from response — reflects reality. If backend latency irregular, replay irregular. |
| Mock/real toggle confusion | Settings modal explicitly labels current `VITE_API_MODE` ("Currently using: REAL backend" vs "Currently using: MOCK in-memory"). User can verify mode at-a-glance via modal. No persistent TopBar badge in MVP — keep TopBar uncluttered. |
| Backend CORS allowlist proliferation | Only add `localhost:5173`; remove defunct `localhost:8501`. Keep allowlist minimal. |
| Pre-existing 22 tests break | Run vitest after each task in implementation plan; fix locally before commit. |
| Vite proxy doesn't apply to production builds | Production deployment uses reverse proxy or absolute base URL via Settings. Documented. |
