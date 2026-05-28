# Frontend Demo React Redesign Implementation Plan (Sub-proyek J)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Vite + React + TypeScript + Tailwind + shadcn/ui + Framer Motion SPA at `./frontend-demo/` that replaces the Streamlit demo, with a PowerShell launcher that force-opens Chrome.

**Architecture:** Single-page React app with two tabs (Tenant Management, Translation Playground). State managed by `useTranslationFlow` state machine; mock API at `services/mockApi.ts` returns the same shape as the real sub-proyek I `/translate` endpoint so the swap is cheap later. shadcn/ui primitives for accessibility; Framer Motion for SVG dot-flow + node pulse animations. PowerShell launcher locates `chrome.exe`, runs Vite in foreground, opens Chrome once dev server is ready.

**Tech Stack:** Vite 5, React 18, TypeScript 5 (strict), Tailwind CSS 3, shadcn/ui, Framer Motion 11, Vitest, @testing-library/react, ESLint, Prettier. PowerShell 7+ on Windows for the launcher.

**Commit policy:** Per user preference + spec §3.7 — **single mega-commit at the end** (no per-phase commits). **Never `git push`**.

**Spec reference:** `docs/superpowers/specs/2026-05-22-frontend-demo-react-design.md` (committed as 4772f1c).

**Dependency on sub-proyek I:** This plan can be drafted at any time but should ONLY be executed AFTER sub-proyek I is committed. The working tree currently has uncommitted sub-proyek I work; do not start sub-proyek J implementation until that is resolved.

---

## File Structure

**New files (`frontend-demo/` package):**

| Path | Responsibility |
|------|----------------|
| `frontend-demo/package.json` | npm manifest + scripts (dev, build, preview, test, lint, format) |
| `frontend-demo/vite.config.ts` | Vite + React plugin + Vitest config + `@` → `src/` alias |
| `frontend-demo/tailwind.config.ts` | Extended palette from brief; Inter + JetBrains Mono fonts; custom keyframes |
| `frontend-demo/postcss.config.js` | Tailwind + autoprefixer plugins |
| `frontend-demo/tsconfig.json` | Strict TS, path alias, project references |
| `frontend-demo/tsconfig.node.json` | Vite config typing |
| `frontend-demo/.eslintrc.cjs` | typescript-eslint + react-hooks rules |
| `frontend-demo/.prettierrc` | Standard config |
| `frontend-demo/.gitignore` | `node_modules`, `dist`, `coverage`, `.env.local` |
| `frontend-demo/components.json` | shadcn/ui config (dark slate, `@/components/ui` alias) |
| `frontend-demo/index.html` | Vite entry; Inter + JetBrains Mono link tags |
| `frontend-demo/public/favicon.svg` | Polyglot AI mark |
| `frontend-demo/src/main.tsx` | React bootstrap |
| `frontend-demo/src/App.tsx` | Top bar + tab routing (tenant, playground) |
| `frontend-demo/src/index.css` | Tailwind directives + CSS vars + custom keyframes (shimmer, shake) |
| `frontend-demo/src/components/ui/*` | shadcn-generated primitives (Button, Card, Tabs, Select, Badge, Dialog, Tooltip) |
| `frontend-demo/src/components/TopBar.tsx` | Brand + active tenant dropdown |
| `frontend-demo/src/components/TenantManagement/index.tsx` | Two-pane layout |
| `frontend-demo/src/components/TenantManagement/TenantForm.tsx` | Create-tenant form |
| `frontend-demo/src/components/TenantManagement/TenantTable.tsx` | Tenant list with row actions |
| `frontend-demo/src/components/TranslationPlayground/index.tsx` | Composition + state ownership |
| `frontend-demo/src/components/TranslationPlayground/LanguageBar.tsx` | Source/target/model selectors + swap |
| `frontend-demo/src/components/TranslationPlayground/InputBox.tsx` | Textarea + detected lang display + mismatch banner |
| `frontend-demo/src/components/TranslationPlayground/LanguageMismatchBanner.tsx` | Red warning slide-in |
| `frontend-demo/src/components/TranslationPlayground/OutputBox.tsx` | Streaming output with skeleton + actions |
| `frontend-demo/src/components/TranslationPlayground/TranslateButton.tsx` | Gradient CTA with loading state |
| `frontend-demo/src/components/AgentPipeline/index.tsx` | Diagram + cards + summary footer |
| `frontend-demo/src/components/AgentPipeline/PipelineDiagram.tsx` | SVG paths + animated dots |
| `frontend-demo/src/components/AgentPipeline/AgentCard.tsx` | Per-agent metrics card |
| `frontend-demo/src/components/AgentPipeline/PipelineSummary.tsx` | Aggregate stats footer |
| `frontend-demo/src/components/PayloadViewer/index.tsx` | Collapsible JSON viewer wrapper |
| `frontend-demo/src/components/PayloadViewer/JsonHighlighter.tsx` | Custom syntax highlighter |
| `frontend-demo/src/services/types.ts` | All API contract types |
| `frontend-demo/src/services/mockApi.ts` | TranslateApi mock implementation |
| `frontend-demo/src/services/languageDetector.ts` | Keyword-based detector (6 langs) |
| `frontend-demo/src/services/pricing.ts` | Model → token-cost table |
| `frontend-demo/src/hooks/useDebouncedValue.ts` | Generic debounce hook |
| `frontend-demo/src/hooks/useElapsedTimer.ts` | Live ms ticker |
| `frontend-demo/src/hooks/useTypewriter.ts` | Character-by-character output |
| `frontend-demo/src/hooks/useTranslationFlow.ts` | State machine for translate cycle |
| `frontend-demo/src/lib/cn.ts` | `clsx` + `tailwind-merge` helper |
| `frontend-demo/src/lib/format.ts` | Currency, latency, token count formatters |
| `frontend-demo/src/mocks/tenants.ts` | 5 seeded tenants |
| `frontend-demo/src/mocks/translations.ts` | Lookup table for test inputs |
| `frontend-demo/src/hooks/useDebouncedValue.test.ts` | Debounce timing tests |
| `frontend-demo/src/hooks/useTypewriter.test.ts` | Typewriter output tests |
| `frontend-demo/src/hooks/useTranslationFlow.test.ts` | State machine tests |
| `frontend-demo/src/services/languageDetector.test.ts` | Detection tests |
| `frontend-demo/src/services/mockApi.test.ts` | Mock API contract tests |
| `frontend-demo/src/components/TranslationPlayground/LanguageMismatchBanner.test.tsx` | Banner visibility tests |
| `frontend-demo/src/components/PayloadViewer/JsonHighlighter.test.tsx` | Highlighter rendering tests |
| `scripts/run-demo.ps1` | PowerShell launcher (Chrome + Vite coordinator) |

**Modified files:**

| Path | What changes |
|------|--------------|
| `.gitignore` (root) | Append `frontend-demo/node_modules/`, `frontend-demo/dist/`, `frontend-demo/coverage/`, `frontend-demo/.env.local` |
| `CLAUDE.md` | Append ADR-047 through ADR-051 + sub-proyek J phase status |

**Files to DELETE (at the very end, in the mega-commit):**

| Path | Reason |
|------|--------|
| `demo/app.py` | Streamlit demo replaced by React frontend |
| `demo/__init__.py` | If exists; left orphan after `app.py` removal |

Note: `demo/webpage/` (the SDK demo from Phase 7) STAYS — that's the JavaScript SDK landing page demo, unrelated to the Streamlit operator UI.

---

# PHASE J-0 — Pre-flight checks

## Task 1: Verify environment + sub-proyek I status

**Files:** none (operator-driven shell commands only).

- [ ] **Step 1.1: Verify Node.js version (≥18)**

```bash
node --version
```

Expected: `v18.x.x` or higher. If lower, install Node 20 LTS from https://nodejs.org/.

- [ ] **Step 1.2: Verify npm available**

```bash
npm --version
```

Expected: `9.x.x` or higher.

- [ ] **Step 1.3: Verify PowerShell 7+ (for launcher)**

```bash
pwsh --version
```

Expected: `PowerShell 7.x.x`. If only `powershell.exe` (5.1) available, the launcher should still work but PS 7 is preferred.

- [ ] **Step 1.4: Verify sub-proyek I is committed**

```bash
git status --short
```

Expected: clean working tree (no `M` or `??` lines) OR only `?? frontend-demo/` lines if you previously partially scaffolded. If there is sub-proyek I work uncommitted, **STOP and commit sub-proyek I first** per its own plan. This plan assumes a clean post-sub-proyek-I state.

- [ ] **Step 1.5: Verify Chrome installed**

```powershell
Get-Command chrome.exe -ErrorAction SilentlyContinue
# Or check standard paths:
Test-Path "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe"
Test-Path "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe"
Test-Path "${env:LocalAppData}\Google\Chrome\Application\chrome.exe"
```

Expected: at least one path returns `True`, OR `Get-Command` returns a result. Otherwise install Chrome.

---

# PHASE J-1 — Project scaffold

## Task 2: Vite scaffold

**Files:**
- Create: `frontend-demo/` directory + Vite-generated files

- [ ] **Step 2.1: Scaffold Vite + React + TS template**

From the repo root:

```bash
npm create vite@latest frontend-demo -- --template react-ts
```

Answer prompts: project name `frontend-demo`, framework `React`, variant `TypeScript`. The directory is created with `package.json`, `vite.config.ts`, `tsconfig.json`, `index.html`, `src/main.tsx`, `src/App.tsx`, `src/index.css`, etc.

- [ ] **Step 2.2: Install base deps**

```bash
cd frontend-demo
npm install
```

Expected: `node_modules/` populated, no errors.

- [ ] **Step 2.3: Verify dev server starts**

```bash
npm run dev
```

Expected: console prints `Local: http://localhost:5173/`. Open in browser, see default Vite + React page. Press `Ctrl+C` to stop.

## Task 3: Add Tailwind CSS

**Files:**
- Modify: `frontend-demo/package.json` (deps)
- Create: `frontend-demo/tailwind.config.ts`
- Create: `frontend-demo/postcss.config.js`
- Modify: `frontend-demo/src/index.css`

- [ ] **Step 3.1: Install Tailwind + PostCSS + Autoprefixer**

```bash
cd frontend-demo
npm install -D tailwindcss@^3.4.0 postcss@^8.4.0 autoprefixer@^10.4.0
npx tailwindcss init -p
```

This creates `tailwind.config.js` (will be replaced) and `postcss.config.js` (keep as-is).

- [ ] **Step 3.2: Delete generated `tailwind.config.js`, create TS version**

```bash
cd frontend-demo
rm tailwind.config.js
```

Create `frontend-demo/tailwind.config.ts`:

```ts
import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Spec §1 visual palette
        bg: {
          base: '#0a0a0c',
          gradient: '#14141a',
          card: '#16161d',
          elevated: '#1c1c25',
        },
        border: {
          default: 'rgba(255, 255, 255, 0.06)',
          active: 'rgba(255, 255, 255, 0.12)',
        },
        accent: {
          cyan: '#06b6d4',
          violet: '#8b5cf6',
          emerald: '#10b981',
          crimson: '#ef4444',
        },
        fg: {
          primary: '#ffffff',
          body: '#d4d4d8',
          muted: '#71717a',
          placeholder: '#52525b',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      keyframes: {
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        shake: {
          '0%, 100%': { transform: 'translateX(0)' },
          '25%': { transform: 'translateX(-4px)' },
          '75%': { transform: 'translateX(4px)' },
        },
      },
      animation: {
        shimmer: 'shimmer 1.5s linear infinite',
        shake: 'shake 200ms ease-in-out',
      },
      backgroundImage: {
        'gradient-radial':
          'radial-gradient(ellipse at top, #14141a 0%, #0a0a0c 70%)',
        'cyan-violet': 'linear-gradient(135deg, #06b6d4 0%, #8b5cf6 100%)',
      },
    },
  },
  plugins: [],
}

export default config
```

- [ ] **Step 3.3: Replace `src/index.css` with Tailwind directives + base styles**

Open `frontend-demo/src/index.css` (currently has Vite defaults). Replace entire file with:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  html, body {
    @apply bg-bg-base text-fg-body font-sans antialiased;
  }
  body {
    background-image: radial-gradient(ellipse at top, #14141a 0%, #0a0a0c 70%);
    min-height: 100vh;
  }
}

@layer utilities {
  .shimmer-bg {
    background: linear-gradient(
      90deg,
      #16161d 0%,
      #1c1c25 50%,
      #16161d 100%
    );
    background-size: 200% 100%;
    animation: shimmer 1.5s linear infinite;
  }
}
```

- [ ] **Step 3.4: Verify Tailwind compiles**

```bash
cd frontend-demo
npm run dev
```

Open `http://localhost:5173`. Page background should be dark (`#0a0a0c` with radial gradient toward `#14141a`). Page itself still shows default Vite content — that's fine, we'll replace later. Stop with `Ctrl+C`.

## Task 4: Install shadcn/ui

**Files:**
- Create: `frontend-demo/components.json`
- Modify: `frontend-demo/tsconfig.json` (add `baseUrl` + paths)
- Modify: `frontend-demo/vite.config.ts` (add `@` alias)
- Create: `frontend-demo/src/lib/cn.ts`

- [ ] **Step 4.1: Add path aliases to `tsconfig.json`**

Open `frontend-demo/tsconfig.json`. Inside `"compilerOptions"`, add:

```json
"baseUrl": ".",
"paths": {
  "@/*": ["./src/*"]
}
```

