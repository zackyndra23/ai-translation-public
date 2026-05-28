import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Copy, RotateCw, Volume2, CheckCircle2, AlertCircle } from 'lucide-react'
import { useTypewriter } from '@/hooks/useTypewriter'
import { cn } from '@/lib/cn'

// Microcopy cycles while the translation is running to give the user a sense
// that work is progressing through multiple agent stages (ADR-031).
const LOADING_MICROCOPY = [
  'Tokenizing input...',
  'Identifying language patterns...',
  'Routing through translation agent...',
  'Polishing output...',
]

interface Props {
  translatedText: string | null
  status: 'idle' | 'running' | 'done' | 'error'
  errorMessage?: string
  onCopy?: () => void
  onRegenerate?: () => void
}

export function OutputBox({
  translatedText,
  status,
  errorMessage,
  onCopy,
  onRegenerate,
}: Props) {
  const [microcopyIdx, setMicrocopyIdx] = useState(0)
  const [copyFlash, setCopyFlash] = useState(false)

  // Cycle microcopy every 800ms while running to create the illusion of
  // multi-step progress even though the mock API returns a single promise.
  useEffect(() => {
    if (status !== 'running') return
    const id = setInterval(() => {
      setMicrocopyIdx((i) => (i + 1) % LOADING_MICROCOPY.length)
    }, 800)
    return () => clearInterval(id)
  }, [status])

  // useTypewriter feeds chars one at a time at 25ms/char so the result
  // animates in naturally rather than snapping to full text (ADR-033 demo aesthetic).
  const { displayed } = useTypewriter(
    status === 'done' && translatedText ? translatedText : '',
    25,
  )

  const handleCopy = () => {
    if (!translatedText) return
    navigator.clipboard.writeText(translatedText).then(() => {
      setCopyFlash(true)
      // Flash the checkmark icon for 1.5s before reverting to Copy icon
      setTimeout(() => setCopyFlash(false), 1500)
      onCopy?.()
    })
  }

  return (
    <div className="flex flex-col rounded-xl border border-border-default bg-bg-card">
      <div className="min-h-[180px] max-h-[400px] overflow-y-auto p-4">
        {status === 'idle' && (
          <p className="text-fg-placeholder">Translation will appear here</p>
        )}

        {status === 'running' && (
          <div className="space-y-3">
            {/* Shimmer skeleton lines mirror the expected output length */}
            <div className="space-y-2">
              <div className="shimmer-bg h-3 w-4/5 rounded" />
              <div className="shimmer-bg h-3 w-3/4 rounded" />
              <div className="shimmer-bg h-3 w-2/3 rounded" />
            </div>
            <AnimatePresence mode="wait">
              <motion.div
                key={microcopyIdx}
                initial={{ opacity: 0 }}
                animate={{ opacity: 0.7 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="text-xs text-fg-muted"
              >
                {LOADING_MICROCOPY[microcopyIdx]}
              </motion.div>
            </AnimatePresence>
          </div>
        )}

        {status === 'done' && (
          <p className="whitespace-pre-wrap text-fg-primary">{displayed}</p>
        )}

        {status === 'error' && (
          <div className="flex items-start gap-2 text-accent-crimson">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <div className="font-medium">Translation failed</div>
              <div className="mt-1 text-sm opacity-90">{errorMessage}</div>
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center justify-end gap-1 border-t border-border-default px-3 py-2">
        <ActionBtn icon={copyFlash ? CheckCircle2 : Copy} onClick={handleCopy} disabled={!translatedText} title="Copy" />
        <ActionBtn icon={Volume2} onClick={() => {}} disabled={!translatedText} title="Listen" />
        <ActionBtn icon={RotateCw} onClick={onRegenerate} disabled={!onRegenerate} title="Regenerate" />
      </div>
    </div>
  )
}

function ActionBtn({
  icon: Icon,
  onClick,
  disabled,
  title,
}: {
  icon: React.ComponentType<{ className?: string }>
  onClick?: () => void
  disabled?: boolean
  title: string
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={cn(
        'rounded p-1.5 text-fg-muted transition-colors',
        disabled
          ? 'opacity-40'
          : 'hover:bg-bg-elevated hover:text-fg-primary',
      )}
    >
      <Icon className="h-4 w-4" />
    </button>
  )
}
