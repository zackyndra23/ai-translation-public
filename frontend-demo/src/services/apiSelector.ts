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
    return JSON.parse(raw) as MinimalSettings
  } catch {
    // Corrupt JSON — treat as not configured. SettingsModal can be reopened
    // to overwrite with valid values.
    return null
  }
}

// Picks the active API per VITE_API_MODE. Re-read localStorage every call
// (NOT a module-init cache) so a Save in SettingsModal takes effect without
// a page reload. Fallback to mockApi when real mode but no credentials yet —
// SettingsModal will surface the gear-button red dot and auto-open in App.tsx.
export function getTranslateApi(): TranslateApi {
  const mode = import.meta.env.VITE_API_MODE
  if (mode !== 'real') return mockApi

  const settings = readSettings()
  if (!settings || !settings.apiKey) {
    // Visible warning so the silent fallback doesn't mislead a developer who
    // expects real-mode behavior. The SettingsModal red-dot UI also signals
    // this in the UI; the console.warn helps when reading devtools logs.
    console.warn(
      '[apiSelector] VITE_API_MODE=real but no apiKey configured; falling back to mockApi. ' +
        'Configure via Settings modal (gear icon in TopBar).',
    )
    return mockApi
  }
  // settings.baseUrl normally wins (set via SettingsModal). If user wiped it
  // manually, fall through to VITE_API_BASE_URL env default, then '/api'.
  return makeRealApi({
    baseUrl:
      settings.baseUrl ??
      (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
      '/api',
    apiKey: settings.apiKey,
  })
}
