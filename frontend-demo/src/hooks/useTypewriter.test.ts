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