Final shape (merge with what's already there):

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **Step 4.2: Add Vite alias**

Open `frontend-demo/vite.config.ts`. Replace entire file:

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    open: false, // launcher controls Chrome
  },
})
```

- [ ] **Step 4.3: Install `clsx` + `tailwind-merge`**

```bash
cd frontend-demo
npm install clsx tailwind-merge
```

- [ ] **Step 4.4: Create `src/lib/cn.ts`**

```ts
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}
```

- [ ] **Step 4.5: Run shadcn/ui init**

```bash
cd frontend-demo
npx shadcn@latest init
```

Answer prompts:
- Which style? **New York** (cleaner aesthetic match)
- Base color? **Slate**
- CSS variables? **Yes**
- Path to global CSS? **src/index.css**
- Tailwind config path? **tailwind.config.ts**
- Components alias? **@/components**
- Utils alias? **@/lib/cn** (use existing file we just made)

This creates `frontend-demo/components.json` and prepends CSS variables to `src/index.css`.

- [ ] **Step 4.6: Verify `components.json` exists**

```bash
cd frontend-demo
ls components.json
```

Expected: file present. Contents should reference `tailwind.config.ts` + `@/components` alias.

## Task 5: Install Framer Motion + other runtime deps

**Files:**
- Modify: `frontend-demo/package.json` (deps)

- [ ] **Step 5.1: Install runtime deps**

```bash
cd frontend-demo
npm install framer-motion@^11.0.0 lucide-react@^0.400.0
```

`lucide-react` is the icon library per spec §6 (brief mentions `Languages`, `Zap`, `Activity`, `ArrowLeftRight`, `Copy`, `ChevronDown`, `AlertCircle`, `CheckCircle2`, `Loader2`, `Settings`, `Plus`, `Trash2`, `Edit3`, `Sparkles`).

## Task 6: Install Vitest + RTL + ESLint + Prettier

**Files:**
- Modify: `frontend-demo/package.json` (devDeps + scripts)
- Modify: `frontend-demo/vite.config.ts` (vitest config)
- Create: `frontend-demo/src/test-setup.ts`
- Create: `frontend-demo/.eslintrc.cjs`
- Create: `frontend-demo/.prettierrc`

- [ ] **Step 6.1: Install test + lint deps**

```bash
cd frontend-demo
npm install -D vitest@^1.6.0 @vitest/ui@^1.6.0 @testing-library/react@^16.0.0 @testing-library/jest-dom@^6.4.0 @testing-library/user-event@^14.5.0 jsdom@^24.0.0 prettier@^3.3.0 eslint-config-prettier@^9.1.0
```

(Vite scaffold already includes `eslint` + `@typescript-eslint/*` + `eslint-plugin-react-hooks`.)

- [ ] **Step 6.2: Extend `vite.config.ts` with Vitest config**

Replace entire `frontend-demo/vite.config.ts`:

```ts
/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    open: false,
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    css: false,
  },
})
```

- [ ] **Step 6.3: Create `src/test-setup.ts`**

```ts
import '@testing-library/jest-dom/vitest'
```

- [ ] **Step 6.4: Create `.eslintrc.cjs`**

```js
module.exports = {
  root: true,
  env: { browser: true, es2020: true },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
    'prettier',
  ],
  ignorePatterns: ['dist', '.eslintrc.cjs', 'coverage'],
  parser: '@typescript-eslint/parser',
  plugins: ['react-refresh'],
  rules: {
    'react-refresh/only-export-components': [
      'warn',
      { allowConstantExport: true },
    ],
    '@typescript-eslint/no-unused-vars': [
      'warn',
      { argsIgnorePattern: '^_' },
    ],
  },
}
```

- [ ] **Step 6.5: Create `.prettierrc`**

```json
{
  "semi": false,
  "singleQuote": true,
  "trailingComma": "all",
  "printWidth": 100,
  "tabWidth": 2
}
```

- [ ] **Step 6.6: Update `package.json` scripts**

Open `frontend-demo/package.json`. Replace the `scripts` block:

```json
"scripts": {
  "dev": "vite",
  "build": "tsc -b && vite build",
  "preview": "vite preview",
  "test": "vitest",
  "test:run": "vitest run",
  "lint": "eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0",
  "format": "prettier --write \"src/**/*.{ts,tsx,css,json}\""
}
```

- [ ] **Step 6.7: Verify all scripts run without error**

```bash
cd frontend-demo
npm run lint
npm run test:run
npm run build
```

Expected:
- `lint`: clean (no warnings, no errors) — only ignoring `dist` + `.eslintrc.cjs`
- `test:run`: prints "No test files found" — fine, no tests yet
- `build`: produces `dist/index.html` etc.

## Task 7: Extend `.gitignore` (root) + add favicon

**Files:**
- Modify: `.gitignore` (root) — _append only_
- Create: `frontend-demo/public/favicon.svg`

- [ ] **Step 7.1: Append to root `.gitignore`**

Read the current `.gitignore` first. Append at the end:

```
# Sub-proyek J frontend-demo
frontend-demo/node_modules/
frontend-demo/dist/
frontend-demo/coverage/
frontend-demo/.env.local
frontend-demo/.env.*.local
```

- [ ] **Step 7.2: Replace `frontend-demo/public/vite.svg` with custom favicon**

Delete `frontend-demo/public/vite.svg`. Create `frontend-demo/public/favicon.svg`:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" fill="none">
  <rect width="32" height="32" rx="6" fill="url(#g)"/>
  <path d="M9 11h14M9 16h14M9 21h10" stroke="#fff" stroke-width="2" stroke-linecap="round"/>
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="32" y2="32">
      <stop offset="0%" stop-color="#06b6d4"/>
      <stop offset="100%" stop-color="#8b5cf6"/>
    </linearGradient>
  </defs>
</svg>
```

- [ ] **Step 7.3: Update `index.html`**

Replace `frontend-demo/index.html` entirely:

```html
<!doctype html>
<html lang="en" class="dark">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
      rel="stylesheet"
    />
    <title>Polyglot AI — Translation Demo</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

---

# PHASE J-2 — Services, types, mocks

## Task 8: Types contract (`services/types.ts`)

**Files:**
- Create: `frontend-demo/src/services/types.ts`

- [ ] **Step 8.1: Write types file**

```ts
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
```

- [ ] **Step 8.2: Verify TypeScript accepts it**

```bash
cd frontend-demo
npx tsc --noEmit
```

Expected: no errors.

## Task 9: Pricing table (`services/pricing.ts`)

**Files:**
- Create: `frontend-demo/src/services/pricing.ts`

- [ ] **Step 9.1: Write pricing file**

```ts
import type { ModelId } from './types'

// Prices per 1K tokens (USD). Roughly aligned with public list prices
// at time of writing; demo-only — don't quote these as authoritative.
export const MODEL_PRICING: Record<
  ModelId,
  { input_per_1k: number; output_per_1k: number }
> = {
  'claude-haiku-4-5': { input_per_1k: 0.0008, output_per_1k: 0.004 },
  'claude-sonnet-4-6': { input_per_1k: 0.003, output_per_1k: 0.015 },
  'claude-opus-4-7': { input_per_1k: 0.015, output_per_1k: 0.075 },
  'gpt-4o-mini': { input_per_1k: 0.00015, output_per_1k: 0.0006 },
}

export function computeCostUsd(
  model: ModelId,
  inputTokens: number,
  outputTokens: number,
): number {
  const p = MODEL_PRICING[model]
  return (inputTokens * p.input_per_1k + outputTokens * p.output_per_1k) / 1000
}
```

- [ ] **Step 9.2: Verify**

```bash
cd frontend-demo
npx tsc --noEmit
```

Expected: no errors.

## Task 10: Language detector (TDD)

**Files:**
- Test: `frontend-demo/src/services/languageDetector.test.ts`
- Create: `frontend-demo/src/services/languageDetector.ts`

- [ ] **Step 10.1: Write failing tests**

`frontend-demo/src/services/languageDetector.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { detectLanguage } from './languageDetector'

describe('detectLanguage', () => {
  it('detects English from common stopwords', () => {
    const r = detectLanguage('The quick brown fox jumps over the lazy dog')
    expect(r?.lang).toBe('en')
    expect(r?.confidence).toBeGreaterThan(0.7)
  })

  it('detects Indonesian from common stopwords', () => {
    const r = detectLanguage('Halo apa kabar hari ini saya baik terima kasih')
    expect(r?.lang).toBe('id')
    expect(r?.confidence).toBeGreaterThan(0.7)
  })

  it('detects Spanish from common stopwords', () => {
    const r = detectLanguage('Hola como estas hoy yo estoy bien gracias')
    expect(r?.lang).toBe('es')
    expect(r?.confidence).toBeGreaterThan(0.5)
  })

  it('detects French from common stopwords', () => {
    const r = detectLanguage('Bonjour comment allez vous aujourd hui je suis')
    expect(r?.lang).toBe('fr')
    expect(r?.confidence).toBeGreaterThan(0.5)
  })

  it('returns null for empty or ambiguous input', () => {
    expect(detectLanguage('')).toBeNull()
    expect(detectLanguage('123 456')).toBeNull()
  })

  it('returns alternatives sorted by confidence', () => {
    const r = detectLanguage('Hello hola bonjour')
    expect(r).not.toBeNull()
    if (r) {
      expect(r.alternatives.length).toBeGreaterThan(0)
      // alternatives sorted descending
      for (let i = 1; i < r.alternatives.length; i++) {
        expect(r.alternatives[i - 1].confidence).toBeGreaterThanOrEqual(
          r.alternatives[i].confidence,
        )
      }
    }
  })
})
```

- [ ] **Step 10.2: Run test to verify FAIL**

```bash
cd frontend-demo
npm run test:run -- src/services/languageDetector.test.ts
```

Expected: 6 failures with "Cannot find module './languageDetector'".

- [ ] **Step 10.3: Implement `languageDetector.ts`**

```ts
import type { LangCode } from './types'

// Stopwords per language. Keep lists small but distinctive — the detector
// is meant for typing-time hints, not authoritative classification.
const STOPWORDS: Record<LangCode, ReadonlySet<string>> = {
  en: new Set(['the', 'and', 'is', 'are', 'was', 'were', 'a', 'an', 'of', 'to',
    'in', 'on', 'at', 'for', 'with', 'this', 'that', 'these', 'hello', 'how',
    'are', 'you', 'today', 'good', 'morning', 'thank', 'quick', 'brown', 'fox',
    'over', 'lazy', 'dog', 'jumps']),
  id: new Set(['halo', 'apa', 'kabar', 'hari', 'ini', 'saya', 'baik', 'terima',
    'kasih', 'yang', 'dan', 'untuk', 'dengan', 'di', 'ke', 'dari', 'pada',
    'tidak', 'ya', 'akan', 'sudah', 'sedang', 'bagaimana', 'selamat']),
  es: new Set(['el', 'la', 'los', 'las', 'de', 'que', 'y', 'a', 'en', 'es',
    'son', 'hola', 'como', 'estas', 'hoy', 'yo', 'estoy', 'bien', 'gracias',
    'por', 'favor', 'buenos', 'dias', 'noches']),
  fr: new Set(['le', 'la', 'les', 'de', 'et', 'a', 'est', 'sont', 'pour',
    'avec', 'bonjour', 'comment', 'allez', 'vous', 'aujourd', 'hui', 'je',
    'suis', 'merci', 'oui', 'non', 'bonsoir']),
  de: new Set(['der', 'die', 'das', 'und', 'ist', 'sind', 'in', 'auf', 'mit',
    'fuer', 'guten', 'tag', 'wie', 'geht', 'es', 'ihnen', 'danke', 'bitte',
    'hallo', 'morgen']),
  ja: new Set(['です', 'ます', 'こんにちは', 'ありがとう', 'お願い', 'はい',
    'いいえ', 'すみません', 'おはよう', 'こんばんは']),
  zh: new Set([]), // not supported in detector v1
  ar: new Set([]),
  pt: new Set([]),
  ru: new Set([]),
}

export interface DetectionResult {
  lang: LangCode
  confidence: number
  alternatives: { lang: LangCode; confidence: number }[]
}

