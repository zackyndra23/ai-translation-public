# AI Translation by Integrity — Frontend Demo

Vite + React + TypeScript + Tailwind + shadcn/ui SPA. Stakeholder-grade
product demo for PT. Integrity Indonesia's AI translation product.

This replaces the former Streamlit operator UI (`demo/app.py`, deleted in
sub-proyek J). The Streamlit `demo/webpage/` Phase-7 JS-SDK landing page
is separate and unrelated to this folder.

## Quick launch

From the repository root:

```powershell
.\scripts\run-demo.ps1
```

The script:
1. Locates `chrome.exe` (PATH, `$env:CHROME_PATH`, or three standard
   install paths).
2. Runs `npm install` (~30–60 seconds on first launch only).
3. Starts Vite in the foreground at `http://localhost:5173`.
4. A background job polls the dev server and opens Chrome on the first
   200 OK response.

Press `Ctrl+C` in the terminal to stop Vite. The background job is
cleaned up automatically.

If you do not have PowerShell 7+ (`pwsh`), the launcher works on Windows
PowerShell 5.1 too — same command.

## Mock-only — no backend needed

The frontend in v1 is **mock-only**:

- `services/mockApi.ts` simulates `/translate` responses entirely
  in-browser. Two agents (`lang_detect_input`, `translate`) emit
  `agent_started` and `agent_completed` events with realistic
  latency ranges (120–280 ms for detect, 500–2200 ms for translate,
  scaled by selected model). Repeat translations hit an in-memory cache
  and return at 3 ms with `cached: true`.
- `services/languageDetector.ts` runs a synchronous keyword-based
  classifier in the browser for the typing-time mismatch banner.
- `mocks/tenants.ts` ships five seeded tenants (Acme Localization,
  TravelGenie Inc., Globex Trading Pte Ltd, Lumen Health Network,
  Aitegrity Internal). Tenant CRUD is in-memory; nothing is persisted.

You do **not** need to start the FastAPI backend (`uvicorn`), PostgreSQL,
or Redis to run or demo this UI.

## Stack

- Vite 5 (npm create vite scaffold → forced to Vite 8 by upstream;
  `vitest.config.ts` is a separate file because Vite 8 + Vitest type
  generics conflict in a combined `defineConfig` call)
- React 18 (`StrictMode`-wrapped root)
- TypeScript 5 (`strict: true`)
- Tailwind CSS 3 with custom merah-putih palette per ADR-052
- shadcn/ui (Button, Card, Tabs, Select, Badge, Dialog, Tooltip — all
  copy-pasted into `src/components/ui/`)
- Framer Motion 11 (SVG `offsetPath` dot-flow on pipeline diagram,
  pulse rings on running agents, slide-in for new tenants and mismatch
  banner)
- Vitest 2 + `@testing-library/react` + `jsdom` (22 tests)
- ESLint + Prettier (`npm run lint` is `--max-warnings 0`)

## Scripts

| Command | What it does |
| --- | --- |
| `npm run dev` | Vite dev server on `localhost:5173` (no auto-open — `scripts/run-demo.ps1` opens Chrome separately) |
| `npm run build` | Type-check + production bundle to `dist/` |
| `npm run preview` | Serve the production build locally |
| `npm run test` | Vitest watch mode |
| `npm run test:run` | One-shot test run (CI mode) |
| `npm run lint` | ESLint with zero-warning gate |
| `npm run format` | Prettier write across `src/` |

## Manual smoke checklist

Launch and verify:

1. Chrome auto-opens `localhost:5173` within ~5 seconds.
2. Default tab = **Translation Playground**; input is pre-filled with
   "Halo, apa kabar hari ini?".
3. Stop typing for 500 ms → "Detected: Indonesian · ~XX% confidence"
   appears below the textarea.
4. Switch source to English → red-ish (amber) banner slides in above
   the textarea with a 200 ms shake; click "Switch source" to swap back.
5. Click **Translate** → button pulses → output box shows shimmer +
   rotating loading messages → pipeline diagram lights up (both agent
   nodes pulse, dots flow on the SVG paths) → `lang_detect_input` flashes
   green first → translate completes → typewriter streams the output.
6. Click **Full Payload** → JSON expands with syntax highlighting
   (string=rose, number=amber, bool=emerald, key=white, null=gray).
