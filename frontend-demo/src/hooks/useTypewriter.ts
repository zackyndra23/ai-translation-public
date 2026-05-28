import { useEffect, useRef, useState } from 'react'

export interface TypewriterState {
  displayed: string
  isComplete: boolean
}

// Uses setInterval (not chained setTimeout) so that fake-timer advancement
// in tests can advance multiple ticks in a single `advanceTimersByTime` call
// without needing intermediate React re-renders per character.
export function useTypewriter(
  target: string,
  speedMs = 25,
): TypewriterState {
  const [index, setIndex] = useState(0)
  // Track the target at effect-setup time so the interval closure sees
  // the latest target even if speedMs stays the same.
  const targetRef = useRef(target)
  targetRef.current = target

  // Reset index immediately when target changes.
  useEffect(() => {
    setIndex(0)
  }, [target])

  useEffect(() => {
    if (index >= target.length) return
    const id = setInterval(() => {
      setIndex((i) => {
        if (i >= targetRef.current.length) {
          clearInterval(id)
          return i
        }
        return i + 1
      })
    }, speedMs)
    return () => clearInterval(id)
    // Re-run when target changes (index reset to 0 triggers this) or speedMs changes.
  }, [index, target, speedMs])

  return {
    displayed: target.slice(0, index),
    isComplete: index >= target.length,
  }
}