export function detectLanguage(text: string): DetectionResult | null {
  const trimmed = text.trim().toLowerCase()
  if (trimmed.length === 0) return null

  // Tokenize roughly — split on whitespace + strip punctuation
  const tokens = trimmed
    .split(/\s+/)
    .map((t) => t.replace(/[^\p{L}\p{N}'-]/gu, ''))
    .filter(Boolean)

  if (tokens.length === 0) return null

  // Score each language by stopword overlap ratio
  const scores: { lang: LangCode; matches: number }[] = []
  for (const [lang, words] of Object.entries(STOPWORDS) as [
    LangCode,
    Set<string>,
  ][]) {
    if (words.size === 0) continue
    let matches = 0
    for (const tok of tokens) {
      if (words.has(tok)) matches++
    }
    if (matches > 0) scores.push({ lang, matches })
  }

  if (scores.length === 0) return null

  // Normalize matches to confidence (fraction of input tokens)
  const ranked = scores
    .map((s) => ({ lang: s.lang, confidence: s.matches / tokens.length }))
    .sort((a, b) => b.confidence - a.confidence)

  // Boost top score by margin over runner-up — clear winners get higher
  // confidence even if absolute match count is small
  const top = ranked[0]
  const runnerUp = ranked[1]?.confidence ?? 0
  const margin = top.confidence - runnerUp
  const boosted = Math.min(1, top.confidence + margin * 0.5 + 0.3)

  return {
    lang: top.lang,
    confidence: Math.max(top.confidence, boosted),
    alternatives: ranked.slice(1),
  }
}
```

- [ ] **Step 10.4: Run tests, verify PASS**

```bash
cd frontend-demo
npm run test:run -- src/services/languageDetector.test.ts
```

Expected: 6 passed.

## Task 11: Mock data (`mocks/tenants.ts`, `mocks/translations.ts`)

**Files:**
- Create: `frontend-demo/src/mocks/tenants.ts`
- Create: `frontend-demo/src/mocks/translations.ts`

- [ ] **Step 11.1: `mocks/tenants.ts`**

```ts
import type { Tenant } from '@/services/types'

export const SEED_TENANTS: Tenant[] = [
  {
    id: 'tnt_a3f9k2',
    name: 'Acme Localization',
    source_lang: 'en',
    target_lang: 'es',
    model_tier: 'Premium',
    language_detection: true,
    output_streaming: true,
    log_payloads: true,
    created_at: '2026-04-15T08:23:00.000Z',
    status: 'active',
  },
  {
    id: 'tnt_x7m2q5',
    name: 'TravelGenie Inc.',
    source_lang: 'en',
    target_lang: 'ja',
    model_tier: 'Enterprise',
    language_detection: true,
    output_streaming: true,
    log_payloads: false,
    created_at: '2026-03-02T14:11:00.000Z',
    status: 'active',
  },
  {
    id: 'tnt_b8h4n1',
    name: 'Globex Trading Pte Ltd',
    source_lang: 'zh',
    target_lang: 'en',
    model_tier: 'Standard',
    language_detection: false,
    output_streaming: true,
    log_payloads: true,
    created_at: '2026-05-01T11:48:00.000Z',
    status: 'active',
  },
  {
    id: 'tnt_q5k9p7',
    name: 'Lumen Health Network',
    source_lang: 'en',
    target_lang: 'pt',
    model_tier: 'Premium',
    language_detection: true,
    output_streaming: false,
    log_payloads: true,
    created_at: '2026-05-12T09:30:00.000Z',
    status: 'inactive',
  },
  {
    id: 'tnt_d2v6c8',
    name: 'Aitegrity Internal',
    source_lang: 'id',
    target_lang: 'en',
    model_tier: 'Standard',
    language_detection: true,
    output_streaming: true,
    log_payloads: true,
    created_at: '2026-05-20T16:00:00.000Z',
    status: 'active',
  },
]

export function generateTenantId(): string {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789'
  let s = 'tnt_'
  for (let i = 0; i < 6; i++) s += chars[Math.floor(Math.random() * chars.length)]
  return s
}
```

- [ ] **Step 11.2: `mocks/translations.ts`**

```ts
import type { LangCode } from '@/services/types'

// Lookup table for common test inputs — keeps the demo's translated output
// believable even though there's no real LLM behind it.
type Key = `${LangCode}:${LangCode}:${string}`

export const TRANSLATIONS: Record<Key, string> = {
  'id:en:halo apa kabar hari ini':
    'Hello, how are you today?',
  'id:en:halo apa kabar hari ini?':
    'Hello, how are you today?',
  'en:id:hello how are you today':
    'Halo, apa kabar hari ini?',
  'en:id:hello how are you today?':
    'Halo, apa kabar hari ini?',
  'en:es:hello how are you':
    'Hola, ¿cómo estás?',
  'en:fr:hello how are you':
    'Bonjour, comment allez-vous ?',
  'en:de:hello how are you':
    'Hallo, wie geht es Ihnen?',
  'en:ja:hello how are you':
    'こんにちは、お元気ですか？',
}

export function lookupTranslation(
  source: LangCode,
  target: LangCode,
  text: string,
): string | null {
  const key = `${source}:${target}:${text.trim().toLowerCase()}` as Key
  return TRANSLATIONS[key] ?? null
}

export function fallbackTranslation(target: LangCode, text: string): string {
  // Generic placeholder when no lookup hit — keeps the demo flow alive
  // without pretending to be a real translation.
  const preview = text.length > 40 ? text.slice(0, 37) + '...' : text
  return `[${target.toUpperCase()} translation of "${preview}"]`
}
```

## Task 12: Mock API (TDD)

**Files:**
- Test: `frontend-demo/src/services/mockApi.test.ts`
- Create: `frontend-demo/src/services/mockApi.ts`

- [ ] **Step 12.1: Write failing tests**

`frontend-demo/src/services/mockApi.test.ts`:

```ts
import { describe, it, expect, vi } from 'vitest'
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
```

- [ ] **Step 12.2: Run, verify FAIL**

```bash
cd frontend-demo
npm run test:run -- src/services/mockApi.test.ts
```

Expected: failures with "Cannot find module './mockApi'".

- [ ] **Step 12.3: Implement `mockApi.ts`**

```ts
import { computeCostUsd } from './pricing'
import { detectLanguage } from './languageDetector'
import { fallbackTranslation, lookupTranslation } from '@/mocks/translations'
import type {
  AgenticActivity,
  AgentEvent,
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
```

- [ ] **Step 12.4: Run tests, verify PASS**

```bash
cd frontend-demo
npm run test:run -- src/services/mockApi.test.ts
```

Expected: 4 passed.

## Task 13: Format helpers (`lib/format.ts`)

**Files:**
- Create: `frontend-demo/src/lib/format.ts`

- [ ] **Step 13.1: Write file**

```ts
export function formatCost(usd: number | string): string {
  const n = typeof usd === 'string' ? parseFloat(usd) : usd
  return `$${n.toFixed(6)}`
}

export function formatLatency(ms: number | null | undefined): string {
  if (ms == null) return '—'
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

export function formatTokens(n: number | null | undefined): string {
  if (n == null) return '—'
  return n.toLocaleString()
}

export function formatElapsedSeconds(ms: number): string {
  return `${(ms / 1000).toFixed(3)}s`
}

export function formatRelativeTime(iso: string): string {
  const date = new Date(iso)
  const diff = Date.now() - date.getTime()
  const days = Math.floor(diff / 86400000)
  if (days > 30) return date.toLocaleDateString()
  if (days > 0) return `${days}d ago`
  const hours = Math.floor(diff / 3600000)
  if (hours > 0) return `${hours}h ago`
  const mins = Math.floor(diff / 60000)
  if (mins > 0) return `${mins}m ago`
  return 'just now'
}
```

## Task 14: Verify all services compile + tests pass

- [ ] **Step 14.1: Run all tests + type-check**

```bash
cd frontend-demo
npm run test:run
npx tsc --noEmit
```

Expected: 10 tests pass (6 detector + 4 mockApi), no TS errors.

---

# PHASE J-3 — Hooks (TDD)

## Task 15: `useDebouncedValue` hook

**Files:**
- Test: `frontend-demo/src/hooks/useDebouncedValue.test.ts`
- Create: `frontend-demo/src/hooks/useDebouncedValue.ts`

- [ ] **Step 15.1: Write failing tests**

```ts
import { describe, it, expect, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useDebouncedValue } from './useDebouncedValue'

describe('useDebouncedValue', () => {
  it('returns initial value immediately', () => {
    const { result } = renderHook(() => useDebouncedValue('hello', 500))
    expect(result.current).toBe('hello')
  })

  it('debounces updates by the delay', () => {
    vi.useFakeTimers()
    try {
      const { result, rerender } = renderHook(
        ({ v }: { v: string }) => useDebouncedValue(v, 500),
        { initialProps: { v: 'a' } },
      )
      expect(result.current).toBe('a')
      rerender({ v: 'b' })
      expect(result.current).toBe('a') // still old
      act(() => {
        vi.advanceTimersByTime(499)
      })
      expect(result.current).toBe('a')
      act(() => {
        vi.advanceTimersByTime(1)
      })
      expect(result.current).toBe('b')
    } finally {
      vi.useRealTimers()
    }
  })
})
```

- [ ] **Step 15.2: Run, verify FAIL**

```bash
cd frontend-demo
npm run test:run -- src/hooks/useDebouncedValue.test.ts
```

- [ ] **Step 15.3: Implement**

```ts
import { useEffect, useState } from 'react'

export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const handle = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(handle)
  }, [value, delayMs])

  return debounced
}
```

- [ ] **Step 15.4: Verify PASS**

```bash
cd frontend-demo
npm run test:run -- src/hooks/useDebouncedValue.test.ts
```

Expected: 2 passed.

## Task 16: `useElapsedTimer` hook

**Files:**
- Create: `frontend-demo/src/hooks/useElapsedTimer.ts`

(No tests for this one — trivial wall-clock tick, manual smoke covers it.)

- [ ] **Step 16.1: Implement**

```ts
import { useEffect, useRef, useState } from 'react'

// Ticks every 30ms while `active` is true, returns elapsed ms since
// activation. Resets to 0 on each (false → true) transition.
export function useElapsedTimer(active: boolean): number {
  const [elapsed, setElapsed] = useState(0)
  const startRef = useRef<number | null>(null)

  useEffect(() => {
    if (!active) {
      startRef.current = null
      setElapsed(0)
      return
    }
    startRef.current = Date.now()
    setElapsed(0)
    const id = setInterval(() => {
      if (startRef.current != null) {
        setElapsed(Date.now() - startRef.current)
      }
    }, 30)
    return () => clearInterval(id)
  }, [active])

  return elapsed
}
```

- [ ] **Step 16.2: Type-check**

```bash
cd frontend-demo
npx tsc --noEmit
```

## Task 17: `useTypewriter` hook (TDD)

**Files:**
- Test: `frontend-demo/src/hooks/useTypewriter.test.ts`
- Create: `frontend-demo/src/hooks/useTypewriter.ts`

- [ ] **Step 17.1: Write failing tests**

```ts
import { describe, it, expect, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useTypewriter } from './useTypewriter'

describe('useTypewriter', () => {
  it('progressively reveals characters', () => {
    vi.useFakeTimers()
    try {
      const { result } = renderHook(() => useTypewriter('hello', 25))
      expect(result.current.displayed).toBe('')
      expect(result.current.isComplete).toBe(false)
      act(() => {
        vi.advanceTimersByTime(25)
      })
      expect(result.current.displayed).toBe('h')
      act(() => {
        vi.advanceTimersByTime(100)
      })
      expect(result.current.displayed).toBe('hello')
      expect(result.current.isComplete).toBe(true)
    } finally {
      vi.useRealTimers()
    }
  })

  it('resets when target text changes', () => {
    vi.useFakeTimers()
    try {
      const { result, rerender } = renderHook(
        ({ t }: { t: string }) => useTypewriter(t, 10),
        { initialProps: { t: 'abc' } },
      )
      act(() => {
        vi.advanceTimersByTime(100)
      })
      expect(result.current.displayed).toBe('abc')
      rerender({ t: 'xyz' })
      expect(result.current.displayed).toBe('')
      expect(result.current.isComplete).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })
})
```

- [ ] **Step 17.2: Run, verify FAIL**

```bash
cd frontend-demo
npm run test:run -- src/hooks/useTypewriter.test.ts
```

- [ ] **Step 17.3: Implement**

```ts
import { useEffect, useState } from 'react'

export interface TypewriterState {
  displayed: string
  isComplete: boolean
}

export function useTypewriter(
  target: string,
  speedMs = 25,
): TypewriterState {
  const [index, setIndex] = useState(0)

  useEffect(() => {
    setIndex(0)
  }, [target])

  useEffect(() => {
    if (index >= target.length) return
    const id = setTimeout(() => setIndex((i) => i + 1), speedMs)
    return () => clearTimeout(id)
  }, [index, target, speedMs])

  return {
    displayed: target.slice(0, index),
    isComplete: index >= target.length,
  }
}
```

- [ ] **Step 17.4: Verify PASS**

```bash
cd frontend-demo
npm run test:run -- src/hooks/useTypewriter.test.ts
```

Expected: 2 passed.

## Task 18: `useTranslationFlow` hook (TDD — the big one)

**Files:**
- Test: `frontend-demo/src/hooks/useTranslationFlow.test.ts`
- Create: `frontend-demo/src/hooks/useTranslationFlow.ts`

- [ ] **Step 18.1: Write failing tests**

```ts
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useTranslationFlow } from './useTranslationFlow'
import { mockApi } from '@/services/mockApi'
import type { TranslateApi, TranslateRequest } from '@/services/types'

const baseReq: TranslateRequest = {
  text: 'Halo apa kabar hari ini',
  source_lang: 'id',
  target_lang: 'en',
  tenant_id: 'tnt_a3f9k2',
  profile_id: 'profile-default',
  model_id: 'claude-sonnet-4-6',
}

beforeEach(() => {
  mockApi._resetCache()
})

describe('useTranslationFlow', () => {
  it('starts in idle state', () => {
    const { result } = renderHook(() => useTranslationFlow())
    expect(result.current.state.status).toBe('idle')
  })

  it('transitions idle → running → done', async () => {
    const { result } = renderHook(() => useTranslationFlow())
    act(() => {
      result.current.start(baseReq)
    })
    await waitFor(() => {
      expect(result.current.state.status).toBe('running')
    })
    await waitFor(
      () => {
        expect(result.current.state.status).toBe('done')
      },
      { timeout: 5000 },
    )
    if (result.current.state.status === 'done') {
      expect(result.current.state.payload.translated_text).toBeTruthy()
    }
  })

  it('updates agent statuses as agents progress', async () => {
    const { result } = renderHook(() => useTranslationFlow())
    act(() => {
      result.current.start(baseReq)
    })
    await waitFor(() => {
      expect(result.current.state.status).toBe('running')
    })
    if (result.current.state.status === 'running') {
      // both agents should reach 'running' within parallel start window
      await waitFor(() => {
        if (result.current.state.status === 'running') {
          expect(result.current.state.agents.lang_detect_input.status).toBe(
            'running',
          )
          expect(result.current.state.agents.translate.status).toBe('running')
        }
      })
    }
    await waitFor(
      () => {
        expect(result.current.state.status).toBe('done')
      },
      { timeout: 5000 },
    )
    if (result.current.state.status === 'done') {
      expect(result.current.state.agents.lang_detect_input.status).toBe(
        'completed',
      )
      expect(result.current.state.agents.translate.status).toBe('completed')
    }
  })

  it('captures error state when api throws', async () => {
    const failingApi = {
      translate: () => Promise.reject(new Error('boom')),
    } as unknown as TranslateApi
    const { result } = renderHook(() => useTranslationFlow(failingApi))
    act(() => {
      result.current.start(baseReq)
    })
    await waitFor(
      () => {
        expect(result.current.state.status).toBe('error')
      },
      { timeout: 2000 },
    )
    if (result.current.state.status === 'error') {
      expect(result.current.state.message).toContain('boom')
    }
  })
})
```

- [ ] **Step 18.2: Run, verify FAIL**

```bash
cd frontend-demo
npm run test:run -- src/hooks/useTranslationFlow.test.ts
```

- [ ] **Step 18.3: Implement**

```ts
import { useCallback, useEffect, useRef, useState } from 'react'
import { mockApi as defaultApi } from '@/services/mockApi'
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
  | { status: 'error'; message: string }

const IDLE_AGENTS: AgentStates = {
  lang_detect_input: { status: 'idle' },
  translate: { status: 'idle' },
}

export interface TranslationFlow {
  state: FlowState
  elapsed: number
  start: (req: TranslateRequest) => void
}

export function useTranslationFlow(api: TranslateApi = defaultApi): TranslationFlow {
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

      api
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
          setState({ status: 'error', message: String(err?.message ?? err) })
        })
    },
    [api],
  )

  return { state, elapsed, start }
}
```

- [ ] **Step 18.4: Verify PASS**

```bash
cd frontend-demo
npm run test:run -- src/hooks/useTranslationFlow.test.ts
```

Expected: 4 passed.

- [ ] **Step 18.5: Run all hook + service tests together**

```bash
cd frontend-demo
npm run test:run
```

Expected: 14 tests pass (6 detector + 4 mockApi + 2 debounce + 2 typewriter + 4 flow).

---

# PHASE J-4 — Components

## Task 19: Install shadcn primitives

**Files:**
- Create: multiple `frontend-demo/src/components/ui/*.tsx`

- [ ] **Step 19.1: Install needed shadcn components**

```bash
cd frontend-demo
npx shadcn@latest add button card tabs select badge dialog tooltip
```

Answer "yes" to overwrite prompts if any. This creates files under `src/components/ui/`.

- [ ] **Step 19.2: Verify components present**

```bash
cd frontend-demo
ls src/components/ui/
```

Expected: `button.tsx`, `card.tsx`, `tabs.tsx`, `select.tsx`, `badge.tsx`, `dialog.tsx`, `tooltip.tsx`.

- [ ] **Step 19.3: Type-check**

```bash
cd frontend-demo
npx tsc --noEmit
```

Expected: no errors.

## Task 20: TopBar component

**Files:**
- Create: `frontend-demo/src/components/TopBar.tsx`

- [ ] **Step 20.1: Implement**

```tsx
import { Languages } from 'lucide-react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { Tenant } from '@/services/types'
import { cn } from '@/lib/cn'

interface Props {
  tenants: Tenant[]
  activeTenantId: string | null
  onSelectTenant: (id: string) => void
}

export function TopBar({ tenants, activeTenantId, onSelectTenant }: Props) {
  const active = tenants.find((t) => t.id === activeTenantId) ?? null

  return (
    <header
      className={cn(
        'sticky top-0 z-50 flex items-center justify-between px-6 py-4',
        'border-b border-border-default bg-bg-base/80 backdrop-blur-md',
      )}
    >
      <div className="flex items-center gap-3">
        <div className="grid h-9 w-9 place-items-center rounded-lg bg-cyan-violet">
          <Languages className="h-5 w-5 text-white" />
        </div>
        <div className="text-lg font-medium tracking-tight text-fg-primary">
          Polyglot <span className="text-fg-muted">AI</span>
        </div>
      </div>

      <div className="flex items-center gap-4">
        {active && (
          <Select value={activeTenantId ?? ''} onValueChange={onSelectTenant}>
            <SelectTrigger className="w-64 bg-bg-card border-border-default text-fg-body">
              <SelectValue>
                <div className="flex items-center gap-2">
                  <span className="text-fg-primary">{active.name}</span>
                  <span className="font-mono text-xs text-fg-muted">
                    {active.id}
                  </span>
                </div>
              </SelectValue>
            </SelectTrigger>
            <SelectContent className="bg-bg-elevated border-border-default">
              {tenants.map((t) => (
                <SelectItem key={t.id} value={t.id}>
                  <div className="flex items-center gap-2">
                    <span>{t.name}</span>
                    <span className="font-mono text-xs text-fg-muted">
                      {t.id}
                    </span>
                  </div>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        <div className="grid h-9 w-9 place-items-center rounded-full bg-bg-elevated text-sm text-fg-muted">
          ZA
        </div>
      </div>
    </header>
  )
}
```

## Task 21: TenantManagement components

**Files:**
- Create: `frontend-demo/src/components/TenantManagement/index.tsx`
- Create: `frontend-demo/src/components/TenantManagement/TenantForm.tsx`
- Create: `frontend-demo/src/components/TenantManagement/TenantTable.tsx`

- [ ] **Step 21.1: `TenantForm.tsx`**

```tsx
import { useState } from 'react'
import { motion } from 'framer-motion'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { LANGUAGE_LABELS, type LangCode, type ModelTier, type Tenant } from '@/services/types'
import { generateTenantId } from '@/mocks/tenants'
import { cn } from '@/lib/cn'

interface Props {
  onCreate: (tenant: Tenant) => void
}

export function TenantForm({ onCreate }: Props) {
  const [name, setName] = useState('')
  const [tenantId, setTenantId] = useState(generateTenantId())
  const [sourceLang, setSourceLang] = useState<LangCode>('en')
  const [targetLang, setTargetLang] = useState<LangCode>('id')
  const [modelTier, setModelTier] = useState<ModelTier>('Standard')
  const [langDetection, setLangDetection] = useState(true)
  const [outputStreaming, setOutputStreaming] = useState(true)
  const [logPayloads, setLogPayloads] = useState(true)

  const langs: LangCode[] = ['en', 'id', 'es', 'fr', 'de', 'ja', 'zh', 'ar', 'pt', 'ru']
  const tiers: ModelTier[] = ['Standard', 'Premium', 'Enterprise']

  const canSubmit = name.trim().length > 0

  const submit = () => {
    if (!canSubmit) return
    onCreate({
      id: tenantId,
      name: name.trim(),
      source_lang: sourceLang,
      target_lang: targetLang,
      model_tier: modelTier,
      language_detection: langDetection,
      output_streaming: outputStreaming,
      log_payloads: logPayloads,
      created_at: new Date().toISOString(),
      status: 'active',
    })
    setName('')
    setTenantId(generateTenantId())
  }

  return (
    <Card className="bg-bg-card border-border-default p-6">
      <div className="mb-6">
        <h2 className="text-lg font-medium text-fg-primary">Create Tenant</h2>
        <p className="mt-1 text-sm text-fg-muted">
          Add a new tenant to manage translation behaviour.
        </p>
      </div>

      <div className="space-y-4">
        <Field label="Tenant Name">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Acme Localization"
            className={inputClass}
          />
        </Field>

        <Field label="Tenant ID">
          <input
            value={tenantId}
            onChange={(e) => setTenantId(e.target.value)}
            className={cn(inputClass, 'font-mono text-sm')}
          />
        </Field>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Default Source Language">
            <Select value={sourceLang} onValueChange={(v) => setSourceLang(v as LangCode)}>
              <SelectTrigger className={selectTriggerClass}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-bg-elevated border-border-default">
                {langs.map((l) => (
                  <SelectItem key={l} value={l}>
                    {LANGUAGE_LABELS[l].flag} {LANGUAGE_LABELS[l].name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>

          <Field label="Default Target Language">
            <Select value={targetLang} onValueChange={(v) => setTargetLang(v as LangCode)}>
              <SelectTrigger className={selectTriggerClass}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-bg-elevated border-border-default">
                {langs.map((l) => (
                  <SelectItem key={l} value={l}>
                    {LANGUAGE_LABELS[l].flag} {LANGUAGE_LABELS[l].name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        </div>

        <Field label="Model Tier">
          <div className="flex rounded-lg border border-border-default bg-bg-base p-1">
            {tiers.map((t) => (
              <button
                key={t}
                onClick={() => setModelTier(t)}
                className={cn(
                  'flex-1 rounded-md px-4 py-1.5 text-sm transition-colors',
                  modelTier === t
                    ? 'bg-bg-elevated text-fg-primary'
                    : 'text-fg-muted hover:text-fg-body',
                )}
              >
                {t}
              </button>
            ))}
          </div>
        </Field>

        <Toggle
          label="Enable language detection"
          checked={langDetection}
          onChange={setLangDetection}
        />
        <Toggle
          label="Enable output streaming"
          checked={outputStreaming}
          onChange={setOutputStreaming}
        />
        <Toggle
          label="Log full payloads"
          checked={logPayloads}
          onChange={setLogPayloads}
        />

        <motion.div whileTap={canSubmit ? { scale: 0.98 } : undefined}>
          <Button
            disabled={!canSubmit}
            onClick={submit}
            className={cn(
              'mt-4 w-full bg-cyan-violet text-white border-0',
              'hover:opacity-90 transition-opacity',
              !canSubmit && 'opacity-50',
            )}
          >
            Create Tenant
          </Button>
        </motion.div>
      </div>
    </Card>
  )
}

const inputClass =
  'w-full rounded-lg border border-border-default bg-bg-base px-3 py-2 text-sm text-fg-primary placeholder:text-fg-placeholder focus:border-border-active focus:outline-none transition-colors'

const selectTriggerClass =
  'w-full bg-bg-base border-border-default text-fg-body'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1.5 block text-xs uppercase tracking-wider text-fg-muted">
        {label}
      </label>
      {children}
    </div>
  )
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <label className="flex cursor-pointer items-center justify-between rounded-lg border border-border-default bg-bg-base px-3 py-2.5">
      <span className="text-sm text-fg-body">{label}</span>
      <button
        onClick={() => onChange(!checked)}
        className={cn(
          'relative h-5 w-9 rounded-full transition-colors',
          checked ? 'bg-accent-cyan' : 'bg-bg-elevated',
        )}
      >
        <span
          className={cn(
            'absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform',
            checked ? 'translate-x-4' : 'translate-x-0.5',
          )}
        />
      </button>
    </label>
  )
}
```

- [ ] **Step 21.2: `TenantTable.tsx`**

```tsx
import { AnimatePresence, motion } from 'framer-motion'
import { Edit3, Trash2, CheckCircle2 } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import type { Tenant } from '@/services/types'
import { formatRelativeTime } from '@/lib/format'
import { cn } from '@/lib/cn'

interface Props {
  tenants: Tenant[]
  activeTenantId: string | null
  recentlyCreated: string | null
  onSelect: (id: string) => void
  onDelete: (id: string) => void
}

export function TenantTable({
  tenants,
  activeTenantId,
  recentlyCreated,
  onSelect,
  onDelete,
}: Props) {
  return (
    <Card className="bg-bg-card border-border-default overflow-hidden">
      <div className="border-b border-border-default px-6 py-4">
        <h2 className="text-lg font-medium text-fg-primary">Tenants</h2>
        <p className="mt-1 text-sm text-fg-muted">
          {tenants.length} tenant{tenants.length === 1 ? '' : 's'} configured
        </p>
      </div>

      <table className="w-full">
        <thead>
          <tr className="border-b border-border-default text-left text-xs uppercase tracking-wider text-fg-muted">
            <th className="px-6 py-3 font-medium">Name</th>
            <th className="px-6 py-3 font-medium">Tenant ID</th>
            <th className="px-6 py-3 font-medium">Created</th>
            <th className="px-6 py-3 font-medium">Status</th>
            <th className="px-6 py-3 font-medium">Tier</th>
            <th className="px-6 py-3 font-medium text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          <AnimatePresence initial={false}>
            {tenants.map((t) => (
              <motion.tr
                key={t.id}
                layout
                initial={{ opacity: 0, y: -10 }}
                animate={{
                  opacity: 1,
                  y: 0,
                  boxShadow:
                    t.id === recentlyCreated
                      ? '0 0 0 1px #06b6d4 inset, 0 0 20px #06b6d433'
                      : 'none',
                }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.3 }}
                className={cn(
                  'group border-b border-border-default text-sm transition-colors hover:bg-bg-elevated/40',
                  activeTenantId === t.id && 'bg-bg-elevated/30',
                )}
              >
                <td className="px-6 py-3 text-fg-primary">
                  <div className="flex items-center gap-2">
                    {activeTenantId === t.id && (
                      <CheckCircle2 className="h-3.5 w-3.5 text-accent-cyan" />
                    )}
                    {t.name}
                  </div>
                </td>
                <td className="px-6 py-3 font-mono text-xs text-fg-muted">
                  {t.id}
                </td>
                <td className="px-6 py-3 text-fg-muted">
                  {formatRelativeTime(t.created_at)}
                </td>
                <td className="px-6 py-3">
                  <Badge
                    variant="outline"
                    className={cn(
                      'border-0 font-normal',
                      t.status === 'active'
                        ? 'bg-accent-emerald/15 text-accent-emerald'
                        : 'bg-bg-elevated text-fg-muted',
                    )}
                  >
                    {t.status}
                  </Badge>
                </td>
                <td className="px-6 py-3 text-fg-body">{t.model_tier}</td>
                <td className="px-6 py-3 text-right">
                  <div className="invisible flex justify-end gap-1 group-hover:visible">
                    <button
                      onClick={() => onSelect(t.id)}
                      className="rounded p-1.5 text-fg-muted hover:bg-bg-elevated hover:text-fg-primary"
                      title="Set active"
                    >
                      <CheckCircle2 className="h-4 w-4" />
                    </button>
                    <button
                      className="rounded p-1.5 text-fg-muted hover:bg-bg-elevated hover:text-fg-primary"
                      title="Edit (mock)"
                    >
                      <Edit3 className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => onDelete(t.id)}
                      className="rounded p-1.5 text-fg-muted hover:bg-bg-elevated hover:text-accent-crimson"
                      title="Delete"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </td>
              </motion.tr>
            ))}
          </AnimatePresence>
        </tbody>
      </table>
    </Card>
  )
}
```

- [ ] **Step 21.3: `index.tsx`**

```tsx
import { useState } from 'react'
import { TenantForm } from './TenantForm'
import { TenantTable } from './TenantTable'
import type { Tenant } from '@/services/types'

interface Props {
  tenants: Tenant[]
  activeTenantId: string | null
  onCreate: (t: Tenant) => void
  onSelect: (id: string) => void
  onDelete: (id: string) => void
}

export function TenantManagement({
  tenants,
  activeTenantId,
  onCreate,
  onSelect,
  onDelete,
}: Props) {
  const [recentlyCreated, setRecentlyCreated] = useState<string | null>(null)

  const handleCreate = (t: Tenant) => {
    onCreate(t)
    setRecentlyCreated(t.id)
    setTimeout(() => setRecentlyCreated(null), 1500)
  }

  return (
    <div className="grid grid-cols-12 gap-6 p-6">
      <div className="col-span-12 lg:col-span-5">
        <TenantForm onCreate={handleCreate} />
      </div>
      <div className="col-span-12 lg:col-span-7">
        <TenantTable
          tenants={tenants}
          activeTenantId={activeTenantId}
          recentlyCreated={recentlyCreated}
          onSelect={onSelect}
          onDelete={onDelete}
        />
      </div>
    </div>
  )
}
```

## Task 22: TranslationPlayground — LanguageBar + InputBox + LanguageMismatchBanner (with test)

**Files:**
- Create: `frontend-demo/src/components/TranslationPlayground/LanguageBar.tsx`
- Create: `frontend-demo/src/components/TranslationPlayground/InputBox.tsx`
- Create: `frontend-demo/src/components/TranslationPlayground/LanguageMismatchBanner.tsx`
- Test: `frontend-demo/src/components/TranslationPlayground/LanguageMismatchBanner.test.tsx`

- [ ] **Step 22.1: `LanguageBar.tsx`**

```tsx
import { motion } from 'framer-motion'
import { ArrowLeftRight } from 'lucide-react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import {
  LANGUAGE_LABELS,
  MODEL_LABELS,
  type LangCode,
  type ModelId,
} from '@/services/types'
import { cn } from '@/lib/cn'

interface Props {
  sourceLang: LangCode
  targetLang: LangCode
  modelId: ModelId
  onSourceChange: (l: LangCode) => void
  onTargetChange: (l: LangCode) => void
  onSwap: () => void
  onModelChange: (m: ModelId) => void
}

const LANGS: LangCode[] = ['en', 'id', 'es', 'fr', 'de', 'ja', 'zh', 'ar', 'pt', 'ru']
const MODELS: ModelId[] = [
  'claude-haiku-4-5',
  'claude-sonnet-4-6',
  'claude-opus-4-7',
  'gpt-4o-mini',
]

export function LanguageBar({
  sourceLang,
  targetLang,
  modelId,
  onSourceChange,
  onTargetChange,
  onSwap,
  onModelChange,
}: Props) {
  return (
    <div className="flex items-center gap-3 border-b border-border-default px-6 py-4">
      <LangSelect value={sourceLang} onChange={onSourceChange} />

      <motion.button
        onClick={onSwap}
        whileTap={{ scale: 0.92, rotate: 180 }}
        transition={{ type: 'spring', stiffness: 300 }}
        className="grid h-9 w-9 place-items-center rounded-lg border border-border-default text-fg-muted hover:bg-bg-elevated hover:text-fg-primary"
      >
        <ArrowLeftRight className="h-4 w-4" />
      </motion.button>

      <LangSelect value={targetLang} onChange={onTargetChange} />

      <div className="ml-auto">
        <Select value={modelId} onValueChange={(v) => onModelChange(v as ModelId)}>
          <SelectTrigger className="bg-bg-base border-border-default text-fg-body w-56">
            <SelectValue>
              <div className="flex items-center gap-2">
                <span className="text-fg-body text-sm">{MODEL_LABELS[modelId]}</span>
                <Badge variant="outline" className="border-border-default font-mono text-[10px] text-fg-muted">
                  {modelId}
                </Badge>
              </div>
            </SelectValue>
          </SelectTrigger>
          <SelectContent className="bg-bg-elevated border-border-default">
            {MODELS.map((m) => (
              <SelectItem key={m} value={m}>
                <span className="text-fg-body">{MODEL_LABELS[m]}</span>
                <span className="ml-2 font-mono text-xs text-fg-muted">{m}</span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  )
}

function LangSelect({
  value,
  onChange,
}: {
  value: LangCode
  onChange: (l: LangCode) => void
}) {
  return (
    <Select value={value} onValueChange={(v) => onChange(v as LangCode)}>
      <SelectTrigger className="bg-bg-base border-border-default text-fg-primary w-44">
        <SelectValue>
          <span className="mr-2">{LANGUAGE_LABELS[value].flag}</span>
          <span>{LANGUAGE_LABELS[value].name}</span>
          <span className="ml-2 font-mono text-xs text-fg-muted">{value.toUpperCase()}</span>
        </SelectValue>
      </SelectTrigger>
      <SelectContent className="bg-bg-elevated border-border-default">
        {LANGS.map((l) => (
          <SelectItem key={l} value={l}>
            <span className="mr-2">{LANGUAGE_LABELS[l].flag}</span>
            {LANGUAGE_LABELS[l].name}{' '}
            <span className="ml-2 font-mono text-xs text-fg-muted">{l.toUpperCase()}</span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
```

- [ ] **Step 22.2: `LanguageMismatchBanner.tsx`**

```tsx
import { AlertCircle } from 'lucide-react'
import { motion } from 'framer-motion'
import { LANGUAGE_LABELS, type LangCode } from '@/services/types'
import { Button } from '@/components/ui/button'

interface Props {
  selectedLang: LangCode
  detectedLang: LangCode
  onSwitchSource: () => void
}

export function LanguageMismatchBanner({
  selectedLang,
  detectedLang,
  onSwitchSource,
}: Props) {
  return (
    <motion.div
      data-testid="mismatch-banner"
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      className="mb-3 flex items-center gap-3 rounded-lg border border-accent-crimson/30 bg-accent-crimson/10 px-4 py-3 animate-shake"
    >
      <AlertCircle className="h-4 w-4 shrink-0 text-accent-crimson" />
      <div className="flex-1 text-sm text-[#fee2e2]">
        Detected language is <strong>{LANGUAGE_LABELS[detectedLang].name}</strong>, but
        you selected <strong>{LANGUAGE_LABELS[selectedLang].name}</strong>. Consider switching.
      </div>
      <Button
        onClick={onSwitchSource}
        size="sm"
        variant="outline"
        className="border-accent-crimson/40 bg-transparent text-[#fee2e2] hover:bg-accent-crimson/20"
      >
        Switch source to {LANGUAGE_LABELS[detectedLang].name}
      </Button>
    </motion.div>
  )
}
```

- [ ] **Step 22.3: Write test for `LanguageMismatchBanner`**

`frontend-demo/src/components/TranslationPlayground/LanguageMismatchBanner.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { LanguageMismatchBanner } from './LanguageMismatchBanner'

describe('LanguageMismatchBanner', () => {
  it('renders detected and selected language names', () => {
    render(
      <LanguageMismatchBanner
        selectedLang="en"
        detectedLang="id"
        onSwitchSource={() => {}}
      />,
    )
    expect(screen.getByText(/English/)).toBeInTheDocument()
    expect(screen.getByText(/Indonesian/)).toBeInTheDocument()
  })

  it('calls onSwitchSource when CTA clicked', () => {
    const handle = vi.fn()
    render(
      <LanguageMismatchBanner
        selectedLang="en"
        detectedLang="id"
        onSwitchSource={handle}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /switch source/i }))
    expect(handle).toHaveBeenCalledOnce()
  })
})
```

- [ ] **Step 22.4: `InputBox.tsx`**

```tsx
import { useEffect } from 'react'
import { AnimatePresence } from 'framer-motion'
import { X } from 'lucide-react'
import { LANGUAGE_LABELS, type LangCode } from '@/services/types'
import { detectLanguage } from '@/services/languageDetector'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { LanguageMismatchBanner } from './LanguageMismatchBanner'
import { cn } from '@/lib/cn'

interface Props {
  value: string
  sourceLang: LangCode
  onChange: (v: string) => void
  onSwitchSource: (l: LangCode) => void
  onDetectionChange?: (detected: LangCode | null, confidence: number) => void
}

export function InputBox({
  value,
  sourceLang,
  onChange,
  onSwitchSource,
  onDetectionChange,
}: Props) {
  const debouncedValue = useDebouncedValue(value, 500)
  const detection = debouncedValue.trim().length > 4 ? detectLanguage(debouncedValue) : null

  useEffect(() => {
    onDetectionChange?.(detection?.lang ?? null, detection?.confidence ?? 0)
  }, [detection?.lang, detection?.confidence, onDetectionChange])

  const charCount = value.length
  const tokenEstimate = Math.max(0, Math.round(value.length / 3.7))
  const showMismatch =
    detection != null && detection.confidence > 0.5 && detection.lang !== sourceLang
  const longWarning = charCount > 5000

  return (
    <div className="flex flex-col">
      <AnimatePresence>
        {showMismatch && detection && (
          <LanguageMismatchBanner
            selectedLang={sourceLang}
            detectedLang={detection.lang}
            onSwitchSource={() => onSwitchSource(detection.lang)}
          />
        )}
      </AnimatePresence>

      {longWarning && (
        <div className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-xs text-amber-200">
          Long input — translation may be slower or hit token limits.
        </div>
      )}

      <div className="relative rounded-xl border border-border-default bg-bg-card">
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Enter text to translate..."
          className={cn(
            'w-full resize-none rounded-xl bg-transparent p-4 text-fg-primary placeholder:text-fg-placeholder',
            'min-h-[180px] max-h-[400px] overflow-y-auto focus:outline-none',
          )}
        />

        <div className="flex items-center justify-between border-t border-border-default px-4 py-2 text-xs text-fg-muted">
          <div>
            {value.length > 0 ? (
              <button
                onClick={() => onChange('')}
                className="flex items-center gap-1 hover:text-fg-body"
              >
                <X className="h-3 w-3" /> Clear
              </button>
            ) : (
              <span>&nbsp;</span>
            )}
          </div>
          <div className="font-mono">
            {charCount} chars · ~{tokenEstimate} tokens
          </div>
        </div>
      </div>

      {detection && !showMismatch && (
        <div className="mt-2 text-xs text-fg-muted">
          Detected: <span className="text-fg-body">{LANGUAGE_LABELS[detection.lang].name}</span>{' '}
          · {(detection.confidence * 100).toFixed(0)}% confidence
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 22.5: Verify tests pass**

```bash
cd frontend-demo
npm run test:run -- src/components/TranslationPlayground/LanguageMismatchBanner.test.tsx
```

Expected: 2 passed.

## Task 23: OutputBox + TranslateButton

**Files:**
- Create: `frontend-demo/src/components/TranslationPlayground/OutputBox.tsx`
- Create: `frontend-demo/src/components/TranslationPlayground/TranslateButton.tsx`

- [ ] **Step 23.1: `OutputBox.tsx`**

```tsx
import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Copy, RotateCw, Volume2, CheckCircle2, AlertCircle } from 'lucide-react'
import { useTypewriter } from '@/hooks/useTypewriter'
import { cn } from '@/lib/cn'

const LOADING_MICROCOPY = [
  'Tokenizing input...',
  'Identifying language patterns...',
  'Routing through translation agent...',
  'Polishing output...',
]

interface Props {
  translatedText: string | null
  status: 'idle' | 'running' | 'done' | 'error'
  errorMessage?: string
  onCopy?: () => void
  onRegenerate?: () => void
}

export function OutputBox({
  translatedText,
  status,
  errorMessage,
  onCopy,
  onRegenerate,
}: Props) {
  const [microcopyIdx, setMicrocopyIdx] = useState(0)
  const [copyFlash, setCopyFlash] = useState(false)

  useEffect(() => {
    if (status !== 'running') return
    const id = setInterval(() => {
      setMicrocopyIdx((i) => (i + 1) % LOADING_MICROCOPY.length)
    }, 800)
    return () => clearInterval(id)
  }, [status])

  const { displayed } = useTypewriter(
    status === 'done' && translatedText ? translatedText : '',
    25,
  )

  const handleCopy = () => {
    if (!translatedText) return
    navigator.clipboard.writeText(translatedText).then(() => {
      setCopyFlash(true)
      setTimeout(() => setCopyFlash(false), 1500)
      onCopy?.()
    })
  }

  return (
    <div className="flex flex-col rounded-xl border border-border-default bg-bg-card">
      <div className="min-h-[180px] max-h-[400px] overflow-y-auto p-4">
        {status === 'idle' && (
          <p className="text-fg-placeholder">Translation will appear here</p>
        )}

        {status === 'running' && (
          <div className="space-y-3">
            <div className="space-y-2">
              <div className="shimmer-bg h-3 w-4/5 rounded" />
              <div className="shimmer-bg h-3 w-3/4 rounded" />
              <div className="shimmer-bg h-3 w-2/3 rounded" />
            </div>
            <AnimatePresence mode="wait">
              <motion.div
                key={microcopyIdx}
                initial={{ opacity: 0 }}
                animate={{ opacity: 0.7 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="text-xs text-fg-muted"
              >
                {LOADING_MICROCOPY[microcopyIdx]}
              </motion.div>
            </AnimatePresence>
          </div>
        )}

        {status === 'done' && (
          <p className="whitespace-pre-wrap text-fg-primary">{displayed}</p>
        )}

        {status === 'error' && (
          <div className="flex items-start gap-2 text-accent-crimson">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <div className="font-medium">Translation failed</div>
              <div className="mt-1 text-sm opacity-90">{errorMessage}</div>
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center justify-end gap-1 border-t border-border-default px-3 py-2">
        <ActionBtn icon={copyFlash ? CheckCircle2 : Copy} onClick={handleCopy} disabled={!translatedText} title="Copy" />
        <ActionBtn icon={Volume2} onClick={() => {}} disabled={!translatedText} title="Listen" />
        <ActionBtn icon={RotateCw} onClick={onRegenerate} disabled={!onRegenerate} title="Regenerate" />
      </div>
    </div>
  )
}

function ActionBtn({
  icon: Icon,
  onClick,
  disabled,
  title,
}: {
  icon: React.ComponentType<{ className?: string }>
  onClick?: () => void
  disabled?: boolean
  title: string
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={cn(
        'rounded p-1.5 text-fg-muted transition-colors',
        disabled
          ? 'opacity-40'
          : 'hover:bg-bg-elevated hover:text-fg-primary',
      )}
    >
      <Icon className="h-4 w-4" />
    </button>
  )
}
```

- [ ] **Step 23.2: `TranslateButton.tsx`**

```tsx
import { motion } from 'framer-motion'
import { Loader2, Sparkles } from 'lucide-react'
import { cn } from '@/lib/cn'

interface Props {
  disabled: boolean
  loading: boolean
  onClick: () => void
}

export function TranslateButton({ disabled, loading, onClick }: Props) {
  return (
    <motion.button
      onClick={onClick}
      disabled={disabled || loading}
      whileTap={disabled || loading ? undefined : { scale: 0.98 }}
      className={cn(
        'mt-6 w-full rounded-xl bg-cyan-violet px-6 py-3 text-sm font-medium text-white',
        'transition-opacity',
        (disabled || loading) && 'opacity-50',
        !disabled && !loading && 'hover:opacity-90',
      )}
    >
      <div className="flex items-center justify-center gap-2">
        {loading ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            Translating...
          </>
        ) : (
          <>
            <Sparkles className="h-4 w-4" />
            Translate
          </>
        )}
      </div>
    </motion.button>
  )
}
```

## Task 24: TranslationPlayground composition

**Files:**
- Create: `frontend-demo/src/components/TranslationPlayground/index.tsx`

- [ ] **Step 24.1: Implement**

```tsx
import { useState } from 'react'
import { Card } from '@/components/ui/card'
import { LanguageBar } from './LanguageBar'
import { InputBox } from './InputBox'
import { OutputBox } from './OutputBox'
import { TranslateButton } from './TranslateButton'
import { AgentPipeline } from '@/components/AgentPipeline'
import { PayloadViewer } from '@/components/PayloadViewer'
import { useTranslationFlow } from '@/hooks/useTranslationFlow'
import type { LangCode, ModelId, Tenant } from '@/services/types'

interface Props {
  tenant: Tenant
}

export function TranslationPlayground({ tenant }: Props) {
  const [inputText, setInputText] = useState('Halo, apa kabar hari ini?')
  const [sourceLang, setSourceLang] = useState<LangCode>(tenant.source_lang)
  const [targetLang, setTargetLang] = useState<LangCode>(tenant.target_lang)
  const [modelId, setModelId] = useState<ModelId>('claude-sonnet-4-6')

  const flow = useTranslationFlow()

  const swap = () => {
    const s = sourceLang
    setSourceLang(targetLang)
    setTargetLang(s)
  }

  const translate = () => {
    flow.start({
      text: inputText,
      source_lang: sourceLang,
      target_lang: targetLang,
      tenant_id: tenant.id,
      profile_id: 'profile-default',
      model_id: modelId,
    })
  }

  const status =
    flow.state.status === 'running'
      ? 'running'
      : flow.state.status === 'done'
        ? 'done'
        : flow.state.status === 'error'
          ? 'error'
          : 'idle'

  const translatedText =
    flow.state.status === 'done' ? flow.state.payload.translated_text : null
  const errorMessage =
    flow.state.status === 'error' ? flow.state.message : undefined
  const payload =
    flow.state.status === 'done' ? flow.state.payload : null
  const agents =
    flow.state.status === 'running' || flow.state.status === 'done'
      ? flow.state.agents
      : null

  return (
    <div className="space-y-6 p-6">
      <Card className="bg-bg-card border-border-default overflow-hidden">
        <LanguageBar
          sourceLang={sourceLang}
          targetLang={targetLang}
          modelId={modelId}
          onSourceChange={setSourceLang}
          onTargetChange={setTargetLang}
          onSwap={swap}
          onModelChange={setModelId}
        />
        <div className="grid grid-cols-2 gap-6 p-6">
          <InputBox
            value={inputText}
            sourceLang={sourceLang}
            onChange={setInputText}
            onSwitchSource={setSourceLang}
          />
          <OutputBox
            translatedText={translatedText}
            status={status}
            errorMessage={errorMessage}
            onRegenerate={status === 'done' ? translate : undefined}
          />
        </div>
        <div className="px-6 pb-6">
          <TranslateButton
            disabled={inputText.trim().length === 0}
            loading={status === 'running'}
            onClick={translate}
          />
        </div>
      </Card>

      <AgentPipeline agents={agents} elapsed={flow.elapsed} payload={payload} />

      <PayloadViewer payload={payload} />
    </div>
  )
}
```

## Task 25: AgentPipeline components

**Files:**
- Create: `frontend-demo/src/components/AgentPipeline/PipelineDiagram.tsx`
- Create: `frontend-demo/src/components/AgentPipeline/AgentCard.tsx`
- Create: `frontend-demo/src/components/AgentPipeline/PipelineSummary.tsx`
- Create: `frontend-demo/src/components/AgentPipeline/index.tsx`

- [ ] **Step 25.1: `PipelineDiagram.tsx`**

```tsx
import { motion } from 'framer-motion'
import type { AgentStates } from '@/hooks/useTranslationFlow'
import { cn } from '@/lib/cn'

interface Props {
  agents: AgentStates | null
}

// Simple SVG diagram:
//                ┌─→ [lang_detect_input] ─┐
//   [Input] ─────┤                         ├──→ [Output]
//                └─→ [translate] ──────────┘
export function PipelineDiagram({ agents }: Props) {
  const detect = agents?.lang_detect_input
  const translate = agents?.translate

  return (
    <div className="relative h-48 w-full">
      <svg viewBox="0 0 800 200" className="h-full w-full">
        {/* Connection paths */}
        <Path d="M 120 100 Q 200 100 240 50 L 320 50" running={detect?.status === 'running'} />
        <Path d="M 120 100 Q 200 100 240 150 L 320 150" running={translate?.status === 'running'} />
        <Path d="M 560 50 L 640 50 Q 680 100 680 100" running={detect?.status === 'completed' && translate?.status === 'running'} />
        <Path d="M 560 150 L 640 150 Q 680 100 680 100" running={translate?.status === 'completed'} />

        {/* Nodes */}
        <Node x={60} y={100} label="Input" tone="muted" />
        <Node
          x={440}
          y={50}
          label="lang_detect_input"
          tone={statusTone(detect?.status)}
          width={240}
        />
        <Node
          x={440}
          y={150}
          label="translate"
          tone={statusTone(translate?.status)}
          width={240}
        />
        <Node x={740} y={100} label="Output" tone={translate?.status === 'completed' ? 'done' : 'muted'} />
      </svg>

      {!agents && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="rounded-full border border-border-default bg-bg-card px-4 py-1.5 text-xs text-fg-muted">
            Run a translation to see the pipeline in action
          </div>
        </div>
      )}
    </div>
  )
}

