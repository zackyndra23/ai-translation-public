import { describe, it, expect, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useDebouncedValue } from './useDebouncedValue'

describe('useDebouncedValue', () => {
  it('returns initial value immediately', () => {
    const { result } = renderHook(() => useDebouncedValue('hello', 500))
    expect(result.current).toBe('hello')
  })

  it('debounces updates by the delay', () => {
    vi.useFakeTimers()
    try {
      const { result, rerender } = renderHook(
        ({ v }: { v: string }) => useDebouncedValue(v, 500),
        { initialProps: { v: 'a' } },
      )
      expect(result.current).toBe('a')
      rerender({ v: 'b' })
      expect(result.current).toBe('a') // still old
      act(() => {
        vi.advanceTimersByTime(499)
      })
      expect(result.current).toBe('a')
      act(() => {
        vi.advanceTimersByTime(1)
      })
      expect(result.current).toBe('b')
    } finally {
      vi.useRealTimers()
    }
  })
})
