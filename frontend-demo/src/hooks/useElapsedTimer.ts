import { useEffect, useRef, useState } from 'react'

// Ticks every 30ms while `active` is true, returns elapsed ms since
// activation. Resets to 0 on each (false → true) transition.
export function useElapsedTimer(active: boolean): number {
  const [elapsed, setElapsed] = useState(0)
  const startRef = useRef<number | null>(null)

  useEffect(() => {
    if (!active) {
      startRef.current = null
      setElapsed(0)
      return
    }
    startRef.current = Date.now()
    setElapsed(0)
    const id = setInterval(() => {
      if (startRef.current != null) {
        setElapsed(Date.now() - startRef.current)
      }
    }, 30)
    return () => clearInterval(id)
  }, [active])

  return elapsed
}
