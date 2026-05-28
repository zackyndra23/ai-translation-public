import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronDown, Copy, CheckCircle2 } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { JsonHighlighter } from './JsonHighlighter'
import type { TranslateResponse } from '@/services/types'
import { cn } from '@/lib/cn'

interface Props {
  payload: TranslateResponse | null
}

export function PayloadViewer({ payload }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [copied, setCopied] = useState(false)

  // Copy stringified payload to clipboard; show checkmark for 1.5s then reset.
  // navigator.clipboard is async; we fire-and-forget the promise since
  // the UI feedback (setCopied) handles user perception and failures are silent.
  const copy = () => {
    if (!payload) return
    navigator.clipboard.writeText(JSON.stringify(payload, null, 2)).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  return (
    <Card className="bg-bg-card border-border-default overflow-hidden">
      <button
        onClick={() => setExpanded((x) => !x)}
        className="flex w-full items-center justify-between border-b border-border-default px-6 py-4 hover:bg-bg-elevated/30"
      >
        <div className="flex items-center gap-2">
          <h2 className="text-base font-medium text-fg-primary">Full Payload</h2>
          {!payload && (
            <span className="text-xs text-fg-muted">— No payload yet</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {payload && (
            <span
              onClick={(e) => {
                e.stopPropagation()
                copy()
              }}
              className="flex items-center gap-1 rounded px-2 py-1 text-xs text-fg-muted hover:bg-bg-elevated hover:text-fg-primary"
            >
              {copied ? <CheckCircle2 className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
              {copied ? 'Copied!' : 'Copy'}
            </span>
          )}
          <ChevronDown
            className={cn(
              'h-4 w-4 text-fg-muted transition-transform',
              expanded && 'rotate-180',
            )}
          />
        </div>
      </button>

      {/* AnimatePresence + motion.div give a smooth height-based collapse/expand.
          initial={false} prevents the exit animation on first mount (nothing to
          collapse since it starts closed). */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="overflow-hidden"
          >
            {payload ? (
              <JsonHighlighter value={payload} />
            ) : (
              <div className="px-6 py-8 text-center text-sm text-fg-muted">
                No payload yet — run a translation
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </Card>
  )
}
