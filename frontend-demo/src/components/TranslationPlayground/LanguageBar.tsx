import { motion } from 'framer-motion'
import { ArrowLeftRight } from 'lucide-react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import {
  LANGUAGE_LABELS,
  MODEL_LABELS,
  type LangCode,
  type ModelId,
} from '@/services/types'

interface Props {
  sourceLang: LangCode
  targetLang: LangCode
  modelId: ModelId
  onSourceChange: (l: LangCode) => void
  onTargetChange: (l: LangCode) => void
  onSwap: () => void
  onModelChange: (m: ModelId) => void
}

const LANGS: LangCode[] = ['en', 'id', 'es', 'fr', 'de', 'ja', 'zh', 'ar', 'pt', 'ru']
const MODELS: ModelId[] = [
  'claude-haiku-4-5',
  'claude-sonnet-4-6',
  'claude-opus-4-7',
  'gpt-4o-mini',
]

export function LanguageBar({
  sourceLang,
  targetLang,
  modelId,
  onSourceChange,
  onTargetChange,
  onSwap,
  onModelChange,
}: Props) {
  return (
    <div className="flex items-center gap-3 border-b border-border-default px-6 py-4">
      <LangSelect value={sourceLang} onChange={onSourceChange} />

      <motion.button
        onClick={onSwap}
        whileTap={{ scale: 0.92, rotate: 180 }}
        transition={{ type: 'spring', stiffness: 300 }}
        className="grid h-9 w-9 place-items-center rounded-lg border border-border-default text-fg-muted hover:bg-bg-elevated hover:text-fg-primary"
      >
        <ArrowLeftRight className="h-4 w-4" />
      </motion.button>

      <LangSelect value={targetLang} onChange={onTargetChange} />

      <div className="ml-auto">
        <Select value={modelId} onValueChange={(v) => onModelChange(v as ModelId)}>
          <SelectTrigger className="bg-bg-base border-border-default text-fg-body w-56">
            <SelectValue>
              <div className="flex items-center gap-2">
                <span className="text-fg-body text-sm">{MODEL_LABELS[modelId]}</span>
                <Badge variant="outline" className="border-border-default font-mono text-[10px] text-fg-muted">
                  {modelId}
                </Badge>
              </div>
            </SelectValue>
          </SelectTrigger>
          <SelectContent className="bg-bg-elevated border-border-default">
            {MODELS.map((m) => (
              <SelectItem key={m} value={m}>
                <span className="text-fg-body">{MODEL_LABELS[m]}</span>
                <span className="ml-2 font-mono text-xs text-fg-muted">{m}</span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  )
}

function LangSelect({
  value,
  onChange,
}: {
  value: LangCode
  onChange: (l: LangCode) => void
}) {
  return (
    <Select value={value} onValueChange={(v) => onChange(v as LangCode)}>
      <SelectTrigger className="bg-bg-base border-border-default text-fg-primary w-44">
        <SelectValue>
          <span className="mr-2">{LANGUAGE_LABELS[value].flag}</span>
          <span>{LANGUAGE_LABELS[value].name}</span>
          <span className="ml-2 font-mono text-xs text-fg-muted">{value.toUpperCase()}</span>
        </SelectValue>
      </SelectTrigger>
      <SelectContent className="bg-bg-elevated border-border-default">
        {LANGS.map((l) => (
          <SelectItem key={l} value={l}>
            <span className="mr-2">{LANGUAGE_LABELS[l].flag}</span>
            {LANGUAGE_LABELS[l].name}{' '}
            <span className="ml-2 font-mono text-xs text-fg-muted">{l.toUpperCase()}</span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
