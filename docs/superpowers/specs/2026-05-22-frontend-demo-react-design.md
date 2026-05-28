# Design — Frontend Demo React Redesign (Sub-proyek J)

> **Tanggal**: 2026-05-22
> **Status**: Approved (brainstorm), pending implementation plan
> **Author**: zaky + Claude (brainstorm session)
> **Sub-proyek**: J — replace Streamlit demo with Vite + React + TS + Tailwind + shadcn/ui SPA
> **Depends on**: sub-proyek I (tenant junction + auth — must commit first). Frontend integration with real backend happens in a follow-up phase after I is merged.
> **Replaces**: `demo/app.py` (Streamlit). Streamlit demo deleted only after React frontend verified working end-to-end.
> **Unblocks**: stakeholder-grade product demos; future operator portal can fork from this scaffold.

---

## 1. Konteks & motivasi

Streamlit demo (`demo/app.py`) sudah cukup untuk operator-style internal validation, tapi tidak cocok untuk product demo ke audience teknis (AI engineers, data scientists, technical PMs) yang user targetkan. Streamlit batasannya:

- Visual style generic, tidak match brand premium yang dimaksudkan
- Tidak support animasi rich (dot-flow di pipeline, parallel completion visualization, typewriter streaming)
- Real-time language detection di typing-time clunky (Streamlit rerun cycle)
- Tab structure rigid

User memberikan **design brief lengkap** untuk SPA modern bertema dark/premium dengan dua tab: **Tenant Management** + **Translation Playground**. Inti demo: pipeline visualization yang transparan menunjukkan agentic orchestration di sub-proyek G+C (parallel `lang_detect_input` + `translate` agents). Brief ini drive seluruh design ini.

Frontend ini akan eventually connect ke real sub-proyek I backend (auth + /translate), tapi v1 mock-only — purely demo-able tanpa backend running.

## 2. Goals & non-goals

**Goals (v1):**
- Scaffold `./frontend-demo/` dengan Vite + React 18 + TypeScript (strict) + Tailwind 3 + shadcn/ui + Framer Motion 11.
- Implement design brief verbatim (visual system, layout, animations, edge cases).
- Mock API (`services/mockApi.ts`) returns shape yang match expected sub-proyek I `/translate` response — cheap swap saat real-integration phase.
- PowerShell launcher (`scripts/run-demo.ps1`) yang force-open Chrome saat Vite dev server ready.
- Vitest + RTL tests untuk hooks + state machine + language detector + mock API contract (~15–18 tests).
- Delete `demo/app.py` (Streamlit) di commit terakhir setelah React frontend verified.

**Non-goals (v1):**
- Bukan real backend integration — `services/realApi.ts` di-dokumentasikan tapi tidak di-implement.
- Bukan tenant cascade UI (country → company → department → position → service). Tab 1 stays simple mock per brief; real cascade dibangun di future sub-project.
- Bukan SSE/WebSocket streaming dari backend — adapter pattern future-proof tapi v1 tidak butuh.
- Bukan responsive mobile/tablet — desktop-first demo (brief tidak minta).
- Bukan i18n/translation untuk UI string itu sendiri — UI labels hard-coded English.
- Bukan production deployment (CI/CD, hosting) — local dev only.
- Bukan automated visual regression testing (Storybook, Chromatic). Manual smoke checklist saja untuk animasi.
- Bukan auth flow di frontend (login screen, token refresh UI) — auth headers di-hardcode di realApi adapter saat phase integrasi.

## 3. Keputusan utama

### 3.1 Stack: Vite + React + TS + Tailwind + shadcn/ui + Framer Motion

**Alternatif rejected**: Next.js (over-engineering untuk pure SPA tanpa SSR/routing needs), CRA (deprecated), plain HTML+JS (animasi kompleks butuh React state machinery).

Vite chosen for fast HMR + minimal config. shadcn/ui chosen sebagai primitive layer (Button, Card, Tabs, Select, Badge, Tooltip, Dialog) — bukan full component library tapi copy-paste accessible primitives. Framer Motion chosen untuk SVG dot-flow + node ring pulses + parallel layout coordination yang sulit di-replicate dengan CSS keyframes alone.

### 3.2 Frontend types = real sub-proyek I backend shape (canonical)

