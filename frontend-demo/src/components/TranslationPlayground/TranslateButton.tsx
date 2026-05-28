import { motion } from 'framer-motion'
import { Loader2, Sparkles } from 'lucide-react'
import { cn } from '@/lib/cn'

interface Props {
  disabled: boolean
  loading: boolean
  onClick: () => void
}

// Framer Motion `whileTap` gives a tactile press feel; we skip it when
// disabled/loading so the button doesn't animate on a no-op click.
export function TranslateButton({ disabled, loading, onClick }: Props) {
  return (
    <motion.button
      onClick={onClick}
      disabled={disabled || loading}
      whileTap={disabled || loading ? undefined : { scale: 0.98 }}
      className={cn(
        'mt-6 w-full rounded-xl bg-red-rose px-6 py-3 text-sm font-medium text-white',
        'transition-opacity',
        (disabled || loading) && 'opacity-50',
        !disabled && !loading && 'hover:opacity-90',
      )}
    >
      <div className="flex items-center justify-center gap-2">
        {loading ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            Translating...
          </>
        ) : (
          <>
            <Sparkles className="h-4 w-4" />
            Translate
          </>
        )}
      </div>
    </motion.button>
  )
}
