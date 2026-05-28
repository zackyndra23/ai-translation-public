# Sub-proyek L Implementation Plan — Frontend-Demo ↔ Real Backend Wiring (MVP)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `frontend-demo/src/services/mockApi.ts` with a real `/translate` adapter (`realApi.ts`) so Tab 2 Translation Playground hits the live backend, preserving AgentPipeline animation via synthetic streaming, with Settings modal for credentials + Vite dev proxy + `VITE_API_MODE` env toggle + error banner UX.

**Architecture:** Adapter pattern over `types.ts` canonical rewrite. `apiClient.ts` thin fetch wrapper. `responseAdapter.ts` maps backend response → frontend type. `realApi.ts` fires synthetic streaming events spaced by `activity.latency_ms`. `apiSelector.ts` picks mock vs real per env var + localStorage settings. Settings modal (shadcn Dialog) configures api_key + tenant_id + profile_id + baseUrl in localStorage. Error mapping: 5 backend `error_code` → severity-tinted inline banner above OutputBox.

**Tech Stack:** Vite 8 + React 18 + TypeScript 5 (strict), Tailwind 3, shadcn/ui (Dialog/Button/Input/Label), Vitest 2, lucide-react (Settings gear icon), localStorage browser API, fetch web API.

**Spec reference:** `docs/superpowers/specs/2026-05-22-frontend-real-api-wiring-design.md`

---

## File Structure Map

**Frontend new files:**
- `frontend-demo/.env.local.example` — `VITE_API_MODE` + `VITE_API_BASE_URL` template
- `frontend-demo/src/services/errors.ts` — `ApiError` + `NetworkError` classes
- `frontend-demo/src/services/apiClient.ts` — fetch wrapper with auth + error mapping
- `frontend-demo/src/services/responseAdapter.ts` — backend response → frontend type
- `frontend-demo/src/services/realApi.ts` — `makeRealApi` factory + synthetic streaming
- `frontend-demo/src/services/apiSelector.ts` — picks mock vs real per env + settings
- `frontend-demo/src/hooks/useApiSettings.ts` — localStorage read/write hook + `ApiSettings` type
- `frontend-demo/src/components/SettingsModal.tsx` — credentials configuration dialog
- `frontend-demo/tests/services/errors.test.ts`
- `frontend-demo/tests/services/apiClient.test.ts`
- `frontend-demo/tests/services/responseAdapter.test.ts`
- `frontend-demo/tests/services/realApi.test.ts`
- `frontend-demo/tests/services/apiSelector.test.ts`
- `frontend-demo/tests/hooks/useApiSettings.test.ts`
- `frontend-demo/tests/components/SettingsModal.test.tsx`

**Frontend modified files:**
- `frontend-demo/vite.config.ts` — add `/api/*` proxy
- `frontend-demo/src/App.tsx` — replace mockApi import; add SettingsModal trigger
- `frontend-demo/src/components/TopBar.tsx` — add Settings gear icon button
- `frontend-demo/src/components/TranslationPlayground/index.tsx` — error banner + ApiError handling + read profile_id/tenant_id from settings
- `frontend-demo/src/services/types.ts` — re-export `ApiSettings` from `useApiSettings` (single line)

**Backend modified files:**
- `src/api/main.py` — extend CORS allowlist to include `localhost:5173`; remove defunct `localhost:8501`

**Docs files:**
- `docs/adrs.md` — append ADR-059..064
- `CLAUDE.md` — extend ADR index + add Sub-proyek L phase entry
- `docs/phase-status.md` — append Sub-proyek L section

---

## Section A — Foundation: errors + settings + modal (commit batch 1)

### Task A1: `errors.ts` — `ApiError` + `NetworkError` classes

**Files:**
- Create: `frontend-demo/src/services/errors.ts`
- Test: `frontend-demo/tests/services/errors.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend-demo/tests/services/errors.test.ts`:

```typescript
import { describe, expect, it } from 'vitest'
import { ApiError, NetworkError } from '@/services/errors'

describe('ApiError', () => {
  it('exposes status + errorCode + detail + traceId', () => {
    const err = new ApiError({
      status: 400,
      errorCode: 'language_not_allowed',
      detail: "target 'ja' not allowed",
      traceId: 'abc123',
    })
    expect(err.status).toBe(400)
    expect(err.errorCode).toBe('language_not_allowed')
    expect(err.detail).toBe("target 'ja' not allowed")
    expect(err.traceId).toBe('abc123')
    expect(err.message).toContain('language_not_allowed')
  })

  it('isLanguageNotAllowed() is true only for that code', () => {
    const a = new ApiError({ status: 400, errorCode: 'language_not_allowed', detail: '' })
    const b = new ApiError({ status: 400, errorCode: 'other', detail: '' })
    expect(a.isLanguageNotAllowed()).toBe(true)
    expect(b.isLanguageNotAllowed()).toBe(false)
  })

  it('isAuth() covers authentication_failed + tenant_not_found', () => {
    expect(new ApiError({ status: 401, errorCode: 'authentication_failed', detail: '' }).isAuth()).toBe(true)
    expect(new ApiError({ status: 401, errorCode: 'tenant_not_found', detail: '' }).isAuth()).toBe(true)
    expect(new ApiError({ status: 400, errorCode: 'other', detail: '' }).isAuth()).toBe(false)
  })

  it('isTransient() covers upstream_transient + 5xx', () => {
    expect(new ApiError({ status: 503, errorCode: 'upstream_transient', detail: '' }).isTransient()).toBe(true)
    expect(new ApiError({ status: 500, errorCode: 'whatever', detail: '' }).isTransient()).toBe(true)
    expect(new ApiError({ status: 400, errorCode: 'other', detail: '' }).isTransient()).toBe(false)
  })

  it('isRateLimited() exactly matches rate_limited', () => {
    expect(new ApiError({ status: 429, errorCode: 'rate_limited', detail: '' }).isRateLimited()).toBe(true)
    expect(new ApiError({ status: 429, errorCode: 'other', detail: '' }).isRateLimited()).toBe(false)
  })
})

describe('NetworkError', () => {
  it('wraps an underlying cause', () => {
    const cause = new TypeError('Failed to fetch')
    const err = new NetworkError(cause)
    expect(err.cause).toBe(cause)
    expect(err.message).toBe('Network error')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend-demo && npm test -- tests/services/errors.test.ts
```
Expected: FAIL — module not found.

- [ ] **Step 3: Create `frontend-demo/src/services/errors.ts`**

```typescript
// Typed API errors. Used by apiClient + realApi + TranslationPlayground.
// Predicates keep the call sites readable (`err.isLanguageNotAllowed()` reads
// better than `err.errorCode === 'language_not_allowed'` scattered everywhere).

export interface ApiErrorOpts {
  status: number
  errorCode: string
  detail: string
  traceId?: string
}

export class ApiError extends Error {
  status: number
  errorCode: string
  detail: string
  traceId?: string

  constructor(opts: ApiErrorOpts) {
    super(`${opts.errorCode}: ${opts.detail}`)
    this.name = 'ApiError'
    this.status = opts.status
    this.errorCode = opts.errorCode
    this.detail = opts.detail
    this.traceId = opts.traceId
  }

  isLanguageNotAllowed(): boolean {
    return this.errorCode === 'language_not_allowed'
  }

  isAuth(): boolean {
    return this.errorCode === 'authentication_failed' || this.errorCode === 'tenant_not_found'
  }

  isRateLimited(): boolean {
    return this.errorCode === 'rate_limited'
  }

  isTransient(): boolean {
    return this.errorCode === 'upstream_transient' || this.status >= 500
  }
}

export class NetworkError extends Error {
  cause: unknown

  constructor(cause: unknown) {
    super('Network error')
    this.name = 'NetworkError'
    this.cause = cause
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd frontend-demo && npm test -- tests/services/errors.test.ts
```
Expected: 5 PASS.