Design brief contains illustrative payload JSON. **Spec adopts real sub-proyek I `/translate` response shape sebagai canonical types**, BUKAN brief's example. Reason:

- Brief mention "easy to swap with real endpoints later" — paling cheap kalau mock dan real return shape sama
- Real shape RICHER (e.g., `prompt_applied`, `trace_id`, `log_id`, `glossary_compliance`) — PayloadViewer dapat showcase actual API contract yang berguna untuk audience teknis
- Brief's payload example tetap relevan sebagai reference visual untuk highlighting/layout, tapi key set canonical = real backend

PayloadViewer renders whatever fields are in TranslateResponse. Per-field handling generic via JSON tree highlighter, bukan per-field hardcoded.

### 3.3 Tab 1 (Tenant Management) stays mock-only forever

Brief's tenant model (name + langs + model_tier + toggles) sengaja simpler dari sub-proyek I tenant junction (country/company/department × position × service). Two reasons:

- Demo audience wants polished consumer-app feel, bukan operator config form
- Sub-proyek I cascade UI butuh terpisah karena UX needs berbeda (multi-step wizard + side-by-side validation)

Tab 1 tenant CRUD purely in-memory (`useState<Tenant[]>` di App). Future sub-project bisa tambah second tab atau separate admin app untuk real cascade.

### 3.4 PowerShell launcher force Chrome (bukan default browser)

Per user explicit request. Launcher cari `chrome.exe` via `Get-Command` + 3 standard install paths + `CHROME_PATH` env override. Vite dev script TIDAK pakai `--open` — kita kontrol browser open dari PowerShell setelah port ready.

**Alternatif rejected**: `--open` Vite flag (mem-open default browser, bukan eksplisit Chrome); start_url di Windows associations (kurang predictable).

### 3.5 Component split (bukan single-file artifact)

Design brief §6 menyebut "Single-file React component" tapi top-of-brief minta "separate components for TenantManagement, TranslationPlayground, AgentPipeline, PayloadViewer". **Pilih multi-file split** — single-file note adalah artifact-mode mindset, tidak cocok untuk scaffold yang akan grow ke real-integration phase.

### 3.6 Tests target state machines + contract, skip animations

Animasi di-verify via manual smoke checklist. Yang di-test otomatis: `useTranslationFlow` state machine, `useTypewriter`, `useDebouncedValue`, `languageDetector`, `mockApi` contract, mismatch banner logic, payload viewer rendering. Total ~15–18 tests.

Reason: visual regression tests (Storybook + Chromatic) butuh infrastructure di luar v1 scope. Hooks + service layer have clear state contracts yang worth testing; animasi-nya stateful tapi visualnya subjective.

### 3.7 Single mega-commit at end of implementation

Konsisten dengan precedent sub-proyek H/I plan. Implementation runs as multi-phase plan (~5 phases), tapi commit final-only. Memudahkan rollback kalau gagal di tengah, dan commit message tunggal lebih representative untuk "new sub-project deliverable".

## 4. Architecture & directory layout

**Stack:**
- Vite 5 + React 18 + TypeScript 5 (strict mode)
- Tailwind CSS 3 + shadcn/ui (CLI-installed components on demand)
- Framer Motion 11
- Vitest + @testing-library/react + jsdom
- ESLint (typescript-eslint + react-hooks) + Prettier

**Top-level layout:**