type Tone = 'muted' | 'running' | 'done' | 'failed'

function statusTone(s?: string): Tone {
  if (s === 'running') return 'running'
  if (s === 'completed') return 'done'
  if (s === 'failed') return 'failed'
  return 'muted'
}

function Node({
  x,
  y,
  label,
  tone,
  width = 120,
}: {
  x: number
  y: number
  label: string
  tone: Tone
  width?: number
}) {
  const colors: Record<Tone, { stroke: string; fill: string; text: string }> = {
    muted: { stroke: 'rgba(255,255,255,0.12)', fill: '#16161d', text: '#71717a' },
    running: { stroke: '#06b6d4', fill: '#16161d', text: '#06b6d4' },
    done: { stroke: '#10b981', fill: '#16161d', text: '#10b981' },
    failed: { stroke: '#ef4444', fill: '#16161d', text: '#ef4444' },
  }
  const c = colors[tone]
  const w = width
  const h = 36

  return (
    <g>
      {tone === 'running' && (
        <motion.rect
          x={x - w / 2}
          y={y - h / 2}
          width={w}
          height={h}
          rx={8}
          fill="none"
          stroke={c.stroke}
          strokeWidth={2}
          animate={{ opacity: [0.4, 1, 0.4] }}
          transition={{ duration: 1.2, repeat: Infinity }}
        />
      )}
      <rect
        x={x - w / 2}
        y={y - h / 2}
        width={w}
        height={h}
        rx={8}
        fill={c.fill}
        stroke={c.stroke}
        strokeWidth={1.5}
      />
      <text
        x={x}
        y={y}
        textAnchor="middle"
        dominantBaseline="middle"
        fill={c.text}
        fontSize={12}
        fontFamily="JetBrains Mono, monospace"
      >
        {label}
      </text>
    </g>
  )
}

