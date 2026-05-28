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