- [ ] **Step 5: No commit yet** — all of Batch A committed together at the end of Task A4.

---

### Task A2: `useApiSettings` hook — localStorage persistence

**Files:**
- Create: `frontend-demo/src/hooks/useApiSettings.ts`
- Test: `frontend-demo/tests/hooks/useApiSettings.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend-demo/tests/hooks/useApiSettings.test.ts`:

```typescript
import { renderHook, act } from '@testing-library/react'
import { describe, expect, it, beforeEach } from 'vitest'
import { useApiSettings } from '@/hooks/useApiSettings'

beforeEach(() => {
  window.localStorage.clear()
})

describe('useApiSettings', () => {
  it('starts with defaults when localStorage is empty', () => {
    const { result } = renderHook(() => useApiSettings())
    expect(result.current.settings).toEqual({
      baseUrl: '/api',
      apiKey: '',
      profileId: '',
      tenantId: '',
    })
    expect(result.current.isConfigured).toBe(false)
  })

  it('save() persists to localStorage and exposes isConfigured=true once all set', () => {
    const { result } = renderHook(() => useApiSettings())
    act(() => {
      result.current.save({
        apiKey: 'aitkey_xyz',
        profileId: 'profile-aaaaaaaa-bbbb',
        tenantId: 'tenant-cccccccc-dddd',
      })
    })
    expect(result.current.settings.apiKey).toBe('aitkey_xyz')
    expect(result.current.isConfigured).toBe(true)
    const stored = JSON.parse(window.localStorage.getItem('aitegrity_api_settings')!)
    expect(stored.apiKey).toBe('aitkey_xyz')
  })

  it('rehydrates from localStorage on mount', () => {
    window.localStorage.setItem(
      'aitegrity_api_settings',
      JSON.stringify({
        baseUrl: 'http://custom:9000',
        apiKey: 'aitkey_pre',
        profileId: 'profile-11111111-2222',
        tenantId: 'tenant-33333333-4444',
      }),
    )
    const { result } = renderHook(() => useApiSettings())
    expect(result.current.settings.baseUrl).toBe('http://custom:9000')
    expect(result.current.isConfigured).toBe(true)
  })

  it('isConfigured=false when apiKey does not start with aitkey_', () => {
    const { result } = renderHook(() => useApiSettings())
    act(() => {
      result.current.save({
        apiKey: 'wrong_prefix',
        profileId: 'profile-aaaaaaaa-bbbb',
        tenantId: 'tenant-cccccccc-dddd',
      })
    })
    expect(result.current.isConfigured).toBe(false)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend-demo && npm test -- tests/hooks/useApiSettings.test.ts
```
Expected: FAIL — module not found.

- [ ] **Step 3: Create `frontend-demo/src/hooks/useApiSettings.ts`**

```typescript
import { useState } from 'react'

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
    // Corrupted JSON — wipe and start fresh rather than throw at render time.
    window.localStorage.removeItem(STORAGE_KEY)
    return DEFAULTS
  }
}

// isConfigured deliberately requires apiKey prefix to catch fat-finger pastes
// (typos in aitkey_ prefix fail loud). profileId/tenantId checked for non-empty
// only — full format validation happens in the SettingsModal form.
function checkConfigured(s: ApiSettings): boolean {
  return s.apiKey.startsWith('aitkey_') && s.profileId.length > 0 && s.tenantId.length > 0
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

  return {
    settings,
    save,
    isConfigured: checkConfigured(settings),
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd frontend-demo && npm test -- tests/hooks/useApiSettings.test.ts
```
Expected: 4 PASS.

- [ ] **Step 5: No commit yet** — accumulating Batch A.

---

### Task A3: `SettingsModal` component — credentials configuration UI

**Files:**
- Create: `frontend-demo/src/components/SettingsModal.tsx`
- Test: `frontend-demo/tests/components/SettingsModal.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend-demo/tests/components/SettingsModal.test.tsx`:

```typescript
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, beforeEach } from 'vitest'
import { SettingsModal } from '@/components/SettingsModal'

beforeEach(() => {
  window.localStorage.clear()
})

describe('SettingsModal', () => {
  it('renders four inputs and a save button when open', () => {
    render(<SettingsModal open={true} onOpenChange={() => {}} />)
    expect(screen.getByLabelText(/Base URL/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/API Key/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/Profile ID/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/Tenant ID/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Save/i })).toBeInTheDocument()
  })

  it('saves to localStorage on Save and closes modal', () => {
    let openState = true
    const onOpenChange = (next: boolean) => { openState = next }
    render(<SettingsModal open={openState} onOpenChange={onOpenChange} />)

    fireEvent.change(screen.getByLabelText(/API Key/i), { target: { value: 'aitkey_xyz' } })
    fireEvent.change(screen.getByLabelText(/Profile ID/i), {
      target: { value: 'profile-aaaaaaaa-bbbb' },
    })
    fireEvent.change(screen.getByLabelText(/Tenant ID/i), {
      target: { value: 'tenant-cccccccc-dddd' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Save/i }))

    const stored = JSON.parse(window.localStorage.getItem('aitegrity_api_settings')!)
    expect(stored.apiKey).toBe('aitkey_xyz')
    expect(stored.profileId).toBe('profile-aaaaaaaa-bbbb')
    expect(openState).toBe(false)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend-demo && npm test -- tests/components/SettingsModal.test.tsx
```
Expected: FAIL — component not found.

- [ ] **Step 3: Inspect shadcn/ui components needed**

Verify `Dialog` and `Label` primitives exist:
```bash
ls frontend-demo/src/components/ui/
```
Expected to include `dialog.tsx`. If `label.tsx` missing, create a minimal one:

```tsx
// frontend-demo/src/components/ui/label.tsx
import * as React from 'react'
import { cn } from '@/lib/cn'

export const Label = React.forwardRef<
  HTMLLabelElement,
  React.LabelHTMLAttributes<HTMLLabelElement>
>(({ className, ...props }, ref) => (
  <label
    ref={ref}
    className={cn('text-sm font-medium text-fg-body', className)}
    {...props}
  />
))
Label.displayName = 'Label'
```

If `input.tsx` missing, create a minimal one:

```tsx
// frontend-demo/src/components/ui/input.tsx
import * as React from 'react'
import { cn } from '@/lib/cn'

export const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, type, ...props }, ref) => (
  <input
    ref={ref}
    type={type}
    className={cn(
      'flex h-9 w-full rounded-md border border-border-default bg-bg-base px-3 py-1 text-sm',
      'text-fg-body placeholder:text-fg-muted',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-red',
      'disabled:cursor-not-allowed disabled:opacity-50',
      className,
    )}
    {...props}
  />
))
Input.displayName = 'Input'
```

- [ ] **Step 4: Create `frontend-demo/src/components/SettingsModal.tsx`**

