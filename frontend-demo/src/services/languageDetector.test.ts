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
