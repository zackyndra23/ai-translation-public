import { AnimatePresence, motion } from 'framer-motion'
import { Edit3, Trash2, CheckCircle2 } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import type { Tenant } from '@/services/types'
import { formatRelativeTime } from '@/lib/format'
import { cn } from '@/lib/cn'

interface Props {
  tenants: Tenant[]
  activeTenantId: string | null
  recentlyCreated: string | null
  onSelect: (id: string) => void
  onDelete: (id: string) => void
}

export function TenantTable({
  tenants,
  activeTenantId,
  recentlyCreated,
  onSelect,
  onDelete,
}: Props) {
  return (
    <Card className="bg-bg-card border-border-default overflow-hidden">
      <div className="border-b border-border-default px-6 py-4">
        <h2 className="text-lg font-medium text-fg-primary">Tenants</h2>
        <p className="mt-1 text-sm text-fg-muted">
          {tenants.length} tenant{tenants.length === 1 ? '' : 's'} configured
        </p>
      </div>

      <table className="w-full">
        <thead>
          <tr className="border-b border-border-default text-left text-xs uppercase tracking-wider text-fg-muted">
            <th className="px-6 py-3 font-medium">Name</th>
            <th className="px-6 py-3 font-medium">Tenant ID</th>
            <th className="px-6 py-3 font-medium">Created</th>
            <th className="px-6 py-3 font-medium">Status</th>
            <th className="px-6 py-3 font-medium">Tier</th>
            <th className="px-6 py-3 font-medium text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          <AnimatePresence initial={false}>
            {tenants.map((t) => (
              <motion.tr
                key={t.id}
                layout
                initial={{ opacity: 0, y: -10 }}
                animate={{
                  opacity: 1,
                  y: 0,
                  boxShadow:
                    t.id === recentlyCreated
                      ? '0 0 0 1px #b91c1c inset, 0 0 20px #b91c1c44'
                      : 'none',
                }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.3 }}
                className={cn(
                  'group border-b border-border-default text-sm transition-colors hover:bg-bg-elevated/40',
                  activeTenantId === t.id && 'bg-bg-elevated/30',
                )}
              >
                <td className="px-6 py-3 text-fg-primary">
                  <div className="flex items-center gap-2">
                    {activeTenantId === t.id && (
                      <CheckCircle2 className="h-3.5 w-3.5 text-accent-red" />
                    )}
                    {t.name}
                  </div>
                </td>
                <td className="px-6 py-3 font-mono text-xs text-fg-muted">
                  {t.id}
                </td>
                <td className="px-6 py-3 text-fg-muted">
                  {formatRelativeTime(t.created_at)}
                </td>
                <td className="px-6 py-3">
                  <Badge
                    variant="outline"
                    className={cn(
                      'border-0 font-normal',
                      t.status === 'active'
                        ? 'bg-accent-emerald/15 text-accent-emerald'
                        : 'bg-bg-elevated text-fg-muted',
                    )}
                  >
                    {t.status}
                  </Badge>
                </td>
                <td className="px-6 py-3 text-fg-body">{t.model_tier}</td>
                <td className="px-6 py-3 text-right">
                  <div className="invisible flex justify-end gap-1 group-hover:visible">
                    <button
                      onClick={() => onSelect(t.id)}
                      className="rounded p-1.5 text-fg-muted hover:bg-bg-elevated hover:text-fg-primary"
                      title="Set active"
                    >
                      <CheckCircle2 className="h-4 w-4" />
                    </button>
                    <button
                      className="rounded p-1.5 text-fg-muted hover:bg-bg-elevated hover:text-fg-primary"
                      title="Edit (mock)"
                    >
                      <Edit3 className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => onDelete(t.id)}
                      className="rounded p-1.5 text-fg-muted hover:bg-bg-elevated hover:text-accent-crimson"
                      title="Delete"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </td>
              </motion.tr>
            ))}
          </AnimatePresence>
        </tbody>
      </table>
    </Card>
  )
}