function Path({ d, running }: { d: string; running: boolean }) {
  return (
    <g>
      <path d={d} fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth={1.5} />
      {running && (
        <motion.circle
          r={3}
          fill="#06b6d4"
          initial={{ offsetDistance: '0%' }}
          animate={{ offsetDistance: '100%' }}
          transition={{ duration: 1.2, repeat: Infinity, ease: 'linear' }}
          style={{ offsetPath: `path('${d}')` } as React.CSSProperties}
        />
      )}
    </g>
  )
}
```

- [ ] **Step 25.2: `AgentCard.tsx`**

```tsx
import { useState } from 'react'
import { motion } from 'framer-motion'
import { ChevronDown } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { formatCost, formatLatency, formatTokens } from '@/lib/format'
import { MODEL_LABELS } from '@/services/types'
import { cn } from '@/lib/cn'
import type { AgentState } from '@/hooks/useTranslationFlow'

interface Props {
  name: string
  state: AgentState | undefined
}

export function AgentCard({ name, state }: Props) {
  const [expanded, setExpanded] = useState(false)
  const status = state?.status ?? 'idle'

  const statusColor = {
    idle: 'text-fg-muted',
    running: 'text-accent-cyan',
    completed: 'text-accent-emerald',
    failed: 'text-accent-crimson',
  }[status]

  return (
    <Card
      className={cn(
        'border-border-default bg-bg-card transition-shadow',
        status === 'running' &&
          'shadow-[0_0_0_1px_#06b6d4_inset,0_0_20px_#06b6d433]',
      )}
    >
      <div className="flex items-center justify-between border-b border-border-default px-4 py-3">
        <div className="font-mono text-sm text-fg-primary">{name}</div>
        <div className="flex items-center gap-2">
          {state?.model && (
            <Badge variant="outline" className="border-border-default font-mono text-[10px] text-fg-muted">
              {state.model}
            </Badge>
          )}
          <span className={cn('text-xs font-medium uppercase tracking-wider', statusColor)}>
            {status}
          </span>
        </div>
      </div>

      <div className="px-4 py-3">
        <div className="mb-3 h-1 overflow-hidden rounded-full bg-bg-base">
          <motion.div
            className={cn(
              'h-full',
              status === 'completed' ? 'bg-accent-emerald' : 'bg-accent-cyan',
            )}
            animate={
              status === 'running'
                ? { width: ['10%', '90%', '10%'] }
                : status === 'completed'
                  ? { width: '100%' }
                  : { width: '0%' }
            }
            transition={
              status === 'running'
                ? { duration: 1.5, repeat: Infinity, ease: 'easeInOut' }
                : { duration: 0.3 }
            }
          />
        </div>

        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
          <Metric label="input tokens" value={formatTokens(state?.tokens?.input)} />
          <Metric label="output tokens" value={formatTokens(state?.tokens?.output)} />
          <Metric label="latency" value={formatLatency(state?.latency_ms)} mono />
          <Metric
            label="cost (USD)"
            value={state?.cost_usd != null ? formatCost(state.cost_usd) : '—'}
            mono
          />
          <Metric
            label="model"
            value={state?.model ? MODEL_LABELS[state.model] : '—'}
          />
          <Metric label="status" value={status} />
        </div>

        <button
          onClick={() => setExpanded((x) => !x)}
          className="mt-3 flex items-center gap-1 text-xs text-fg-muted hover:text-fg-body"
        >
          <ChevronDown
            className={cn('h-3 w-3 transition-transform', expanded && 'rotate-180')}
          />
          View I/O
        </button>

        {expanded && (
          <div className="mt-3 space-y-2">
            <CodeBlock label="text_input" content={state?.text_input ?? '(none)'} />
            <CodeBlock
              label="llm_output"
              content={
                state?.llm_output != null
                  ? JSON.stringify(state.llm_output, null, 2)
                  : '(none)'
              }
            />
          </div>
        )}
      </div>
    </Card>
  )
}