```tsx
import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useApiSettings } from '@/hooks/useApiSettings'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
}

// Settings modal — sole entry point for backend credentials configuration.
// Per ADR-061, kept separate from Tab 1 mock tenant management. localStorage
// persistence via useApiSettings hook (ADR-026 PII trade-off precedent —
// API key in localStorage is acceptable for demo/dev context).
export function SettingsModal({ open, onOpenChange }: Props) {
  const { settings, save } = useApiSettings()
  const [draft, setDraft] = useState(settings)
  const [showApiKey, setShowApiKey] = useState(false)

  // Re-sync draft when modal opens — picks up external changes (e.g. another
  // tab edited localStorage). Reset show-API-key on close so re-open doesn't
  // leak the key visually if user walks away mid-edit.
  useEffect(() => {
    if (open) {
      setDraft(settings)
    } else {
      setShowApiKey(false)
    }
  }, [open, settings])

  const apiMode = import.meta.env.VITE_API_MODE ?? 'mock'

  const handleSave = () => {
    save(draft)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-bg-card border-border-default max-w-md">
        <DialogHeader>
          <DialogTitle className="text-fg-primary">Backend Connection</DialogTitle>
          <DialogDescription>
            Currently using:{' '}
            <span className={apiMode === 'real' ? 'text-accent-emerald' : 'text-accent-amber'}>
              {apiMode === 'real' ? 'REAL backend' : 'MOCK in-memory'}
            </span>
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1">
            <Label htmlFor="settings-baseUrl">Base URL</Label>
            <Input
              id="settings-baseUrl"
              value={draft.baseUrl}
              onChange={(e) => setDraft({ ...draft, baseUrl: e.target.value })}
              placeholder="/api"
            />
            <p className="text-xs text-fg-muted">
              Default <code>/api</code> uses Vite dev proxy. Override with full URL for prod.
            </p>
          </div>

          <div className="space-y-1">
            <Label htmlFor="settings-apiKey">API Key</Label>
            <div className="flex gap-2">
              <Input
                id="settings-apiKey"
                type={showApiKey ? 'text' : 'password'}
                value={draft.apiKey}
                onChange={(e) => setDraft({ ...draft, apiKey: e.target.value })}
                placeholder="aitkey_..."
                className="font-mono"
              />
              <Button
                type="button"
                variant="outline"
                onClick={() => setShowApiKey((s) => !s)}
              >
                {showApiKey ? 'Hide' : 'Show'}
              </Button>
            </div>
            <p className="text-xs text-fg-muted">
              Output from <code>scripts/seed_tenant_data.py</code> first run (stdout
              <code> API_KEY=aitkey_...</code>).
            </p>
          </div>

          <div className="space-y-1">
            <Label htmlFor="settings-profileId">Profile ID</Label>
            <Input
              id="settings-profileId"
              value={draft.profileId}
              onChange={(e) => setDraft({ ...draft, profileId: e.target.value })}
              placeholder="profile-XXXXXXXX-XXXX"
              className="font-mono"
            />
            <p className="text-xs text-fg-muted">
              From backend. PSQL:{' '}
              <code>SELECT profile_id, tenant_name FROM tenant_profile LIMIT 5;</code>
            </p>
          </div>

          <div className="space-y-1">
            <Label htmlFor="settings-tenantId">Tenant ID</Label>
            <Input
              id="settings-tenantId"
              value={draft.tenantId}
              onChange={(e) => setDraft({ ...draft, tenantId: e.target.value })}
              placeholder="tenant-XXXXXXXX-XXXX"
              className="font-mono"
            />
            <p className="text-xs text-fg-muted">
              From backend. PSQL:{' '}
              <code>SELECT tenant_id, tenant_name FROM tenant LIMIT 5;</code>
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd frontend-demo && npm test -- tests/components/SettingsModal.test.tsx
```
Expected: 2 PASS.

If `@testing-library/react` is missing, install:
```bash
cd frontend-demo && npm install -D @testing-library/react @testing-library/dom
```

- [ ] **Step 6: No commit yet** — accumulating Batch A.

---

### Task A4: TopBar gear icon + App.tsx integration + commit Batch A

**Files:**
- Modify: `frontend-demo/src/components/TopBar.tsx`
- Modify: `frontend-demo/src/App.tsx`

- [ ] **Step 1: Update `frontend-demo/src/components/TopBar.tsx`** to add a Settings gear icon button with `onOpenSettings` prop.

Add to imports:
```typescript
import { Settings as SettingsIcon } from 'lucide-react'
import { useApiSettings } from '@/hooks/useApiSettings'
```

Extend `Props`:
```typescript
interface Props {
  tenants: Tenant[]
  activeTenantId: string | null
  onSelectTenant: (id: string) => void
  onOpenSettings: () => void  // NEW
}
```

In the right-side `<div className="flex items-center gap-4">`, BEFORE the avatar div, insert the gear button:
```tsx
{/* Settings gear — opens credentials modal. Red dot indicator when settings
    not configured AND VITE_API_MODE === 'real' (real backend wants creds but
    user hasn't provided any). */}
<SettingsGearButton onClick={onOpenSettings} />
```

And at the bottom of the file, add:
```tsx
function SettingsGearButton({ onClick }: { onClick: () => void }) {
  const { isConfigured } = useApiSettings()
  const apiMode = import.meta.env.VITE_API_MODE ?? 'mock'
  const showAlert = apiMode === 'real' && !isConfigured

  return (
    <button
      onClick={onClick}
      className={cn(
        'relative grid h-9 w-9 place-items-center rounded-lg bg-bg-elevated text-fg-muted',
        'hover:text-fg-primary hover:bg-bg-card transition-colors',
      )}
      aria-label="Open settings"
    >
      <SettingsIcon className="h-5 w-5" />
      {showAlert && (
        <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-accent-red" />
      )}
    </button>
  )
}
```

- [ ] **Step 2: Update `frontend-demo/src/App.tsx`** to manage settings modal state.

Add to imports:
```typescript
import { useState, useEffect } from 'react'  // useEffect newly needed
import { SettingsModal } from '@/components/SettingsModal'
import { useApiSettings } from '@/hooks/useApiSettings'
```

Inside `App()`, add state:
```typescript
const [settingsOpen, setSettingsOpen] = useState(false)
const { isConfigured } = useApiSettings()

// Auto-open on first launch if real mode and no credentials.
useEffect(() => {
  const apiMode = import.meta.env.VITE_API_MODE ?? 'mock'
  if (apiMode === 'real' && !isConfigured) {
    setSettingsOpen(true)
  }
}, [isConfigured])
```

Pass `onOpenSettings={() => setSettingsOpen(true)}` to `<TopBar>`. Render `<SettingsModal open={settingsOpen} onOpenChange={setSettingsOpen} />` just inside the root `<div>`.

Full updated return:
```tsx
return (
  <div className="min-h-screen text-fg-body">
    <TopBar
      tenants={tenants}
      activeTenantId={activeTenantId}
      onSelectTenant={setActiveTenantId}
      onOpenSettings={() => setSettingsOpen(true)}
    />
    <SettingsModal open={settingsOpen} onOpenChange={setSettingsOpen} />
    <Tabs defaultValue="playground" className="w-full">
      {/* ...existing tabs unchanged... */}
    </Tabs>
  </div>
)
```

- [ ] **Step 3: Verify the dev server still boots cleanly**

```bash
cd frontend-demo && npm run dev
```
Expected: Vite serves on `http://localhost:5173` without TypeScript errors. Browse manually: TopBar should show the gear icon. Click it → SettingsModal opens.

Kill the dev server (Ctrl+C) before committing.

- [ ] **Step 4: Run full vitest suite**

```bash
cd frontend-demo && npm test -- --run
```
Expected: 22 pre-existing + 11 new (5 errors + 4 settings + 2 modal) = 33 pass.

- [ ] **Step 5: Lint + typecheck**

```bash
cd frontend-demo && npm run lint && npm run build
```
Expected: lint clean (zero warnings), build dist/.

- [ ] **Step 6: Commit Batch A**

```bash
git add frontend-demo/
git commit -m "$(cat <<'EOF'
feat(sub-proyek L): batch A - settings foundation (errors + useApiSettings + SettingsModal + TopBar gear)

ApiError + NetworkError typed classes, localStorage-backed useApiSettings
hook, shadcn Dialog-based SettingsModal with 4 inputs (baseUrl, apiKey
masked, profileId, tenantId), TopBar gear button with red-dot alert when
real mode + missing creds, auto-open on first real-mode launch.
EOF
)"
```

---

## Section B — API layer: client + adapter + selector (commit batch 2)

### Task B1: `apiClient.ts` — fetch wrapper with auth + error mapping

**Files:**
- Create: `frontend-demo/src/services/apiClient.ts`
- Test: `frontend-demo/tests/services/apiClient.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend-demo/tests/services/apiClient.test.ts`:

```typescript
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { ApiClient } from '@/services/apiClient'
import { ApiError, NetworkError } from '@/services/errors'

const okResponse = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })

const errorResponse = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('ApiClient', () => {
  it('parses JSON success and injects X-Tenant-API-Key header', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      okResponse({ translation: 'Hello' }),
    )
    const client = new ApiClient({ baseUrl: '/api', apiKey: 'aitkey_xyz' })
    const result = await client.post<{ translation: string }>('/translate', { text: 'Halo' })

    expect(result).toEqual({ translation: 'Hello' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/translate')
    expect((init as RequestInit).method).toBe('POST')
    expect((init as RequestInit).headers).toMatchObject({
      'Content-Type': 'application/json',
      'X-Tenant-API-Key': 'aitkey_xyz',
    })
    expect((init as RequestInit).body).toBe(JSON.stringify({ text: 'Halo' }))
  })

  it('maps 400 error envelope to ApiError with error_code + detail + trace_id', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      errorResponse(400, {
        error_code: 'language_not_allowed',
        detail: "target 'ja' not allowed",
        trace_id: 'abc123',
      }),
    )
    const client = new ApiClient({ baseUrl: '/api', apiKey: 'aitkey_xyz' })

    await expect(client.post('/translate', {})).rejects.toBeInstanceOf(ApiError)
    try {
      await client.post('/translate', {})
    } catch (e) {
      expect((e as ApiError).status).toBe(400)
      expect((e as ApiError).errorCode).toBe('language_not_allowed')
      expect((e as ApiError).traceId).toBe('abc123')
    }
  })

  it('falls back to statusText when error body is not JSON', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('Internal Server Error', { status: 500 }),
    )
    const client = new ApiClient({ baseUrl: '/api', apiKey: 'aitkey_xyz' })

    try {
      await client.post('/translate', {})
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError)
      expect((e as ApiError).status).toBe(500)
      expect((e as ApiError).errorCode).toBe('unknown')
    }
  })

  it('wraps network/fetch failures in NetworkError', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
    const client = new ApiClient({ baseUrl: '/api', apiKey: 'aitkey_xyz' })

    await expect(client.post('/translate', {})).rejects.toBeInstanceOf(NetworkError)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend-demo && npm test -- tests/services/apiClient.test.ts
```
Expected: FAIL — module not found.

- [ ] **Step 3: Create `frontend-demo/src/services/apiClient.ts`**

```typescript
import { ApiError, NetworkError } from './errors'

export interface ApiClientOptions {
  baseUrl: string
  apiKey: string
}

// Thin fetch wrapper. Single responsibility: serialize request body, inject
// auth header, parse response, map error envelope. NOT a full HTTP client —
// realApi composes on top for streaming / domain-specific concerns.
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
      // fetch() rejects on network failure (DNS, refused connection, CORS).
      // Wrap so callers can distinguish "server said no" from "couldn't reach server".
      throw new NetworkError(e)
    }

    if (!resp.ok) {
      // Try to parse the standard ErrorResponse envelope; fall back to raw
      // statusText if the response isn't JSON (proxy 502, etc.).
      let errorCode = 'unknown'
      let detail = resp.statusText
      let traceId: string | undefined
      try {
        const errBody = await resp.json()
        errorCode = typeof errBody.error_code === 'string' ? errBody.error_code : errorCode
        detail = typeof errBody.detail === 'string' ? errBody.detail : detail
        traceId = typeof errBody.trace_id === 'string' ? errBody.trace_id : undefined
      } catch {
        // Not JSON — keep fallback values.
      }
      throw new ApiError({ status: resp.status, errorCode, detail, traceId })
    }

    return (await resp.json()) as TResp
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd frontend-demo && npm test -- tests/services/apiClient.test.ts
```
Expected: 4 PASS.

- [ ] **Step 5: No commit yet** — accumulating Batch B.

---

### Task B2: `responseAdapter.ts` — backend → frontend shape mapping

**Files:**
- Create: `frontend-demo/src/services/responseAdapter.ts`
- Test: `frontend-demo/tests/services/responseAdapter.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend-demo/tests/services/responseAdapter.test.ts`:

```typescript
import { describe, expect, it } from 'vitest'
import {
  adaptActivity,
  adaptResponse,
  type BackendTranslateResponse,
} from '@/services/responseAdapter'

const backendActivity = (overrides: Partial<BackendTranslateResponse['agentic_activities'][0]> = {}) => ({
  name: 'translate',
  agent_type: 'translation',
  status: 'success' as const,
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

const backendResp = (overrides: Partial<BackendTranslateResponse> = {}): BackendTranslateResponse => ({
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

  it('reconstructs violations array from metadata count', () => {
    const adapted = adaptResponse(
      backendResp({ metadata: { trace_id: 't', tokens_input: 0, tokens_output: 0, glossary_violations: 3 } }),
    )
    expect(adapted.glossary_compliance.violations).toHaveLength(3)
  })

  it('uses 0 tokens when metadata missing token counts', () => {
    const adapted = adaptResponse(backendResp({ metadata: { trace_id: 't' } }))
    expect(adapted.input_tokens).toBe(0)
    expect(adapted.output_tokens).toBe(0)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend-demo && npm test -- tests/services/responseAdapter.test.ts
```
Expected: FAIL — module not found.

- [ ] **Step 3: Create `frontend-demo/src/services/responseAdapter.ts`**

```typescript
import type { AgenticActivity, LangCode, ModelId, TranslateResponse } from './types'

// Backend response shape mirror. Lives here because the only consumer is the
// adapter; co-located reduces "where does this type live?" friction.
// This is NOT the same as `types.ts::TranslateResponse` — they diverged after
// sub-proyek B/C/I/K backend evolution. ADR-059: adapter is the swap point.

export interface BackendAgenticActivity {
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
  'en', 'id', 'es', 'fr', 'de', 'ja', 'zh', 'ar', 'pt', 'ru',
])

// Defensive casts: backend may return values outside the frontend's
// closed-set unions (new model IDs, regional lang codes). Falling back to
// safe defaults keeps the UI from crashing on unknown values.
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
  // glossary_compliance: backend returns a float [0..1]; metadata may carry
  // `glossary_violations` as a COUNT (not a list). Reconstruct placeholder
  // violation entries so the frontend type — which expects string[] — stays
  // satisfied. Real violation text is not exposed by backend at this point.
  const violationsRaw = backend.metadata?.glossary_violations
  const violations =
    typeof violationsRaw === 'number'
      ? Array.from({ length: violationsRaw }, (_, i) => `violation_${i + 1}`)
      : []
  const traceId = typeof backend.metadata?.trace_id === 'string'
    ? (backend.metadata.trace_id as string)
    : ''

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

- [ ] **Step 4: Run test to verify it passes**

```bash
cd frontend-demo && npm test -- tests/services/responseAdapter.test.ts
```
Expected: 10 PASS (4 adaptActivity + 6 adaptResponse, counting nested describes).

If your test runner reports a different count, that's fine — what matters is no failures.

- [ ] **Step 5: No commit yet**.

---

### Task B3: `realApi.ts` — synthetic streaming over real `/translate`

**Files:**
- Create: `frontend-demo/src/services/realApi.ts`
- Test: `frontend-demo/tests/services/realApi.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend-demo/tests/services/realApi.test.ts`:

```typescript
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { makeRealApi } from '@/services/realApi'
import type { BackendTranslateResponse } from '@/services/responseAdapter'
import type { AgentEvent } from '@/services/types'

const backendActivity = (name: string, latency = 100, status: 'success' | 'failed' = 'success') => ({
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

const backendResp = (overrides: Partial<BackendTranslateResponse> = {}): BackendTranslateResponse => ({
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
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } }),
  )

beforeEach(() => {
  vi.restoreAllMocks()
  vi.useFakeTimers()
})

