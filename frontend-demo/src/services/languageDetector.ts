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
