import { useEffect, useState } from 'react'
import { TenantForm } from './TenantForm'
import { TenantTable } from './TenantTable'
import type { Tenant } from '@/services/types'

interface Props {
  tenants: Tenant[]
  activeTenantId: string | null
  onCreate: (t: Tenant) => void
  onSelect: (id: string) => void
  onDelete: (id: string) => void
}

export function TenantManagement({
  tenants,
  activeTenantId,
  onCreate,
  onSelect,
  onDelete,
}: Props) {
  const [recentlyCreated, setRecentlyCreated] = useState<string | null>(null)

  useEffect(() => {
    if (!recentlyCreated) return
    const t = setTimeout(() => setRecentlyCreated(null), 1500)
    return () => clearTimeout(t)
  }, [recentlyCreated])

  const handleCreate = (t: Tenant) => {
    onCreate(t)
    setRecentlyCreated(t.id)
  }

  return (
    <div className="grid grid-cols-12 gap-6 p-6">
      <div className="col-span-12 lg:col-span-5">
        <TenantForm onCreate={handleCreate} />
      </div>
      <div className="col-span-12 lg:col-span-7">
        <TenantTable
          tenants={tenants}
          activeTenantId={activeTenantId}
          recentlyCreated={recentlyCreated}
          onSelect={onSelect}
          onDelete={onDelete}
        />
      </div>
    </div>
  )
}