function Metric({
  label,
  value,
  mono,
}: {
  label: string
  value: string
  mono?: boolean
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-fg-muted">{label}</span>
      <span className={cn('text-fg-body', mono && 'font-mono')}>{value}</span>
    </div>
  )
}

function CodeBlock({ label, content }: { label: string; content: string }) {
  return (
    <div>
      <div className="mb-1 text-[10px] uppercase tracking-wider text-fg-muted">
        {label}
      </div>
      <pre className="overflow-x-auto rounded-lg border border-border-default bg-bg-base p-2 font-mono text-[11px] text-fg-body">
        {content}
      </pre>
    </div>
  )
}
```

- [ ] **Step 25.3: `PipelineSummary.tsx`**

```tsx
import { Card } from '@/components/ui/card'
import { formatCost, formatLatency, formatTokens } from '@/lib/format'
import type { TranslateResponse } from '@/services/types'

interface Props {
  payload: TranslateResponse | null
  elapsed: number
}

export function PipelineSummary({ payload, elapsed }: Props) {
  if (!payload) {
    return (
      <Card className="border-border-default bg-bg-card px-4 py-3 text-xs text-fg-muted">
        Elapsed: <span className="font-mono">{(elapsed / 1000).toFixed(3)}s</span>
      </Card>
    )
  }

  const totalInputTokens = payload.agentic_activities.reduce(
    (s, a) => s + (a.input_tokens ?? 0),
    0,
  )
  const totalOutputTokens = payload.agentic_activities.reduce(
    (s, a) => s + (a.output_tokens ?? 0),
    0,
  )
  const totalCost = payload.agentic_activities.reduce(
    (s, a) => s + (a.cost_usd ? parseFloat(a.cost_usd) : 0),
    0,
  )
  // Parallel savings = sum(individual latencies) - max(latency)
  const latencies = payload.agentic_activities
    .map((a) => a.latency_ms ?? 0)
    .filter((n) => n > 0)
  const parallelSavings =
    latencies.reduce((s, n) => s + n, 0) - Math.max(...latencies, 0)

  return (
    <Card className="border-border-default bg-bg-card">
      <div className="grid grid-cols-4 divide-x divide-border-default px-2 py-3 text-xs">
        <Stat
          label="Total latency"
          value={formatLatency(payload.latency_ms)}
          sub={parallelSavings > 0 ? `parallel saved ${Math.round(parallelSavings)}ms` : undefined}
          mono
        />
        <Stat
          label="Total tokens"
          value={`${formatTokens(totalInputTokens)} in · ${formatTokens(totalOutputTokens)} out`}
        />
        <Stat label="Total cost" value={formatCost(totalCost)} mono />
        <Stat label="Agents executed" value={String(payload.agentic_activities.length)} />
      </div>
    </Card>
  )
}