7. Switch to **Tenant Management** → five seeded tenants visible →
   fill the form → click "Create Tenant" → new row slides in at the top
   with a brief red glow.
8. Click the swap (↔) icon between the language selectors → source and
   target swap with a 180° rotate animation.

## Project structure

```
frontend-demo/
├── public/favicon.svg     # Owl mark — Integrity's mascot (ADR-052)
├── src/
│   ├── App.tsx            # Top bar + tab routing
│   ├── main.tsx           # React 18 createRoot bootstrap
│   ├── index.css          # Tailwind directives + base + shimmer keyframe
│   ├── components/
│   │   ├── TopBar.tsx
│   │   ├── TenantManagement/
│   │   ├── TranslationPlayground/    # Top section: language bar + input/output + translate CTA
│   │   ├── AgentPipeline/            # Middle section: SVG diagram + agent cards + summary
│   │   ├── PayloadViewer/            # Bottom section: collapsible JSON with syntax highlighter
│   │   └── ui/                       # shadcn-generated primitives — don't hand-edit
│   ├── hooks/
│   │   ├── useDebouncedValue.ts
│   │   ├── useElapsedTimer.ts
│   │   ├── useTypewriter.ts
│   │   └── useTranslationFlow.ts     # Idle → running → done | error state machine
│   ├── services/
│   │   ├── types.ts                  # TranslateApi + AgenticActivity + TranslateResponse — mirrors real backend shape per ADR-048
│   │   ├── mockApi.ts                # In-browser simulator
│   │   ├── languageDetector.ts       # Typing-time classifier
│   │   └── pricing.ts                # Per-model token costs
│   ├── lib/
│   │   ├── cn.ts                     # clsx + tailwind-merge helper
│   │   ├── utils.ts                  # shadcn duplicate of cn — both kept; new shadcn components import from utils
│   │   └── format.ts                 # Cost / latency / token / elapsed formatters
│   └── mocks/
│       ├── tenants.ts                # Five seeded tenants + generateTenantId
│       └── translations.ts           # Lookup table + fallback placeholder
├── components.json                   # shadcn config
├── tailwind.config.ts                # Custom palette + keyframes + gradient
├── vite.config.ts                    # Production build config
├── vitest.config.ts                  # Test config (separate file due to Vite 8 type conflict)
├── tsconfig.json                     # Strict TypeScript + path alias `@/*`
└── package.json
```

## Future: real backend integration

In v1 the frontend never calls the FastAPI `/translate` endpoint. The
mock returns the same shape as the real backend will (see
`services/types.ts` and ADR-048), so swapping in a real client is a
single-file replacement.

A future sub-project will:
1. Create `services/realApi.ts` implementing the `TranslateApi` interface.
   POST `${VITE_API_BASE}/translate` with either
   `Authorization: Bearer <jwt>` or `X-Tenant-API-Key: aitkey_…` (per
   ADR-046).
2. Adapt the single-shot HTTP response into the streaming
   `onAgentEvent(agent_started)` / `onAgentEvent(agent_completed)`
   callbacks by scheduling events from `agentic_activities[].latency_ms`.
3. Switch via `VITE_API_MODE=mock|real` in `.env.local`.

The cascade UI (Country → Company → Department → Position → Service) is
also a future sub-project — Tab 1 in this demo is intentionally
mock-only forever per ADR-049.

## Branding

"AI Translation by Integrity" — PT. Integrity Indonesia's product. Owl
mascot/trademark. Merah-putih palette per ADR-052:

| Token | Hex | Use |
| --- | --- | --- |
| `accent-red` | `#B91C1C` | Primary brand + CTAs |
| `accent-rose` | `#F43F5E` | Gradient pair for CTAs (`bg-red-rose`) |
| `accent-amber` | `#F59E0B` | Warnings (lang-mismatch banner) |
| `accent-emerald` | `#10B981` | Success / agent-completed |
| `accent-crimson` | `#EF4444` | True error / failure (rare) |
| `bg-base` | `#0A0A0C` | Page background (with radial-gradient to `#14141A` at top) |
| `bg-card` | `#16161D` | Card surfaces |
| `bg-elevated` | `#1C1C25` | Hover / popover surfaces |

The Streamlit demo had cyan-violet branding; that has been removed.
