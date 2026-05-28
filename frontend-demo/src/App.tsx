import { useState, useEffect } from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { TopBar } from '@/components/TopBar'
import { TenantManagement } from '@/components/TenantManagement'
import { TranslationPlayground } from '@/components/TranslationPlayground'
import { SettingsModal } from '@/components/SettingsModal'
import { useApiSettings } from '@/hooks/useApiSettings'
import { SEED_TENANTS } from '@/mocks/tenants'
import type { Tenant } from '@/services/types'

function App() {
  const [tenants, setTenants] = useState<Tenant[]>(SEED_TENANTS)
  const [activeTenantId, setActiveTenantId] = useState<string | null>(
    SEED_TENANTS[0]?.id ?? null,
  )
  const [settingsOpen, setSettingsOpen] = useState(false)
  const { isConfigured } = useApiSettings()

  // Auto-open on first launch if real mode and no credentials. Saves the user
  // from a confusing "translate fails immediately" first run — they see the
  // modal before they even attempt a translation.
  useEffect(() => {
    const apiMode = import.meta.env.VITE_API_MODE ?? 'mock'
    if (apiMode === 'real' && !isConfigured) {
      setSettingsOpen(true)
    }
  }, [isConfigured])

  const activeTenant = tenants.find((t) => t.id === activeTenantId) ?? null

  const createTenant = (t: Tenant) => {
    setTenants((prev) => [t, ...prev])
    setActiveTenantId(t.id)
  }

  const deleteTenant = (id: string) => {
    setTenants((prev) => prev.filter((t) => t.id !== id))
    if (activeTenantId === id) {
      setActiveTenantId(tenants.find((t) => t.id !== id)?.id ?? null)
    }
  }

  return (
    <div className="min-h-screen text-fg-body">
      <TopBar
        tenants={tenants}
        activeTenantId={activeTenantId}
        onSelectTenant={setActiveTenantId}
        onOpenSettings={() => setSettingsOpen(true)}
      />
      <SettingsModal open={settingsOpen} onOpenChange={setSettingsOpen} />

      <Tabs defaultValue="playground" className="w-full">
        <TabsList className="mx-6 mt-4 bg-transparent">
          <TabsTrigger value="tenant" className="data-[state=active]:bg-bg-card">
            Tenant Management
          </TabsTrigger>
          <TabsTrigger value="playground" className="data-[state=active]:bg-bg-card">
            Translation Playground
          </TabsTrigger>
        </TabsList>

        <TabsContent value="tenant" className="mt-0">
          <TenantManagement
            tenants={tenants}
            activeTenantId={activeTenantId}
            onCreate={createTenant}
            onSelect={setActiveTenantId}
            onDelete={deleteTenant}
          />
        </TabsContent>

        <TabsContent value="playground" className="mt-0">
          {activeTenant ? (
            <TranslationPlayground tenant={activeTenant} />
          ) : (
            <div className="p-6 text-fg-muted">Create a tenant first.</div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}

export default App