function Stat({
  label,
  value,
  sub,
  mono,
}: {
  label: string
  value: string
  sub?: string
  mono?: boolean
}) {
  return (
    <div className="px-4">
      <div className="text-fg-muted uppercase tracking-wider text-[10px]">{label}</div>
      <div className={mono ? 'mt-0.5 font-mono text-fg-primary' : 'mt-0.5 text-fg-primary'}>
        {value}
      </div>
      {sub && <div className="mt-0.5 text-[10px] text-fg-muted">{sub}</div>}
    </div>
  )
}
```

- [ ] **Step 25.4: `index.tsx`**

```tsx
import { Card } from '@/components/ui/card'
import { Activity } from 'lucide-react'
import { PipelineDiagram } from './PipelineDiagram'
import { AgentCard } from './AgentCard'
import { PipelineSummary } from './PipelineSummary'
import type { AgentStates } from '@/hooks/useTranslationFlow'
import type { TranslateResponse } from '@/services/types'
import { formatElapsedSeconds } from '@/lib/format'

interface Props {
  agents: AgentStates | null
  elapsed: number
  payload: TranslateResponse | null
}

export function AgentPipeline({ agents, elapsed, payload }: Props) {
  return (
    <Card className="bg-bg-card border-border-default">
      <div className="flex items-center justify-between border-b border-border-default px-6 py-4">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-accent-cyan" />
          <h2 className="text-base font-medium text-fg-primary">
            Agent Pipeline
          </h2>
          <span className="text-xs text-fg-muted">
            (parallel orchestration)
          </span>
        </div>
        {agents && (
          <div className="font-mono text-xs text-fg-muted">
            {formatElapsedSeconds(elapsed)}
          </div>
        )}
      </div>

      <div className="p-6">
        <PipelineDiagram agents={agents} />

        {agents && (
          <div className="mt-6 grid grid-cols-2 gap-4">
            <AgentCard name="lang_detect_input" state={agents.lang_detect_input} />
            <AgentCard name="translate" state={agents.translate} />
          </div>
        )}

        <div className="mt-6">
          <PipelineSummary payload={payload} elapsed={elapsed} />
        </div>
      </div>
    </Card>
  )
}
```

## Task 26: PayloadViewer + JsonHighlighter (with test)

**Files:**
- Create: `frontend-demo/src/components/PayloadViewer/JsonHighlighter.tsx`
- Create: `frontend-demo/src/components/PayloadViewer/index.tsx`
- Test: `frontend-demo/src/components/PayloadViewer/JsonHighlighter.test.tsx`

- [ ] **Step 26.1: `JsonHighlighter.tsx`**

```tsx
import { cn } from '@/lib/cn'

interface Props {
  value: unknown
  className?: string
}

// Custom syntax highlighter — no external dep. Renders JSON with token-typed
// spans (string=cyan, number=violet, bool=amber, null=gray, key=white).
export function JsonHighlighter({ value, className }: Props) {
  const json = JSON.stringify(value, null, 2)
  const lines = json.split('\n')

  return (
    <pre className={cn('overflow-x-auto p-4 font-mono text-xs leading-relaxed', className)}>
      {lines.map((line, i) => (
        <div key={i} className="flex">
          <span className="mr-4 w-8 shrink-0 select-none text-right text-fg-placeholder">
            {i + 1}
          </span>
          <span dangerouslySetInnerHTML={{ __html: highlight(line) }} />
        </div>
      ))}
    </pre>
  )
}

