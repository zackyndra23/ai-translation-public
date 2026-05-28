import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { Tenant } from '@/services/types'
import { cn } from '@/lib/cn'
import { Settings as SettingsIcon } from 'lucide-react'
import { useApiSettings } from '@/hooks/useApiSettings'

interface Props {
  tenants: Tenant[]
  activeTenantId: string | null
  onSelectTenant: (id: string) => void
  onOpenSettings: () => void
}

// Owl mark — Integrity Indonesia's trademark mascot, stylised as a flat
// geometric silhouette so it reads at 20–36px. Matches the favicon shape.
function OwlMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      <path
        d="M16 4 L23 8 L26 16 L23 24 L16 26 L9 24 L6 16 L9 8 Z"
        fill="currentColor"
      />
      <circle cx="12" cy="14" r="3" fill="#ffffff" />
      <circle cx="20" cy="14" r="3" fill="#ffffff" />
      <circle cx="12" cy="14" r="1.4" fill="#0a0a0c" />
      <circle cx="20" cy="14" r="1.4" fill="#0a0a0c" />
      <path d="M16 17 L14.5 19 L17.5 19 Z" fill="#0a0a0c" />
    </svg>
  )
}

export function TopBar({ tenants, activeTenantId, onSelectTenant, onOpenSettings }: Props) {
  const active = tenants.find((t) => t.id === activeTenantId) ?? null

  return (
    <header
      className={cn(
        'sticky top-0 z-50 flex items-center justify-between px-6 py-4',
        'border-b border-border-default bg-bg-base/80 backdrop-blur-md',
      )}
    >
      <div className="flex items-center gap-3">
        <div className="grid h-9 w-9 place-items-center rounded-lg bg-bg-elevated text-accent-red">
          <OwlMark className="h-6 w-6" />
        </div>
        <div className="text-lg font-medium tracking-tight text-fg-primary">
          AI Translation <span className="text-fg-muted">by</span>{' '}
          <span className="text-accent-red">Integrity</span>
        </div>
      </div>

      <div className="flex items-center gap-4">
        {active && (
          <Select value={activeTenantId ?? ''} onValueChange={onSelectTenant}>
            <SelectTrigger className="w-64 bg-bg-card border-border-default text-fg-body">
              <SelectValue>
                <div className="flex items-center gap-2">
                  <span className="text-fg-primary">{active.name}</span>
                  <span className="font-mono text-xs text-fg-muted">
                    {active.id}
                  </span>
                </div>
              </SelectValue>
            </SelectTrigger>
            <SelectContent className="bg-bg-elevated border-border-default">
              {tenants.map((t) => (
                <SelectItem key={t.id} value={t.id}>
                  <div className="flex items-center gap-2">
                    <span>{t.name}</span>
                    <span className="font-mono text-xs text-fg-muted">
                      {t.id}
                    </span>
                  </div>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        {/* Settings gear — opens credentials modal. Red dot indicator when settings
            not configured AND VITE_API_MODE === 'real' (real backend wants creds but
            user hasn't provided any). */}
        <SettingsGearButton onClick={onOpenSettings} />
        <div className="grid h-9 w-9 place-items-center rounded-full bg-bg-elevated text-sm text-fg-muted">
          ZA
        </div>
      </div>
    </header>
  )
}

function SettingsGearButton({ onClick }: { onClick: () => void }) {
  const { isConfigured } = useApiSettings()
  const apiMode = import.meta.env.VITE_API_MODE ?? 'mock'
  const showAlert = apiMode === 'real' && !isConfigured

  return (
    <button
      onClick={onClick}
      className={cn(
        'relative grid h-9 w-9 place-items-center rounded-lg bg-bg-elevated text-fg-muted',
        'hover:text-fg-primary hover:bg-bg-card transition-colors',
      )}
      aria-label="Open settings"
    >
      <SettingsIcon className="h-5 w-5" />
      {showAlert && (
        <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-accent-red" />
      )}
    </button>
  )
}