describe('realApi.translate', () => {
  it('fires agent_started for both agents before HTTP call', async () => {
    mockFetch(backendResp())
    const events: AgentEvent[] = []
    const api = makeRealApi({ baseUrl: '/api', apiKey: 'aitkey_xyz' })

    const promise = api.translate(
      { text: 'Halo', source_lang: 'id', target_lang: 'en', tenant_id: 't', profile_id: 'p' },
      { onAgentEvent: (e) => events.push(e) },
    )
    // Advance microtask queue so events fire synchronously before fetch settles
    await vi.advanceTimersByTimeAsync(0)

    expect(events.slice(0, 2)).toEqual([
      { type: 'agent_started', agent_name: 'lang_detect_input' },
      { type: 'agent_started', agent_name: 'translate' },
    ])

    // Drain remaining timers to let the replay loop finish.
    await vi.advanceTimersByTimeAsync(200)
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

    await vi.advanceTimersByTimeAsync(0)
    const result = await promise

    expect(result.cached).toBe(true)
    // No setTimeout delay should have been needed — all events present without time advance.
    expect(events.filter((e) => e.type === 'agent_completed')).toHaveLength(2)
  })

  it('fires agent_failed for both and throws on backend error', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ error_code: 'rate_limited', detail: 'slow down', trace_id: 't1' }), {
        status: 429,
        headers: { 'Content-Type': 'application/json' },
      }),
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend-demo && npm test -- tests/services/realApi.test.ts
```
Expected: FAIL — module not found.

- [ ] **Step 3: Create `frontend-demo/src/services/realApi.ts`**

```typescript
import { ApiClient } from './apiClient'
import { adaptResponse, type BackendTranslateResponse } from './responseAdapter'
import type {
  AgentEvent,
  TranslateApi,
  TranslateRequest,
  TranslateResponse,
} from './types'

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