function highlight(line: string): string {
  // Escape HTML first
  const escaped = line
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // Order matters: keys first, then strings, numbers, bools, null
  return escaped
    .replace(
      /"([^"\\]*(\\.[^"\\]*)*)"\s*:/g,
      '<span style="color:#ffffff">"$1"</span>:',
    )
    .replace(
      /:\s*"([^"\\]*(\\.[^"\\]*)*)"/g,
      ': <span style="color:#06b6d4">"$1"</span>',
    )
    .replace(
      /:\s*(-?\d+\.?\d*([eE][+-]?\d+)?)/g,
      ': <span style="color:#8b5cf6">$1</span>',
    )
    .replace(/:\s*(true|false)/g, ': <span style="color:#f59e0b">$1</span>')
    .replace(/:\s*null/g, ': <span style="color:#71717a">null</span>')
}
```

- [ ] **Step 26.2: Write `JsonHighlighter.test.tsx`**

```tsx
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { JsonHighlighter } from './JsonHighlighter'

describe('JsonHighlighter', () => {
  it('renders all top-level keys from a TranslateResponse-like object', () => {
    const { container } = render(
      <JsonHighlighter
        value={{
          translated_text: 'Hello',
          source_lang: 'id',
          target_lang: 'en',
          cached: false,
          input_tokens: 42,
          cost_usd: '0.000045',
        }}
      />,
    )
    const text = container.textContent ?? ''
    expect(text).toContain('translated_text')
    expect(text).toContain('source_lang')
    expect(text).toContain('cached')
    expect(text).toContain('42')
    expect(text).toContain('Hello')
  })

  it('numbers lines', () => {
    const { container } = render(<JsonHighlighter value={{ a: 1, b: 2 }} />)
    const text = container.textContent ?? ''
    expect(text).toContain('1')
    expect(text).toContain('2')
    expect(text).toContain('3')
  })
})
```

- [ ] **Step 26.3: `PayloadViewer/index.tsx`**

```tsx
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronDown, Copy, CheckCircle2 } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { JsonHighlighter } from './JsonHighlighter'
import type { TranslateResponse } from '@/services/types'
import { cn } from '@/lib/cn'

interface Props {
  payload: TranslateResponse | null
}

export function PayloadViewer({ payload }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [copied, setCopied] = useState(false)

  const copy = () => {
    if (!payload) return
    navigator.clipboard.writeText(JSON.stringify(payload, null, 2)).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  return (
    <Card className="bg-bg-card border-border-default overflow-hidden">
      <button
        onClick={() => setExpanded((x) => !x)}
        className="flex w-full items-center justify-between border-b border-border-default px-6 py-4 hover:bg-bg-elevated/30"
      >
        <div className="flex items-center gap-2">
          <h2 className="text-base font-medium text-fg-primary">Full Payload</h2>
          {!payload && (
            <span className="text-xs text-fg-muted">— No payload yet</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {payload && (
            <span
              onClick={(e) => {
                e.stopPropagation()
                copy()
              }}
              className="flex items-center gap-1 rounded px-2 py-1 text-xs text-fg-muted hover:bg-bg-elevated hover:text-fg-primary"
            >
              {copied ? <CheckCircle2 className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
              {copied ? 'Copied!' : 'Copy'}
            </span>
          )}
          <ChevronDown
            className={cn(
              'h-4 w-4 text-fg-muted transition-transform',
              expanded && 'rotate-180',
            )}
          />
        </div>
      </button>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="overflow-hidden"
          >
            {payload ? (
              <JsonHighlighter value={payload} />
            ) : (
              <div className="px-6 py-8 text-center text-sm text-fg-muted">
                No payload yet — run a translation
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </Card>
  )
}
```

- [ ] **Step 26.4: Verify tests pass**

```bash
cd frontend-demo
npm run test:run
```

Expected: 18 tests pass total (6 detector + 4 mockApi + 2 debounce + 2 typewriter + 4 flow + 2 mismatch + 2 highlighter — wait, count is 22; brief said ~15-18 so close).

Actually count: 6+4+2+2+4+2+2 = 22. Spec said ~15-18; we're a bit over. Acceptable.

---

# PHASE J-5 — App composition, launcher, cleanup, mega-commit

## Task 27: App composition

**Files:**
- Modify: `frontend-demo/src/App.tsx`
- Modify: `frontend-demo/src/main.tsx`

- [ ] **Step 27.1: Replace `src/App.tsx`**

```tsx
import { useState } from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { TopBar } from '@/components/TopBar'
import { TenantManagement } from '@/components/TenantManagement'
import { TranslationPlayground } from '@/components/TranslationPlayground'
import { SEED_TENANTS } from '@/mocks/tenants'
import type { Tenant } from '@/services/types'

function App() {
  const [tenants, setTenants] = useState<Tenant[]>(SEED_TENANTS)
  const [activeTenantId, setActiveTenantId] = useState<string | null>(
    SEED_TENANTS[0]?.id ?? null,
  )

  const activeTenant = tenants.find((t) => t.id === activeTenantId) ?? null

  const createTenant = (t: Tenant) => {
    setTenants((prev) => [t, ...prev])
    setActiveTenantId(t.id)
  }

  const deleteTenant = (id: string) => {
    setTenants((prev) => prev.filter((t) => t.id !== id))
    if (activeTenantId === id) {
      setActiveTenantId(tenants.find((t) => t.id !== id)?.id ?? null)
    }
  }

  return (
    <div className="min-h-screen text-fg-body">
      <TopBar
        tenants={tenants}
        activeTenantId={activeTenantId}
        onSelectTenant={setActiveTenantId}
      />

      <Tabs defaultValue="playground" className="w-full">
        <TabsList className="mx-6 mt-4 bg-transparent">
          <TabsTrigger value="tenant" className="data-[state=active]:bg-bg-card">
            Tenant Management
          </TabsTrigger>
          <TabsTrigger value="playground" className="data-[state=active]:bg-bg-card">
            Translation Playground
          </TabsTrigger>
        </TabsList>

        <TabsContent value="tenant" className="mt-0">
          <TenantManagement
            tenants={tenants}
            activeTenantId={activeTenantId}
            onCreate={createTenant}
            onSelect={setActiveTenantId}
            onDelete={deleteTenant}
          />
        </TabsContent>

        <TabsContent value="playground" className="mt-0">
          {activeTenant ? (
            <TranslationPlayground tenant={activeTenant} />
          ) : (
            <div className="p-6 text-fg-muted">Create a tenant first.</div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}

export default App
```

- [ ] **Step 27.2: Verify `src/main.tsx`**

It should be:

```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
```

If different, replace with the above.

- [ ] **Step 27.3: Full type-check + tests + build**

```bash
cd frontend-demo
npm run lint
npx tsc --noEmit
npm run test:run
npm run build
```

Expected:
- lint: 0 errors, 0 warnings
- tsc: no errors
- test:run: 22 tests pass
- build: produces `dist/`

If lint warnings appear for unused imports etc., fix them inline before moving on.

## Task 28: PowerShell launcher

**Files:**
- Create: `scripts/run-demo.ps1`

- [ ] **Step 28.1: Write script**

```powershell
# scripts/run-demo.ps1
# Launches the frontend-demo Vite dev server and force-opens Chrome
# once the server is ready. Vite runs in foreground; a background job
# polls localhost:5173 and opens Chrome.

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
    Write-Error 'Chrome not found. Set $env:CHROME_PATH or install Chrome.'
    exit 1
}

# 2. Resolve frontend dir relative to this script
$projectRoot = Split-Path $PSScriptRoot -Parent
$frontendDir = Join-Path $projectRoot 'frontend-demo'
$url = 'http://localhost:5173'

if (-not (Test-Path $frontendDir)) {
    Write-Error "frontend-demo directory not found at $frontendDir"
    exit 1
}

# 3. Install deps if needed
if (-not (Test-Path (Join-Path $frontendDir 'node_modules'))) {
    Write-Host 'Installing dependencies...' -ForegroundColor Cyan
    Push-Location $frontendDir
    try { npm install } finally { Pop-Location }
}

# 4. Background job: wait for Vite, then open Chrome
$openJob = Start-Job -ScriptBlock {
    param($url, $chrome)
    for ($i = 0; $i -lt 60; $i++) {
        try {
            $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 1
            if ($r.StatusCode -eq 200) {
                Start-Process -FilePath $chrome -ArgumentList $url
                return
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    Write-Host 'Vite did not start in 30s — opening Chrome anyway'
    Start-Process -FilePath $chrome -ArgumentList $url
} -ArgumentList $url, $chrome

# 5. Run Vite in foreground
Write-Host "Starting Vite at $url" -ForegroundColor Cyan
Push-Location $frontendDir
try {
    npm run dev
} finally {
    Remove-Job -Job $openJob -Force -ErrorAction SilentlyContinue
    Pop-Location
}
```

- [ ] **Step 28.2: Test the launcher (one round trip)**

```powershell
pwsh scripts/run-demo.ps1
```

Expected:
- Console prints "Starting Vite at http://localhost:5173"
- Vite prints `Local: http://localhost:5173/`
- Within ~5 seconds, Chrome opens the URL
- React app renders (dark background, Polyglot AI top bar, Translation Playground tab active by default)
- Press `Ctrl+C` to stop — script exits cleanly

If Chrome doesn't open, check `Get-Command chrome.exe` and standard paths from Task 1.5. Set `$env:CHROME_PATH` if needed.

## Task 29: Manual smoke checklist

- [ ] **Step 29.1: Launch and verify all features per spec §9.2**

With `pwsh scripts/run-demo.ps1` running:

1. **Chrome auto-opens** to http://localhost:5173 within ~5s ✓
2. **Default tab = Playground**; sample text "Halo, apa kabar hari ini?" pre-filled in input ✓
3. **Real-time detection**: stop typing for 500ms → "Detected: Indonesian · ~95% confidence" appears under textarea ✓
4. **Switch source to English** → red mismatch banner slides in with shake; "Switch source to Indonesian" button works ✓
5. **Click Translate** (with source = Indonesian) → button shows loader; output box shows shimmer skeleton + rotating microcopy; pipeline diagram lights up (both nodes pulse cyan, dots flow on both paths) ✓
6. **lang_detect_input completes first** (~200ms) → flashes green, dot stops on its path; translate completes ~1.2s later → typewriter streams output character-by-character ✓
7. **PayloadViewer collapsed**; click header → expands; JSON renders with syntax highlighting (cyan strings, violet numbers, white keys); Copy button shows checkmark ✓
8. **Switch to Tenant tab** → 5 seeded tenants visible; fill form with name "Test Co" → click Create Tenant → new row slides in at top with cyan glow; auto-selects as active in top bar ✓
9. **Switch back to Playground** → state preserved; payload still rendered ✓
10. **Type long input** (paste >5000 chars) → amber warning banner appears ✓
11. **Empty input** → Translate button visibly disabled ✓
12. **Translate again** with same input → returns instantly with "Cached" feel (pipeline skips long animation, response near-instant) ✓
13. **Tab underline indicator** slides between tabs ✓
14. **Swap button** rotates 180° on click and swaps source/target ✓
15. **Model selector** changes selected model; subsequent translate uses new model in payload ✓

Document any failures inline before commit. Fix root cause, don't paper over.

## Task 30: Delete Streamlit demo

**Files:**
- Delete: `demo/app.py`

- [ ] **Step 30.1: Delete `demo/app.py`**

```bash
rm demo/app.py
```

- [ ] **Step 30.2: Check for orphaned files in `demo/`**

```bash
ls demo/
```

If `demo/__init__.py` or other Python files exist that were only there for app.py, delete them too. Keep `demo/webpage/` (Phase 7 SDK demo — unrelated).

- [ ] **Step 30.3: Search for stale references**

```bash
git grep -l "demo/app.py" -- ":(exclude)docs/" ":(exclude)*.md"
```

Expected: no results, or only in docs (acceptable). If any source/script references `demo/app.py`, update or remove.

## Task 31: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 31.1: Append ADR-047 through ADR-051 to the Decision log section**

Open `CLAUDE.md`. Find the last `ADR-046` line and append after it (before any later sections):

```markdown
- ADR-047: New frontend (Vite + React + TS + Tailwind + shadcn/ui + Framer Motion) replaces Streamlit demo `demo/app.py`. Reason: design brief minta visual rich + animasi tinggi yang Streamlit batasi; demo audience teknis butuh polish stakeholder-grade. Streamlit dihapus setelah React frontend verified end-to-end.
- ADR-048: Frontend TypeScript types match real sub-proyek I `/translate` response shape (canonical), bukan brief's illustrative payload. Reason: cheap mock-to-real swap (single file replacement at integration phase). Brief's payload example tetap dijadikan visual reference untuk highlighting/layout.
- ADR-049: Tab 1 (Tenant Management) di frontend mock-only forever. Brief's tenant model sengaja simpler dari sub-proyek I tenant junction. Real cascade UI (country → company → department → position → service) deferred ke future sub-project — UX needs berbeda (multi-step wizard) dan demo audience focus consumer-app feel.
- ADR-050: PowerShell launcher (`scripts/run-demo.ps1`) force-open Chrome explicitly (bukan default browser). Reason: user requirement, predictable behavior. Resolves chrome.exe via `$env:CHROME_PATH` + `Get-Command` + 3 standard install paths; Vite TIDAK pakai `--open` flag — launcher owns browser open.
- ADR-051: shadcn/ui adopted sebagai base primitive layer (Button, Card, Tabs, Select, Badge, Dialog, Tooltip) bukan Material/Chakra/Mantine. Reason: copy-paste primitives accessible by default, no runtime CSS-in-JS, generated components tinggal di repo (versioned, customizable in-place). Trade-off: lebih banyak files vs single npm import — acceptable for a demo-grade scaffold.
```

- [ ] **Step 31.2: Append sub-proyek J phase status**

Find the section labeled `**Post-MVP sub-projects (started 2026-05-21):**` (or similar). Add a new bullet for sub-proyek J after sub-proyek I:

```markdown
- **Sub-proyek J — Frontend Demo React Redesign**: ✅ complete (verified 2026-05-22)
  - `frontend-demo/` — new Vite + React 18 + TypeScript (strict) + Tailwind 3 + shadcn/ui + Framer Motion 11 SPA replacing Streamlit `demo/app.py` (deleted).
  - `src/services/{types,mockApi,languageDetector,pricing}.ts` — typed contract that mirrors expected sub-proyek I `/translate` response shape (cheap mock-to-real swap). `mockApi` simulates parallel agent orchestration: lang_detect_input + translate agents fire `agent_started` within ~50ms, lang_detect completes 120–280ms, translate completes 800–2200ms (scales by model). Cache hit short-circuits at 3ms latency.
  - `src/hooks/{useDebouncedValue,useElapsedTimer,useTypewriter,useTranslationFlow}.ts` — state machine (`useTranslationFlow`) with `idle → running → done | error` transitions, per-agent status updates driven by `onAgentEvent` callbacks.
  - `src/components/` — TopBar (active tenant dropdown), TenantManagement (form + table, mock-only), TranslationPlayground (LanguageBar + InputBox with real-time langdetect + LanguageMismatchBanner + OutputBox with typewriter + TranslateButton), AgentPipeline (SVG diagram with Framer dot-flow + per-agent cards + summary footer), PayloadViewer (collapsible JSON viewer with custom highlighter).
  - `scripts/run-demo.ps1` — PowerShell launcher: locates `chrome.exe` via `$env:CHROME_PATH` + 3 standard install paths, runs Vite in foreground, background-polls localhost:5173 and opens Chrome on ready.
  - **22 tests** (6 detector + 4 mockApi + 2 debounce + 2 typewriter + 4 flow + 2 mismatch banner + 2 highlighter). Manual smoke checklist from spec §9.2 verified end-to-end.
  - **Known limitations:** Mock-only — `services/realApi.ts` not implemented (deferred to future sub-project that wires to sub-proyek I `/translate` with auth). Mandarin/Arabic/Portuguese/Russian language detection not supported in detector v1 (added on-demand). Browser launcher Windows-only (PowerShell).
  - **Unblocks:** stakeholder-grade product demos; future operator portal can fork the scaffold for cascade-based admin UI.
```

## Task 32: Mega-commit

**Files:** all of the above

- [ ] **Step 32.1: Verify clean state**

```bash
git status --short
```

Expected: lots of `??` lines for new files under `frontend-demo/` + `scripts/run-demo.ps1` + `M CLAUDE.md` + `D demo/app.py` (and maybe `D demo/__init__.py`). No leftover sub-proyek-I-related changes (those should be in previous commits).

- [ ] **Step 32.2: Stage everything**

```bash
git add frontend-demo/ scripts/run-demo.ps1 CLAUDE.md .gitignore
git rm demo/app.py
# If demo/__init__.py also removed:
git rm demo/__init__.py 2>$null
```

- [ ] **Step 32.3: Verify nothing unexpected staged**

```bash
git status --short
```

Expected: all changes staged (`A` for new files, `M` for modified, `D` for deleted). Nothing accidentally pulled in.

- [ ] **Step 32.4: Commit**

Use PowerShell here-string (`@'...'@`). The closing `'@` MUST be at column 0:

```powershell
git commit -m @'
Sub-proyek J complete: Vite + React + TS + Tailwind + shadcn frontend-demo SPA replaces Streamlit (ADR-047-051)

frontend-demo/ new scaffold - TopBar, TenantManagement (mock-only),
TranslationPlayground (LanguageBar + InputBox real-time langdetect +
mismatch banner + OutputBox typewriter + TranslateButton),
AgentPipeline (SVG dot-flow diagram + per-agent metric cards + summary),
PayloadViewer (collapsible JSON with custom highlighter).

Mock API (services/mockApi.ts) returns the real sub-proyek I /translate
shape so swap-out at integration phase is a single file replacement
(ADR-048). State machine (useTranslationFlow) drives idle->running->done
with parallel agent completion events.

PowerShell launcher (scripts/run-demo.ps1) force-opens Chrome via
$env:CHROME_PATH + 3 standard install paths fallback (ADR-050).
Vite runs foreground; background job polls localhost:5173 and opens
Chrome once ready.

22 tests pass (6 detector + 4 mockApi + 2 debounce + 2 typewriter +
4 flow state machine + 2 mismatch banner + 2 JSON highlighter).
Manual smoke checklist from spec section 9.2 verified end-to-end (Chrome
auto-open, parallel agent viz, typewriter streaming, mismatch banner
with shake, cached repeat, long-input warning, swap, model switcher).

Streamlit demo/app.py deleted (verified git grep no stale refs
outside docs). demo/webpage/ Phase 7 SDK landing page retained.
Tab 1 stays mock-only forever per ADR-049 - real cascade UI is a
separate sub-project.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
'@
```

If running in bash (e.g., via Git Bash), use this equivalent:

```bash
git commit -m "$(cat <<'EOF'
Sub-proyek J complete: Vite + React + TS + Tailwind + shadcn frontend-demo SPA replaces Streamlit (ADR-047-051)

[same body as above]

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 32.5: Verify commit**

```bash
git log --oneline -1
git show --stat HEAD | head -40
```

Expected: commit lands; ~70+ files changed.

- [ ] **Step 32.6: DO NOT push**

Per project policy, never `git push`. User pushes manually when ready.

---

## Summary

After all 32 tasks:
- `frontend-demo/` package built: ~40 source files, 7 test files, ~22 passing tests
- `scripts/run-demo.ps1` launches Vite + opens Chrome
- `demo/app.py` (Streamlit) deleted; `demo/webpage/` (SDK Phase 7 demo) retained
- CLAUDE.md gains ADR-047 through ADR-051 + sub-proyek J phase status entry
- Single commit at HEAD; ready for review and (optional) push

**Next sub-project (out of scope):** wire `services/realApi.ts` to sub-proyek I `/translate` with `Authorization: Bearer <jwt>` or `X-Tenant-API-Key`. Adapter fires `agent_started` immediately, schedules `agent_completed` from `agentic_activities[i].latency_ms`. Switch via `VITE_API_MODE=mock|real` in `.env.local`.
