import { createContext, useContext, useState, type ReactNode } from 'react'

export interface ApiSettings {
  baseUrl: string
  apiKey: string
  profileId: string
  tenantId: string
}

const STORAGE_KEY = 'aitegrity_api_settings'

// Read default baseUrl from VITE_API_BASE_URL env var (documented in
// .env.local.example) so operators can override the default without editing
// frontend source. Falls back to '/api' for the Vite dev proxy path.
const DEFAULT_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '/api'

const DEFAULTS: ApiSettings = {
  baseUrl: DEFAULT_BASE_URL,
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

// Context shape exposed to consumers. Identical surface to the previous
// useApiSettings hook return value — call sites don't change.
interface ApiSettingsContextValue {
  settings: ApiSettings
  save: (next: Partial<ApiSettings>) => void
  isConfigured: boolean
}

const ApiSettingsContext = createContext<ApiSettingsContextValue | null>(null)

// Single source of truth for backend credentials. Provider wraps the app so
// every consumer (TopBar red-dot, SettingsModal form, App auto-open effect)
// shares the same state — fixes the multi-instance staleness bug where each
// useApiSettings() call previously created its own useState, so SettingsModal
// could save() while TopBar's red dot remained showing.
export function ApiSettingsProvider({ children }: { children: ReactNode }) {
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

  return (
    <ApiSettingsContext.Provider
      value={{ settings, save, isConfigured: checkConfigured(settings) }}
    >
      {children}
    </ApiSettingsContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useApiSettings(): ApiSettingsContextValue {
  const ctx = useContext(ApiSettingsContext)
  if (ctx === null) {
    throw new Error('useApiSettings must be used within <ApiSettingsProvider>')
  }
  return ctx
}
