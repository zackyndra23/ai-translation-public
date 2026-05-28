import { AlertCircle } from 'lucide-react'
import { motion } from 'framer-motion'
import { LANGUAGE_LABELS, type LangCode } from '@/services/types'
import { Button } from '@/components/ui/button'

interface Props {
  selectedLang: LangCode
  detectedLang: LangCode
  onSwitchSource: () => void
}

export function LanguageMismatchBanner({
  selectedLang,
  detectedLang,
  onSwitchSource,
}: Props) {
  return (
    <motion.div
      data-testid="mismatch-banner"
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      className="mb-3 flex items-center gap-3 rounded-lg border border-accent-amber/30 bg-accent-amber/10 px-4 py-3 animate-shake"
    >
      <AlertCircle className="h-4 w-4 shrink-0 text-accent-amber" />
      <div className="flex-1 text-sm text-[#fef3c7]">
        Detected language is <strong>{LANGUAGE_LABELS[detectedLang].name}</strong>, but
        you selected <strong>{LANGUAGE_LABELS[selectedLang].name}</strong>. Consider switching.
      </div>
      <Button
        onClick={onSwitchSource}
        size="sm"
        variant="outline"
        aria-label={`Switch source to ${LANGUAGE_LABELS[detectedLang].name}`}
        className="border-accent-amber/40 bg-transparent text-[#fef3c7] hover:bg-accent-amber/20"
      >
        Switch source
      </Button>
    </motion.div>
  )
}