```
frontend-demo/
├── package.json                 # scripts: dev, build, preview, test, lint, format
├── vite.config.ts               # alias '@' → src/, plugins: react, tailwind, vitest
├── tailwind.config.ts           # extend palette from brief, fonts (Inter, JetBrains Mono)
├── postcss.config.js
├── tsconfig.json                # strict, path aliases, project references
├── tsconfig.node.json           # vite config typing
├── .eslintrc.cjs
├── .prettierrc
├── .gitignore                   # node_modules, dist, coverage, .env.local
├── components.json              # shadcn config (slate dark base, '@/components/ui')
├── index.html                   # links Inter + JetBrains Mono from Google Fonts
├── public/
│   └── favicon.svg
└── src/
    ├── main.tsx                 # bootstrap, mount App
    ├── App.tsx                  # top bar + tabs router
    ├── index.css                # @tailwind directives + CSS vars + keyframes (shimmer, shake)
    │
    ├── components/
    │   ├── ui/                  # shadcn-generated: Button, Card, Tabs, Select, Badge, Dialog, Tooltip
    │   ├── TopBar.tsx
    │   ├── TenantManagement/
    │   │   ├── index.tsx
    │   │   ├── TenantForm.tsx
    │   │   └── TenantTable.tsx
    │   ├── TranslationPlayground/
    │   │   ├── index.tsx
    │   │   ├── LanguageBar.tsx
    │   │   ├── InputBox.tsx
    │   │   ├── LanguageMismatchBanner.tsx
    │   │   ├── OutputBox.tsx
    │   │   └── TranslateButton.tsx
    │   ├── AgentPipeline/
    │   │   ├── index.tsx
    │   │   ├── PipelineDiagram.tsx    # SVG + Framer motion paths
    │   │   ├── AgentCard.tsx
    │   │   └── PipelineSummary.tsx
    │   └── PayloadViewer/
    │       ├── index.tsx
    │       └── JsonHighlighter.tsx
    │
    ├── services/
    │   ├── types.ts             # contract types (mirrors real sub-proyek I)
    │   ├── mockApi.ts           # TranslateApi implementation with setTimeout simulation
    │   ├── languageDetector.ts  # keyword-based detect (6 langs)
    │   └── pricing.ts           # ModelId → token cost
    │
    ├── hooks/
    │   ├── useDebouncedValue.ts
    │   ├── useElapsedTimer.ts
    │   ├── useTypewriter.ts
    │   └── useTranslationFlow.ts
    │
    ├── lib/
    │   ├── cn.ts                # twMerge wrapper (shadcn default)
    │   └── format.ts            # currency, latency, token count formatters
    │
    └── mocks/
        ├── tenants.ts           # 4–5 seeded tenants
        └── translations.ts      # lookup table for common test inputs
```

**Position in repo:**
- `./frontend-demo/` adalah sibling dari `demo/`, `src/`, `sdk/`.
- Streamlit `demo/app.py` _stays_ sampai React verified, baru dihapus di commit terakhir sub-proyek J.
- `scripts/run-demo.ps1` di root (sibling `scripts/seed_tenant_data.py`).
- Root `.gitignore` di-extend untuk `frontend-demo/node_modules`, `dist`, `coverage`.

**Build/run commands:**
- Dev: `npm run dev` → Vite on port 5173
- Build: `npm run build`
- Test: `npm run test` (Vitest watch) atau `npm run test -- --run` (CI mode)
- Lint: `npm run lint`
- Format: `npm run format`

## 5. Component breakdown & state ownership

### 5.1 Sources of state

**App-level** (`App.tsx` — useReducer atau split useState):
- `activeTab: 'tenant' | 'playground'` (default: `'playground'`)
- `tenants: Tenant[]` (seeded dari `mocks/tenants.ts`, mutated via TenantManagement callbacks)
- `activeTenantId: string | null` (default: first tenant)

**Playground-level** (owned by `TranslationPlayground/index.tsx`):
- `inputText: string`
- `sourceLang: LangCode`, `targetLang: LangCode`
- `modelId: ModelId`
- Flow state via `useTranslationFlow()` hook
- `latestPayload: TranslateResponse | null`

