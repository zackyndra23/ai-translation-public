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
