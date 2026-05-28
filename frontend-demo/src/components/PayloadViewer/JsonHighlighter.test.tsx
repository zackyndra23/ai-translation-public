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