**Component-local:**
- `TenantForm` — local `useState` per-field (no form library; v1 doesn't justify react-hook-form + zod overhead untuk 6-field form)
- `PayloadViewer` — `expanded: boolean` + `copyFlash: boolean`
- `OutputBox` — typewriter index via `useTypewriter` hook
- `AgentCard` — `expanded: boolean` for "View I/O" reveal

### 5.2 State machine — `useTranslationFlow`

```ts
type FlowState =
  | { status: 'idle' }
  | { status: 'detecting' }
  | { status: 'running', startedAt: number, agents: AgentStates }
  | { status: 'done', payload: TranslateResponse, agents: AgentStates }
  | { status: 'error', message: string }

type AgentState = {
  status: 'idle' | 'running' | 'completed' | 'failed'
  model: ModelId
  startedAt?: number
  completedAt?: number
  tokens?: { input: number; output: number }
  cost_usd?: number
  latency_ms?: number
  text_input?: string
  llm_output?: unknown
}
type AgentStates = {
  lang_detect_input: AgentState
  translate: AgentState
}
```

Hook exposes:
- `state: FlowState`
- `elapsed: number` (ms, ticked di-`running`)
- `detectedLang: LangCode | null`, `detectionConfidence: number | null`
- `start(req: TranslateRequest): void`

Internally:
- Subscribes ke `mockApi.translate(req, { onAgentEvent })`. `onAgentEvent` fires `agent_started` (segera, dalam 50ms untuk parallel feel) + `agent_completed` (sesuai per-agent latency).
- Separate effect: debounce `inputText` (500ms) → call `languageDetector.detect()` synchronously, update `detectedLang` + `detectionConfidence`. Independent dari agent flow.
- 30ms-tick `useElapsedTimer` selama `status === 'running'`.

### 5.3 Dataflow diagram

```
App.tsx
  ├── TopBar (activeTenant, tenants → display + dropdown)
  └── <Tabs value={activeTab}>
      ├── <TabsContent value="tenant">
      │     TenantManagement
      │       ├── TenantForm (onCreate)
      │       └── TenantTable (tenants, onSelect, onDelete)
      └── <TabsContent value="playground">
            TranslationPlayground (owns playground state + hook)
              ├── LanguageBar (sourceLang, targetLang, modelId, onSwap, onModelChange)
              ├── InputBox (text, onChange, detectedLang, mismatch, onSwitchSource)
              ├── OutputBox (translatedText, status, onCopy, onRegenerate)
              ├── TranslateButton (disabled, onClick=flow.start)
              ├── AgentPipeline (flow.state.agents, elapsed, summary)
              └── PayloadViewer (latestPayload | null, defaultOpen=false)
```

## 6. Mock API design & types contract

### 6.1 `services/types.ts`

```ts
export type LangCode = 'en' | 'id' | 'es' | 'fr' | 'de' | 'ja' | 'zh' | 'ar' | 'pt' | 'ru'
export type ModelId = 'claude-haiku-4-5' | 'claude-sonnet-4-6' | 'claude-opus-4-7' | 'gpt-4o-mini'
export type AgentName = 'lang_detect_input' | 'lang_detect_output' | 'translate'
export type AgentStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface TranslateRequest {
  text: string
  source_lang: LangCode | null      // null → auto-detect
  target_lang: LangCode
  tenant_id: string
  profile_id: string                 // matches sub-proyek I tenant_profile.profile_id
  model_id?: ModelId                 // optional override
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
    opts: { onAgentEvent: (e: AgentEvent) => void }
  ): Promise<TranslateResponse>
}
```

### 6.2 `services/mockApi.ts` behavior

- **Parallel start**: kedua agent fire `agent_started` dalam 50ms (mensimulasikan parallel orchestration ADR-031).
- **Realistic latency**: `lang_detect_input` resolves 120–280ms; `translate` 800–1800ms (skala berdasarkan model — Haiku faster, Opus slower).
- **Token & cost generation**: `input_tokens ≈ text.length / 3.7`; `output_tokens ≈ input × random[0.8, 1.4]`; `cost_usd = tokens × pricing[model]` (from `pricing.ts`).
- **Text output**: keyword-based lookup di `mocks/translations.ts` untuk common test inputs; fallback ke generic "[translation of '...']" placeholder. Demo tidak perlu real translation.
- **Cache simulation**: same text+source+target dalam session → return `cached: true, latency_ms: 3`. UI shows "Cached" badge + skip pipeline animation.
- **Error injection (dev-only)**: querystring `?error=translate` → mockApi throws untuk demo error state. Pipeline shows failed agent dengan red ring.

### 6.3 `services/languageDetector.ts`

Synchronous keyword-based, runs in browser. Detects 6 languages (en, id, es, fr, de, ja) via stopword overlap scoring. Returns `{ lang: LangCode, confidence: number, alternatives: [{lang, confidence}] }` atau `null` kalau uncertain.

**Separate dari** `agentic_activities.lang_detect_input` di TranslateResponse — detector ini typing-time UX feature; agent activity adalah actual LLM result. Per ADR-033 precedent (frontend langdetect vs Haiku agent — different layers).

### 6.4 `mocks/tenants.ts`

```ts
export const SEED_TENANTS: Tenant[] = [
  { id: 'tnt_a3f9k2', name: 'Acme Localization', ... },
  { id: 'tnt_x7m2q5', name: 'TravelGenie Inc.', ... },
  { id: 'tnt_b8h4n1', name: 'Globex Trading Pte Ltd', ... },
  { id: 'tnt_q5k9p7', name: 'Lumen Health Network', ... },
  { id: 'tnt_d2v6c8', name: 'Aitegrity Internal', ... },
]
```

### 6.5 Real-integration roadmap (NOT in v1)

Future `services/realApi.ts` implements `TranslateApi`:
1. `POST ${VITE_API_BASE}/translate` dengan `Authorization: Bearer <jwt>` atau `X-Tenant-API-Key`
2. HTTP single-shot — adapter fires `agent_started` segera, lalu schedule `agent_completed` events di waktu relatif sesuai `agentic_activities[i].latency_ms`. Visual progression feel preserved tanpa streaming.
3. Switch via `VITE_API_MODE=mock|real` env var.

Sub-proyek selanjutnya (post-v1) bisa tambah SSE/WebSocket untuk genuine streaming.

## 7. Launcher mechanics

### 7.1 `scripts/run-demo.ps1`

```powershell
$ErrorActionPreference = 'Stop'

# 1. Locate chrome.exe
$chromePaths = @(
    $env:CHROME_PATH,
    "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "${env:LocalAppData}\Google\Chrome\Application\chrome.exe"
)
$chrome = $chromePaths | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $chrome) {
    $chrome = (Get-Command chrome.exe -ErrorAction SilentlyContinue).Source
}
if (-not $chrome) {
    Write-Error "Chrome not found. Set `$env:CHROME_PATH or install Chrome."
    exit 1
}

