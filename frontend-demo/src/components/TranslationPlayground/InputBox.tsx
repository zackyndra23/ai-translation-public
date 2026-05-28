import { useEffect } from 'react'
import { AnimatePresence } from 'framer-motion'
import { X } from 'lucide-react'
import { LANGUAGE_LABELS, type LangCode } from '@/services/types'
import { detectLanguage } from '@/services/languageDetector'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { LanguageMismatchBanner } from './LanguageMismatchBanner'
import { cn } from '@/lib/cn'

interface Props {
  value: string
  sourceLang: LangCode
  onChange: (v: string) => void
  onSwitchSource: (l: LangCode) => void
  onDetectionChange?: (detected: LangCode | null, confidence: number) => void
}

export function InputBox({
  value,
  sourceLang,
  onChange,
  onSwitchSource,
  onDetectionChange,
}: Props) {
  // Debounce language detection so we don't run it on every keystroke —
  // 500ms delay keeps it responsive without hammering the detector on
  // fast typists (ADR-015: NFC normalisation happens inside detectLanguage).
  const debouncedValue = useDebouncedValue(value, 500)
  const detection = debouncedValue.trim().length > 4 ? detectLanguage(debouncedValue) : null

  // Notify parent about the latest detection result whenever it changes
  // so the state machine or parent can record it in the pipeline request.
  useEffect(() => {
    onDetectionChange?.(detection?.lang ?? null, detection?.confidence ?? 0)
  }, [detection?.lang, detection?.confidence, onDetectionChange])

  const charCount = value.length
  const tokenEstimate = Math.max(0, Math.round(value.length / 3.7))

  // Show the mismatch banner only when confidence is high enough to avoid
  // noisy false-positive alerts (e.g. very short English words scoring 0.4 on Indonesian).
  const showMismatch =
    detection != null && detection.confidence > 0.5 && detection.lang !== sourceLang
  const longWarning = charCount > 5000

  return (
    <div className="flex flex-col">
      <AnimatePresence>
        {showMismatch && detection && (
          <LanguageMismatchBanner
            selectedLang={sourceLang}
            detectedLang={detection.lang}
            onSwitchSource={() => onSwitchSource(detection.lang)}
          />
        )}
      </AnimatePresence>

      {longWarning && (
        <div className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-xs text-amber-200">
          Long input — translation may be slower or hit token limits.
        </div>
      )}

      <div className="relative rounded-xl border border-border-default bg-bg-card">
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Enter text to translate..."
          className={cn(
            'w-full resize-none rounded-xl bg-transparent p-4 text-fg-primary placeholder:text-fg-placeholder',
            'min-h-[180px] max-h-[400px] overflow-y-auto focus:outline-none',
          )}
        />

        <div className="flex items-center justify-between border-t border-border-default px-4 py-2 text-xs text-fg-muted">
          <div>
            {value.length > 0 ? (
              <button
                onClick={() => onChange('')}
                className="flex items-center gap-1 hover:text-fg-body"
              >
                <X className="h-3 w-3" /> Clear
              </button>
            ) : (
              <span>&nbsp;</span>
            )}
          </div>
          <div className="font-mono">
            {charCount} chars · ~{tokenEstimate} tokens
          </div>
        </div>
      </div>

      {/* Show a subtle detection notice when language matches — no banner needed,
          just a soft confirmation that detection is working. */}
      {detection && !showMismatch && (
        <div className="mt-2 text-xs text-fg-muted">
          Detected: <span className="text-fg-body">{LANGUAGE_LABELS[detection.lang].name}</span>{' '}
          · {(detection.confidence * 100).toFixed(0)}% confidence
        </div>
      )}
    </div>
  )
}