// Factory so the caller can inject baseUrl + apiKey from useApiSettings.
// Returning a TranslateApi keeps the swap with mockApi clean (apiSelector.ts).
export function makeRealApi(opts: { baseUrl: string; apiKey: string }): TranslateApi {
  const client = new ApiClient(opts)

  return {
    async translate(
      req: TranslateRequest,
      { onAgentEvent }: { onAgentEvent: (e: AgentEvent) => void },
    ): Promise<TranslateResponse> {
      // Fire both agent_started immediately — preserves the "parallel agents"
      // visual narrative even though the backend call is one-shot. ADR-060.
      onAgentEvent({ type: 'agent_started', agent_name: 'lang_detect_input' })
      onAgentEvent({ type: 'agent_started', agent_name: 'translate' })

      // Map frontend req → backend payload shape. Backend reads source_lang/
      // target_lang at the top level; model_id (if present) goes into options.
      const body: Record<string, unknown> = {
        text: req.text,
        source_lang: req.source_lang,
        target_lang: req.target_lang,
        tenant_id: req.tenant_id,
        profile_id: req.profile_id,
      }
      if (req.model_id) {
        body.options = { model_id: req.model_id }
      }

      let backendResp: BackendTranslateResponse
      try {
        backendResp = await client.post<BackendTranslateResponse>('/translate', body)
      } catch (e) {
        // Fire failure events so AgentPipeline shows red state on both agents.
        // Then re-throw so TranslationPlayground can map error_code → banner.
        onAgentEvent({ type: 'agent_failed', agent_name: 'lang_detect_input' })
        onAgentEvent({ type: 'agent_failed', agent_name: 'translate' })
        throw e
      }

      const adapted = adaptResponse(backendResp)

      if (backendResp.cached) {
        // Cache hit: no real agent ran. Fire completions immediately so the
        // UI snaps to the result without artificial replay delay.
        for (const activity of adapted.agentic_activities) {
          onAgentEvent({
            type: 'agent_completed',
            agent_name: activity.agent_name,
            activity,
          })
        }
        return adapted
      }

      // Cache miss: replay agent_completed events spaced by activity.latency_ms.
      // Ordering: by completed_at (chronological). If two activities finish at
      // exactly the same time we keep the input order from agentic_activities.
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

- [ ] **Step 4: Run test to verify it passes**

```bash
cd frontend-demo && npm test -- tests/services/realApi.test.ts
```
Expected: 4 PASS.

If timing-related tests are flaky, increase `advanceTimersByTimeAsync` durations or use `vi.runAllTimersAsync()`.

- [ ] **Step 5: No commit yet**.

---

### Task B4: `apiSelector.ts` — mock vs real toggle

**Files:**
- Create: `frontend-demo/src/services/apiSelector.ts`
- Test: `frontend-demo/tests/services/apiSelector.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend-demo/tests/services/apiSelector.test.ts`:

```typescript
import { describe, expect, it, vi, beforeEach } from 'vitest'

describe('apiSelector', () => {
  beforeEach(() => {
    vi.resetModules()
    window.localStorage.clear()
  })

  it('returns mockApi when VITE_API_MODE !== real', async () => {
    vi.stubEnv('VITE_API_MODE', 'mock')
    const { getTranslateApi } = await import('@/services/apiSelector')
    const { mockApi } = await import('@/services/mockApi')
    expect(getTranslateApi()).toBe(mockApi)
  })

  it('returns mockApi fallback when real mode but no apiKey configured', async () => {
    vi.stubEnv('VITE_API_MODE', 'real')
    const { getTranslateApi } = await import('@/services/apiSelector')
    const { mockApi } = await import('@/services/mockApi')
    expect(getTranslateApi()).toBe(mockApi)
  })

  it('returns a real API factory result when real mode + apiKey set', async () => {
    vi.stubEnv('VITE_API_MODE', 'real')
    window.localStorage.setItem(
      'aitegrity_api_settings',
      JSON.stringify({
        baseUrl: '/api',
        apiKey: 'aitkey_xyz',
        profileId: 'profile-aaaaaaaa-bbbb',
        tenantId: 'tenant-cccccccc-dddd',
      }),
    )
    const { getTranslateApi } = await import('@/services/apiSelector')
    const api = getTranslateApi()
    expect(api).toHaveProperty('translate')
    // Not the mock — mockApi has a `_resetCache` method, real doesn't.
    expect((api as { _resetCache?: unknown })._resetCache).toBeUndefined()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend-demo && npm test -- tests/services/apiSelector.test.ts
```
Expected: FAIL — module not found.

- [ ] **Step 3: Create `frontend-demo/src/services/apiSelector.ts`**

```typescript
import { mockApi } from './mockApi'
import { makeRealApi } from './realApi'
import type { TranslateApi } from './types'

const STORAGE_KEY = 'aitegrity_api_settings'

interface MinimalSettings {
  baseUrl?: string
  apiKey?: string
}

function readSettings(): MinimalSettings | null {
  if (typeof window === 'undefined') return null
  const raw = window.localStorage.getItem(STORAGE_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

// Picks the active API per VITE_API_MODE. Re-read every call (not module-init)
// so a Save in SettingsModal takes effect without page reload. Fallback to
// mockApi when real mode but no credentials yet — SettingsModal will prompt.
export function getTranslateApi(): TranslateApi {
  const mode = import.meta.env.VITE_API_MODE
  if (mode !== 'real') return mockApi

  const settings = readSettings()
  if (!settings || !settings.apiKey) {
    return mockApi
  }
  return makeRealApi({
    baseUrl: settings.baseUrl ?? '/api',
    apiKey: settings.apiKey,
  })
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd frontend-demo && npm test -- tests/services/apiSelector.test.ts
```
Expected: 3 PASS.

- [ ] **Step 5: No commit yet**.

---

### Task B5: `.env.local.example` template + commit Batch B

**Files:**
- Create: `frontend-demo/.env.local.example`

- [ ] **Step 1: Create `frontend-demo/.env.local.example`**

```
# Sub-proyek L runtime config. Copy to .env.local (gitignored) and edit.
#
# VITE_API_MODE: 'mock' uses in-memory mockApi.ts (default — demo runs without
#                backend). 'real' wires apiSelector to realApi.ts which hits
#                the backend /translate endpoint. Required: SettingsModal
#                credentials configured (api key + tenant_id + profile_id).
#
VITE_API_MODE=mock

# VITE_API_BASE_URL: used as the default in SettingsModal. Frontend code calls
# `${baseUrl}/translate`. '/api' relies on the Vite dev proxy (vite.config.ts).
# Override with full URL (e.g. https://api.example.com) for prod deployments.
#
VITE_API_BASE_URL=/api
```

- [ ] **Step 2: Verify `.gitignore` excludes `.env.local`**

```bash
cd frontend-demo && cat .gitignore | grep -E "^\.env"
```
Expected: at minimum a `*.local` or `.env.local` line.

If missing, append `.env.local` to `frontend-demo/.gitignore`:

```bash
echo ".env.local" >> frontend-demo/.gitignore
```

- [ ] **Step 3: Full vitest run to verify Batch B**

```bash
cd frontend-demo && npm test -- --run
```
Expected: 22 pre-existing + 11 from Batch A + 21 from Batch B (4 apiClient + 10 responseAdapter + 4 realApi + 3 apiSelector) = 54 pass.

- [ ] **Step 4: Lint + typecheck**

```bash
cd frontend-demo && npm run lint && npm run build
```
Expected: clean.

- [ ] **Step 5: Commit Batch B**

```bash
git add frontend-demo/
git commit -m "$(cat <<'EOF'
feat(sub-proyek L): batch B - API client + adapter + selector

apiClient.ts thin fetch wrapper with X-Tenant-API-Key auth + error envelope
mapping. responseAdapter.ts maps backend TranslateResponse → frontend type
(handles drift from ADR-048 expectations). realApi.ts synthesizes streaming
agentic events from response timing. apiSelector picks mock|real per
VITE_API_MODE env + localStorage settings, fallback to mock when missing.
.env.local.example template.
EOF
)"
```

---

## Section C — Wiring + UX (commit batch 3)

### Task C1: Vite dev proxy `/api/*` → `localhost:8000`

**Files:**
- Modify: `frontend-demo/vite.config.ts`

- [ ] **Step 1: Update `frontend-demo/vite.config.ts`**

Replace existing file with:

```typescript
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
    proxy: {
      // Forward /api/* to backend FastAPI on :8000. Avoids CORS in dev and
      // matches the production-style relative-path routing the frontend uses.
      // Per ADR-063: Vite proxy is the dev path; reverse proxy handles prod.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
})
```

- [ ] **Step 2: Smoke test the proxy**

In one terminal, start the backend:
```bash
uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

In another, start the frontend dev server:
```bash
cd frontend-demo && npm run dev
```

Then probe via curl:
```bash
curl http://localhost:5173/api/health
```
Expected: `{"status":"ok"}` (proxied through). If you get 404 or HTML, the proxy isn't wired correctly.

Kill both servers.

- [ ] **Step 3: No commit yet**.

---

### Task C2: App.tsx + TranslationPlayground.tsx — replace mockApi import + add error UX + use settings

**Files:**
- Modify: `frontend-demo/src/components/TranslationPlayground/index.tsx`
- Modify: `frontend-demo/src/hooks/useTranslationFlow.ts` (verify error propagation)

- [ ] **Step 1: Inspect `useTranslationFlow.ts` to confirm error path**

```bash
cd frontend-demo && cat src/hooks/useTranslationFlow.ts | head -80
```

Verify the flow's catch block sets `state.status = 'error'` AND propagates a typed error. If errors are swallowed without making the typed error available to the caller, we need to extend it.

Look for a pattern like:
```typescript
try {
  ...
  await api.translate(...)
} catch (e) {
  setState({ status: 'error', message: String(e), error: e })  // need `error` field
}
```

If `error` field is missing on the error-status state, extend the state type and propagate the typed error. Otherwise no changes needed here.

If extension needed, add to `useTranslationFlow.ts`:
- In the state union: `{ status: 'error', message: string, error: unknown }`
- In the catch block: `setState({ status: 'error', message: ..., error: e })`

(Tests in `tests/hooks/useTranslationFlow.test.ts` may need an update to assert the `error` field — run that test file and patch any mismatches.)

- [ ] **Step 2: Update `frontend-demo/src/components/TranslationPlayground/index.tsx`** to use settings + show error banner.

Full replacement:

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
import { useApiSettings } from '@/hooks/useApiSettings'
import { ApiError, NetworkError } from '@/services/errors'
import type { LangCode, ModelId, Tenant } from '@/services/types'

interface Props {
  tenant: Tenant
}

// Map error_code → human banner copy. Severity colour drawn from CLAUDE.md
// merah-putih palette per ADR-052 + ADR-064.
function bannerCopyForError(err: unknown): { title: string; severity: 'amber' | 'crimson' } | null {
  if (err instanceof ApiError) {
    if (err.isLanguageNotAllowed()) {
      return { title: err.detail, severity: 'amber' }
    }
    if (err.isAuth()) {
      return {
        title: 'Authentication failed. Check API key in Settings.',
        severity: 'crimson',
      }
    }
    if (err.isRateLimited()) {
      return { title: `Rate limited: ${err.detail}`, severity: 'amber' }
    }
    if (err.isTransient()) {
      return {
        title: 'Translation service temporarily unavailable. Retry.',
        severity: 'crimson',
      }
    }
    return {
      title: `Translation failed: ${err.detail}`,
      severity: 'crimson',
    }
  }
  if (err instanceof NetworkError) {
    return {
      title: 'Cannot reach translation service. Check Settings → Base URL.',
      severity: 'crimson',
    }
  }
  return null
}

export function TranslationPlayground({ tenant }: Props) {
  const { settings, isConfigured } = useApiSettings()
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
    // When configured via Settings, use real backend IDs. Otherwise fall back
    // to the mock tenant id + a placeholder profile_id (mockApi ignores both).
    const apiMode = import.meta.env.VITE_API_MODE ?? 'mock'
    const usingReal = apiMode === 'real' && isConfigured
    flow.start({
      text: inputText,
      source_lang: sourceLang,
      target_lang: targetLang,
      tenant_id: usingReal ? settings.tenantId : tenant.id,
      profile_id: usingReal ? settings.profileId : 'profile-default',
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

  // Banner derived from the typed error if available, otherwise from the
  // raw message string for legacy mock-flow errors.
  const errorBanner =
    flow.state.status === 'error' && 'error' in flow.state
      ? bannerCopyForError(flow.state.error)
      : null
  const errorTraceId =
    flow.state.status === 'error' &&
    'error' in flow.state &&
    flow.state.error instanceof ApiError
      ? flow.state.error.traceId
      : undefined

  return (
    <div className="space-y-6 p-6">
      {errorBanner && (
        <div
          className={
            errorBanner.severity === 'amber'
              ? 'rounded-md border border-accent-amber/50 bg-accent-amber/10 px-4 py-3 text-fg-primary'
              : 'rounded-md border border-accent-crimson/50 bg-accent-crimson/10 px-4 py-3 text-fg-primary'
          }
        >
          <div className="font-medium">{errorBanner.title}</div>
          {errorTraceId && (
            <button
              onClick={() => navigator.clipboard.writeText(errorTraceId)}
              className="mt-1 font-mono text-xs text-fg-muted hover:text-fg-body"
              title="Click to copy"
            >
              trace_id: {errorTraceId}
            </button>
          )}
        </div>
      )}

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

**IMPORTANT** — `flow.start` uses `useTranslationFlow`. That hook today probably imports `mockApi` directly. We need it to call `getTranslateApi()` per invocation so the selector logic kicks in. Read the hook and update:

- Find `import { mockApi } from '@/services/mockApi'` (or similar) in `useTranslationFlow.ts`
- Replace with: `import { getTranslateApi } from '@/services/apiSelector'`
- Replace the call site `mockApi.translate(req, {...})` with: `getTranslateApi().translate(req, {...})`

If the hook also currently relies on `mockApi._resetCache()`, comment-out or guard those calls (they're mock-only).

- [ ] **Step 3: Run tests**

```bash
cd frontend-demo && npm test -- --run
```
Expected: 54+ from earlier batches still pass. If `useTranslationFlow.test.ts` references mockApi directly, it may need a small fix to stub `getTranslateApi()` instead.

- [ ] **Step 4: Lint + typecheck**

```bash
cd frontend-demo && npm run lint && npm run build
```
Expected: clean.

- [ ] **Step 5: No commit yet** — Batch C will be committed after C3.

---

### Task C3: Backend CORS update for `localhost:5173`

**Files:**
- Modify: `src/api/main.py`

- [ ] **Step 1: Update `src/api/main.py`** CORS allowlist.

Replace `_CORS_ORIGINS` block (around line 51-56) with:

```python
# CORS allowlist. Sub-proyek L extends this to include the frontend-demo
# Vite dev server (:5173). Streamlit (:8501) entries removed — demo/app.py
# was deleted in sub-proyek J. SDK landing page (:8001) retained.
_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8001",
    "http://127.0.0.1:8001",
]
```

Also update the docstring at line 12-13:

```python
3. **CORS**: localhost:5173 (frontend-demo Vite, sub-proyek L) and
   localhost:8001 (Phase 7 webpage SDK demo) allowed. Production
   allowlist will be tighter.
```

- [ ] **Step 2: Run backend tests**

```bash
uv run pytest tests/api -v
```
Expected: all green (no test should depend on the old CORS values).

- [ ] **Step 3: Commit Batch C**

```bash
git add frontend-demo/vite.config.ts \
        frontend-demo/src/components/TranslationPlayground/index.tsx \
        frontend-demo/src/hooks/useTranslationFlow.ts \
        src/api/main.py
git commit -m "$(cat <<'EOF'
feat(sub-proyek L): batch C - wiring + error UX + CORS

Vite dev proxy /api/* → localhost:8000. useTranslationFlow consumes
apiSelector instead of mockApi directly. TranslationPlayground reads
profile_id/tenant_id from useApiSettings when in real mode, renders
amber/crimson banner for 5 error_code categories + copy-on-click
trace_id. Backend CORS allowlist extended to localhost:5173, Streamlit
entries removed.
EOF
)"
```

---

## Section D — Documentation (commit batch 4)

### Task D1: ADR-059..064 appended to `docs/adrs.md`

**Files:**
- Modify: `docs/adrs.md`

- [ ] **Step 1: Append the 6 new ADRs at the end of `docs/adrs.md`**

```markdown
- ADR-059: Frontend adapter pattern over types.ts canonical rewrite (sub-proyek L). `frontend-demo/src/services/responseAdapter.ts` maps backend `TranslateResponse` → frontend `TranslateResponse` without forcing alignment. Components stay unchanged; future backend swap edits adapter, not types. Trade-off: type-system not the single source of truth across stack.
- ADR-060: Synthetic streaming for agentic events. Real `/translate` is one-shot; frontend `realApi.ts` replays `agent_completed` events spaced by `activity.latency_ms` to preserve `AgentPipeline` progressive-parallel animation. Cache hit short-circuits replay (all events fire immediately). Future SSE/WebSocket replaces the replay loop.
- ADR-061: Settings modal route, NOT Tab 1 tenant embedding. Backend credentials (api_key + tenant_id + profile_id + baseUrl) configured separately from mock tenant management. Honors ADR-049 "Tab 1 mock-only forever". Trade-off: two unlinked entities (mock tenant vs real credentials); mitigated by gear-icon framing + explicit modal copy ("Backend Connection / Currently using: REAL backend").
- ADR-062: `VITE_API_MODE` env var toggle, default `mock`. Demo runs out-of-box without backend; operator sets `=real` in `.env.local` (gitignored) when ready. `.env.local.example` committed as template. No runtime UI toggle in MVP — `apiSelector.ts` re-reads localStorage settings every call so Settings Save takes effect without page reload.
- ADR-063: Vite dev proxy `/api/*` → `http://localhost:8000`. Frontend code uses relative paths (`/api/translate`). Backend CORS allowlist extended to `localhost:5173` for direct-hit fallback (when user overrides baseUrl to absolute URL in Settings). Production deployment uses reverse proxy with identical path mapping.
- ADR-064: 5 explicit `error_code` → UI banner mapping (`language_not_allowed` → amber, `authentication_failed`/`tenant_not_found` → crimson, `rate_limited` → amber, `upstream_transient` → crimson, generic/network → crimson). Banner positioned ABOVE OutputBox, severity-tinted per ADR-052 palette. Copy-on-click `trace_id` for support correlation. Auto-dismiss on next successful translate.
```

- [ ] **Step 2: No commit yet** — bundled with D2.

---

### Task D2: CLAUDE.md ADR index + Sub-proyek L phase entry + commit Batch D

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/phase-status.md`

- [ ] **Step 1: Update `CLAUDE.md`** "Decision log" section — after the ADR-053..058 line, append:

```markdown
- ADR-059..064: frontend adapter pattern (sub-proyek L), synthetic streaming via response-timing replay, Settings modal route, VITE_API_MODE env toggle, Vite dev proxy + CORS extension, 5 error_code → banner mapping
```

Also bump the ADR count one line above (replace `58 ADRs ditrack` with `64 ADRs ditrack`).

- [ ] **Step 2: Update `CLAUDE.md`** "Phase status" section — after Sub-proyek K line, append:

```markdown
- **Sub-proyek L** (Frontend-demo wired to real /translate, MVP): ✅ 2026-05-22 — realApi.ts adapter implements TranslateApi against backend, synthetic streaming preserves AgentPipeline UX, Settings modal configures credentials (localStorage), Vite dev proxy + VITE_API_MODE toggle (default mock), 5 error_code → banner mapping. End-to-end smoke verified.
```

- [ ] **Step 3: Update `docs/phase-status.md`** — append at the end:

```markdown
### Sub-proyek L — Frontend-Demo ↔ Real Backend Wiring (MVP)
**Status:** ✅ complete (verified 2026-05-22)

- `frontend-demo/src/services/errors.ts` — `ApiError` (with `error_code`/`detail`/`traceId` + `isLanguageNotAllowed`/`isAuth`/`isRateLimited`/`isTransient` predicates) + `NetworkError` (wraps underlying fetch failure cause).
- `frontend-demo/src/services/apiClient.ts` — thin fetch wrapper. Injects `X-Tenant-API-Key`. Parses backend `{error_code, detail, trace_id}` envelope. Wraps network failures in `NetworkError`.
- `frontend-demo/src/services/responseAdapter.ts` — `BackendTranslateResponse` type mirror + `adaptResponse(backend) → TranslateResponse` + `adaptActivity(backend) → AgenticActivity`. Defensive casts on `model_id` + `source_lang/target_lang` (fallback to sonnet/en for unknown values). Reconstructs glossary `violations[]` from `metadata.glossary_violations` count.
- `frontend-demo/src/services/realApi.ts` — `makeRealApi({baseUrl, apiKey})` factory implementing `TranslateApi`. Fires `agent_started` for both agents at request start, POSTs `/translate`, on success replays `agent_completed` events spaced by `activity.latency_ms` (cache hit short-circuits replay). On error fires `agent_failed` for both before throwing `ApiError`.
- `frontend-demo/src/services/apiSelector.ts` — `getTranslateApi()` picks mock vs real per `VITE_API_MODE` env + localStorage settings presence. Re-evaluated every call (no module-init cache) so Settings Save takes effect without reload.
- `frontend-demo/src/hooks/useApiSettings.ts` — `ApiSettings` interface + localStorage-backed hook (`baseUrl`, `apiKey`, `profileId`, `tenantId` + `isConfigured` predicate). Key `aitegrity_api_settings`.
- `frontend-demo/src/components/SettingsModal.tsx` — shadcn Dialog with 4 inputs (baseUrl, apiKey password-masked with show/hide toggle, profileId, tenantId). Save button persists to localStorage. Dialog description displays current `VITE_API_MODE`.
- `frontend-demo/src/components/TopBar.tsx` — added Settings gear button (lucide-react `Settings` icon) with red-dot indicator when `VITE_API_MODE === 'real'` AND not configured.
- `frontend-demo/src/components/TranslationPlayground/index.tsx` — renders amber/crimson banner ABOVE Card on ApiError/NetworkError with copy-on-click trace_id. Reads `profile_id`/`tenant_id` from useApiSettings when in real mode, otherwise falls back to mock tenant.id.
- `frontend-demo/src/App.tsx` — manages SettingsModal open state. Auto-opens on first launch when real mode + not configured.
- `frontend-demo/vite.config.ts` — added `/api/*` proxy → `http://localhost:8000`.
- `frontend-demo/.env.local.example` — `VITE_API_MODE=mock` + `VITE_API_BASE_URL=/api` template.
- `src/api/main.py` — CORS allowlist extended to `localhost:5173` + `127.0.0.1:5173`; removed defunct `localhost:8501` entries.
- **21+ new tests** (5 errors + 4 settings + 2 SettingsModal + 4 apiClient + 10 responseAdapter + 4 realApi + 3 apiSelector). Pre-existing 22 + new = ~50 vitest tests pass. Backend pytest 141 still green.
- **Known limitations / future work:** API key in localStorage XSS-exposed (acceptable per ADR-026 demo trade-off, production needs session-based auth). No JWT login/refresh flow (deferred). Real cascade UI replacing Tab 1 still deferred per ADR-049. SSE/WebSocket real streaming deferred — synthetic replay is the v1 approximation.
- **Unblocks:** stakeholder demos against real LLM responses. Future sub-projects: SSE streaming endpoint + frontend consumer; operator portal with cascade UI + JWT login; multi-account credential switching.
```

- [ ] **Step 4: Verify CLAUDE.md still under 40k threshold**

```bash
cd "C:/Users/zaki/Jack Works/aitegrity-core/ai_translation_v1" && ls -lha CLAUDE.md
```
Expected: well under 40000 bytes.

- [ ] **Step 5: Commit Batch D**

```bash
git add docs/adrs.md CLAUDE.md docs/phase-status.md
git commit -m "$(cat <<'EOF'
docs(sub-proyek L): ADR-059..064 + CLAUDE.md index + phase-status section

6 new ADRs (adapter pattern, synthetic streaming, settings modal route,
VITE_API_MODE toggle, Vite proxy + CORS extension, error_code → banner
mapping). CLAUDE.md ADR index bumped 58 → 64, Sub-proyek L phase entry
added. docs/phase-status.md Sub-proyek L section with full file-level
detail + known limitations.
EOF
)"
```

---

## Section E — Manual smoke verification (operational only, no commit)

### Task E1: End-to-end smoke against real backend

**Files:**
- None (operational only)

- [ ] **Step 1: Prerequisites**

Backend dev DB has been seeded (sub-proyek K Batch D). You have a captured API key + corresponding tenant_id + profile_id.

If you lost the keys, re-seed (it'll print new ones — note that the OLD keys become unrecoverable since the table only stores hashes):
```bash
docker compose exec postgres psql -U postgres -d aitrans -c "TRUNCATE tenant CASCADE;"
uv run python scripts/seed_tenant_data.py
```

Grab one tenant's `tenant_id`, `API_KEY`, and a matching `profile_id`:
```bash
docker compose exec postgres psql -U postgres -d aitrans -c "
  SELECT t.tenant_id, p.profile_id, p.allowed_language
  FROM tenant t
  JOIN tenant_profile p ON p.tenant_name = t.tenant_name
  WHERE p.allowed_language @> ARRAY['id','en']
  ORDER BY t.company_name LIMIT 1;
"
```

- [ ] **Step 2: Start backend**

```bash
uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

In another terminal verify health:
```bash
curl http://localhost:8000/health
```

- [ ] **Step 3: Configure frontend env**

```bash
cd frontend-demo
cp .env.local.example .env.local
```

Edit `.env.local`:
```
VITE_API_MODE=real
VITE_API_BASE_URL=/api
```

- [ ] **Step 4: Start frontend**

```bash
cd frontend-demo && npm run dev
```

Browse to `http://localhost:5173`.

- [ ] **Step 5: Visual checklist**

1. SettingsModal auto-opens (real mode + no creds). Title: "Backend Connection". "Currently using: REAL backend" in accent-emerald color.
2. Paste API key (`aitkey_...`), profile_id (`profile-XXXXXXXX-XXXX`), tenant_id (`tenant-XXXXXXXX-XXXX`). Leave baseUrl as `/api`. Click Save.
3. Modal closes. TopBar gear icon shows NO red dot (configured).
4. Navigate to "Translation Playground" tab. Type "Halo, selamat pagi". Source = Indonesian, target = English. Click Translate.
5. AgentPipeline: lang_detect_input + translate both go "running" → after ~100-300ms lang_detect_input completes → after ~1-2s translate completes.
6. OutputBox shows real translation (e.g. "Hello, good morning"). Cost shown (e.g. $0.0008). Latency shown.
7. PayloadViewer expands to show real backend JSON (translation field, agentic_activities array, metadata.trace_id).
8. Change target language to Japanese (ja, not in allowed_language). Click Translate.
9. AMBER banner appears ABOVE Card: "target 'ja' not allowed for this profile..." with `trace_id: ...` copyable line below.
10. Change target back to English. Click Translate. Banner dismisses. Result is cached (cached=true badge, latency < 50ms).
11. Reload browser. Modal does NOT auto-open (credentials persist in localStorage). Translation Playground works without re-config.
12. Edit `.env.local` to `VITE_API_MODE=mock`. Reload. Settings modal shows "Currently using: MOCK in-memory" in accent-amber. Translate hits mock (instant fake response, no backend log row).

- [ ] **Step 6: Negative-path check — bad API key**

In Settings modal, change the API key to `aitkey_invalid_xxx`. Save. Click Translate.

Expected: CRIMSON banner "Authentication failed. Check API key in Settings."

Restore correct key. Translation works again.

- [ ] **Step 7: Negative-path check — backend offline**

Kill the backend server (Ctrl+C in its terminal). Click Translate.

Expected: CRIMSON banner "Cannot reach translation service. Check Settings → Base URL."

Restart backend. Translation works again.

- [ ] **Step 8: No commit** — operational only. Capture any unexpected behavior in a follow-up issue; don't fix here.

---

## Self-Review Checklist

Run once after all tasks complete:

- [ ] **Spec coverage**: every spec section (§1 architecture, §2 file map, §3 keputusan utama, §5 component interfaces, §6 CORS, §7 tests, §8 smoke checklist, §9 ADRs) maps to a task above.
- [ ] **Placeholder scan**: no "TBD"/"TODO"/"implement appropriate" strings in any task above.
- [ ] **Type consistency**:
  - `ApiSettings` shape: `{baseUrl, apiKey, profileId, tenantId}` consistent in Tasks A2 + A3 + B4 + C2
  - `ApiError` predicates: `isLanguageNotAllowed`/`isAuth`/`isRateLimited`/`isTransient` consistent in A1 (impl) + B1 (test) + C2 (consumer)
  - `BackendTranslateResponse` field names match real backend schema in B2 + B3
  - `getTranslateApi()` named consistently (not `getApi` or `selectApi`)
- [ ] **All commits ahead of `origin/main`**: `git log origin/main..HEAD --oneline` shows 4 sub-proyek L commits.
- [ ] **`.env.local` gitignored**: not in commit diff.

---

## Plan Complete

Plan saved to `docs/superpowers/plans/2026-05-22-frontend-real-api-wiring.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per batch, review between batches, fast iteration. Matches sub-proyek K pattern: 6 batches × 3 subagents (impl + spec review + code-quality review) = ~18 dispatches.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints. Faster wall-clock but main session context grows.

Which approach?