# 2. Resolve frontend dir
$projectRoot = Split-Path $PSScriptRoot -Parent
$frontendDir = Join-Path $projectRoot 'frontend-demo'
$url = 'http://localhost:5173'

# 3. Install deps if needed
if (-not (Test-Path (Join-Path $frontendDir 'node_modules'))) {
    Write-Host 'Installing dependencies...' -ForegroundColor Cyan
    Push-Location $frontendDir
    try { npm install } finally { Pop-Location }
}

# 4. Background job: wait for Vite, open Chrome
$openJob = Start-Job -ScriptBlock {
    param($url, $chrome)
    for ($i = 0; $i -lt 60; $i++) {
        try {
            $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 1
            if ($r.StatusCode -eq 200) {
                Start-Process -FilePath $chrome -ArgumentList $url
                return
            }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    Write-Host 'Vite did not start in 30s — opening Chrome anyway'
    Start-Process -FilePath $chrome -ArgumentList $url
} -ArgumentList $url, $chrome

# 5. Run Vite in foreground
Push-Location $frontendDir
try {
    npm run dev
} finally {
    Remove-Job -Job $openJob -Force -ErrorAction SilentlyContinue
    Pop-Location
}
```

**Edge cases ditangani:**
- Chrome not found → clear error + `CHROME_PATH` override suggestion
- Vite port 5173 busy → Vite errors visible di main thread, script tidak crash
- User `Ctrl+C` Vite → `finally` cleanup background job
- node_modules missing → auto-install on first run

## 8. Animations

### 8.1 Tailwind transitions (no JS)

- Hover lift cards (`hover:-translate-y-0.5 hover:shadow-lg transition-all duration-200`)
- Button press scale (`active:scale-[0.98] transition-transform`)
- Mismatch banner slide-in (`transition-all data-[state=open]:translate-y-0 data-[state=closed]:-translate-y-2`)
- Tab content cross-fade (shadcn `Tabs` built-in)

### 8.2 CSS keyframes (di `index.css`)

- **Shimmer skeleton** — `background: linear-gradient(90deg, #16161d 0%, #1c1c25 50%, #16161d 100%); animation: shimmer 1.5s infinite`
- **Shake on first banner appear** — `@keyframes shake { 0%, 100% { transform: translateX(0) } 25% { translateX(-4px) } 75% { translateX(4px) } }`, apply once via `animation: shake 200ms`

### 8.3 Framer Motion (state-coordinated)

- **SVG dot-flow on pipeline paths**: `<motion.circle>` dengan `animate={{ offsetDistance: ['0%', '100%'] }}, transition={{ duration: 1.5, repeat: Infinity, ease: 'linear' }}` + `offsetPath: 'path(...)'`. Multiple dots offset by phase. Active only when `agent.status === 'running'`.
- **Agent node ring pulse**: `<motion.circle>` dengan `animate={{ scale: [1, 1.05, 1], opacity: [0.6, 1, 0.6] }}` saat 'running', static green saat 'completed'.
- **Tab underline indicator**: `<motion.div layoutId="tab-underline">` slides between triggers.
- **New tenant slide-in**: `<motion.tr layout>` di `<AnimatePresence>` dengan `initial={{ opacity: 0, y: -10 }}, animate={{ opacity: 1, y: 0 }}` + cyan glow yang fade out via Tailwind transition setelah 1.5s.
- **Translate button → loading**: `<motion.button>` morphs antara "Translate" label dan `<Loader2 className="animate-spin" />`.

### 8.4 Custom hooks

- `useTypewriter(targetText, speedMs = 25)` — increments substring via `setInterval`, returns `{ displayed, isComplete }`. OutputBox consumes.
- `useElapsedTimer(active)` — ticks every 30ms while `active`, returns `elapsedMs`. Display sebagai `(ms / 1000).toFixed(3) + 's'` monospace.
- `useDebouncedValue<T>(value, delayMs)` — standard debounce. InputBox consumes untuk language detection trigger.
- `useTranslationFlow()` — state machine described in §5.2.

## 9. Testing strategy

### 9.1 Automated (Vitest + RTL) — ~15–18 tests

| File | Count | Coverage |
|---|---|---|
| `hooks/useTranslationFlow.test.ts` | 4 | idle → detecting → running → done; parallel agent completion; error propagation; elapsed timer ticks |
| `hooks/useTypewriter.test.ts` | 2 | character-by-character output; isComplete flag at end |
| `hooks/useDebouncedValue.test.ts` | 2 | debounce timing; cancel on unmount |
| `services/languageDetector.test.ts` | 4 | detect en/id/es/fr/de/ja samples; ambiguous returns null |
| `services/mockApi.test.ts` | 3 | onAgentEvent fires in expected order; response shape matches TranslateResponse contract; cache hit semantics |
| `components/TranslationPlayground/LanguageMismatchBanner.test.tsx` | 2 | shows when detected ≠ selected; hides when match |
| `components/PayloadViewer/JsonHighlighter.test.tsx` | 2 | renders TranslateResponse shape; copy button feedback |

### 9.2 Manual smoke (post-implementation)

Brief §5 + §8 jadi checklist:

1. `pwsh scripts/run-demo.ps1` → Chrome auto-opens to http://localhost:5173 dalam ~5 detik
2. Default tab = Playground; pre-filled Indonesian sample text
3. Type "Halo apa kabar hari ini?" → "Detected: Indonesian · 98% confidence" muncul di bawah textarea
4. Switch source ke English → red banner slide-in dengan shake; "Switch source to Indonesian" button works
5. Click Translate → button press animation; output box → shimmer skeleton dengan rotating microcopy; pipeline diagram lights up (both nodes pulse, dots flow on both paths)
6. lang_detect_input completes first (~200ms) → flashes green, dot-flow stops on its path; translate completes after ~1.2s → typewriter streams output character-by-character
7. PayloadViewer collapsed; expand → JSON renders dengan syntax highlighting (cyan strings, violet numbers, white keys); copy button shows checkmark on success
8. Switch ke Tenant tab → 4–5 tenants visible; create new tenant → slides in at top dengan cyan glow
9. Switch back to Playground → state preserved; payload still rendered
10. Long input (>5000 chars) → soft warning banner above textarea
11. Empty input → Translate button disabled
12. Querystring `?error=translate` → translate agent fails dengan red ring, OutputBox shows error message

### 9.3 What's NOT tested in v1

- Visual animations (Framer/CSS) — manual smoke only
- Tenant CRUD logic — trivial useState mutations
- shadcn primitives — third-party
- Layout responsive — desktop-first per brief
- PowerShell launcher — manual smoke (Windows machine required)

## 10. Error handling

| Scenario | Behavior |
|---|---|
| Empty input | TranslateButton `disabled`; muted helper text "Enter text above to translate" |
| Input >5000 chars | Char counter turns amber; soft banner "Long input — translation may be slower or hit token limits" |
| Detected lang ≠ selected source | Red banner above textarea with AlertCircle, slide-in + 200ms shake, "Switch source to {lang}" CTA |
| Match | Banner not rendered (clean state) |
| Pipeline empty (no run yet) | Diagram in muted gray, low-opacity rings, hint "Run a translation to see the pipeline in action" |
| PayloadViewer empty | "No payload yet — run a translation" placeholder |
| mockApi `?error=translate` | FlowState `{ status: 'error' }`; OutputBox shows error icon + message in red; failed agent shows red ring |
| Cache hit | Mock returns `cached: true, latency_ms: 3`; UI shows "Cached" badge in summary footer; pipeline skips animation (instant green flash) |
| Chrome not found in launcher | PowerShell error + `CHROME_PATH` override suggestion |
| Vite port 5173 busy | Vite errors visible; user kills other process or `npm run dev -- --port 5174` |

## 11. ADR additions

ADRs land in CLAUDE.md "Decision log" pada commit terakhir sub-proyek J.

| ID | Topic |
|----|-------|
| **ADR-047** | New frontend (Vite + React + TS + Tailwind + shadcn/ui + Framer Motion) replaces Streamlit demo. Reason: brief minta visual rich + animasi tinggi yang Streamlit batasi; demo audience teknis butuh polish stakeholder-grade. Streamlit dihapus setelah React verified. |
| **ADR-048** | Frontend TypeScript types match real sub-proyek I `/translate` response shape (canonical), bukan brief's illustrative payload. Reason: cheap mock-to-real swap (single file replacement). Brief's payload example tetap dijadikan visual reference. |
| **ADR-049** | Tab 1 (Tenant Management) mock-only forever. Brief's tenant model sengaja simpler dari sub-proyek I tenant junction. Real cascade UI (country → company → department → position → service) deferred ke future sub-project — UX needs berbeda (multi-step wizard) dan demo audience focus consumer-app feel. |
| **ADR-050** | PowerShell launcher force-open Chrome explicitly (bukan default browser). Reason: user requirement, predictable behavior. `Get-Command` + 3 standard install paths + `CHROME_PATH` env override. Vite TIDAK pakai `--open` flag. |
| **ADR-051** | shadcn/ui adopted sebagai base primitive layer (bukan Material/Chakra/Mantine). Reason: copy-paste primitives accessible by default, no runtime CSS-in-JS, generated components tinggal di repo (versioned, customizable). Trade-off: lebih banyak files vs single npm import. |

## 12. Open questions / future work

**Out of scope sub-proyek J (deferred to future sub-projects):**
- Real API integration (`services/realApi.ts` implementation, auth flow UI)
- Tenant cascade UI (real sub-proyek I tenant junction)
- SSE/WebSocket streaming dari backend untuk genuine real-time agent events
- Production deployment (Vercel/Netlify), CDN, custom domain
- i18n untuk UI strings sendiri
- Responsive mobile/tablet layout
- Storybook + Chromatic visual regression
- Operator-facing prompt editor (uses tenant_prompts.update)
- Multi-tab batch translation
- Glossary/style examples management UI

**Risks / unknowns:**
- Framer Motion `offsetDistance` + `offsetPath` browser support — Chrome OK, but verify exact MotionValue behavior pada Vite dev build
- shadcn/ui CLI requires Node 18+ — confirm user environment
- PowerShell `Start-Job` cleanup on Ctrl+C kadang flaky — test pada Windows 11 PowerShell 7.x
- Brief's color `#fee2e2` text on red surface = pale red on red — verify contrast ratio (mungkin perlu adjust)

## 13. References

- Design brief (terlampir di chat — komplit dari user dengan visual system, layout, animasi, mock data, edge cases)
- Sub-proyek I spec: `docs/superpowers/specs/2026-05-22-tenant-junction-redesign-design.md` — defines real `/translate` response shape yang frontend types mirror
- CLAUDE.md ADR-013 (graceful degradation precedent — cache down ≠ crash)
- CLAUDE.md ADR-027 (record_log swallow — service degrades, doesn't crash)
- CLAUDE.md ADR-031 (parallel agent orchestration — `lang_detect_input` + `translate`, `_safe_run` pattern)
- CLAUDE.md ADR-033 (Haiku-backed lang detect agent vs Streamlit's frontend langdetect — different layers; same precedent applies here untuk demo's typing-time vs LLM-agent split)
- Streamlit `demo/app.py` — UI reference yang akan di-replace; `demo/app.py` deletion is last step of implementation
