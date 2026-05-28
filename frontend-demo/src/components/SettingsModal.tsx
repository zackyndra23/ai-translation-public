import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useApiSettings } from '@/hooks/useApiSettings'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
}

// Settings modal — sole entry point for backend credentials configuration.
// Per ADR-061, kept separate from Tab 1 mock tenant management. localStorage
// persistence via useApiSettings hook (ADR-026 PII trade-off precedent —
// API key in localStorage is acceptable for demo/dev context).
export function SettingsModal({ open, onOpenChange }: Props) {
  const { settings, save } = useApiSettings()
  const [draft, setDraft] = useState(settings)
  const [showApiKey, setShowApiKey] = useState(false)

  // Re-sync draft when modal opens — picks up any settings changes that
  // happened while the modal was closed (Context update from elsewhere).
  // Reset show-API-key on close so re-open doesn't leak the key visually
  // if user walks away mid-edit.
  useEffect(() => {
    if (open) {
      setDraft(settings)
    } else {
      setShowApiKey(false)
    }
  }, [open, settings])

  const apiMode = import.meta.env.VITE_API_MODE ?? 'mock'

  const handleSave = () => {
    save(draft)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-bg-card border-border-default max-w-md">
        <DialogHeader>
          <DialogTitle className="text-fg-primary">Backend Connection</DialogTitle>
          <DialogDescription>
            Currently using:{' '}
            <span className={apiMode === 'real' ? 'text-accent-emerald' : 'text-accent-amber'}>
              {apiMode === 'real' ? 'REAL backend' : 'MOCK in-memory'}
            </span>
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1">
            <Label htmlFor="settings-baseUrl">Base URL</Label>
            <Input
              id="settings-baseUrl"
              value={draft.baseUrl}
              onChange={(e) => setDraft({ ...draft, baseUrl: e.target.value })}
              placeholder="/api"
            />
            <p className="text-xs text-fg-muted">
              Default <code>/api</code> uses Vite dev proxy. Override with full URL for prod.
            </p>
          </div>

          <div className="space-y-1">
            <Label htmlFor="settings-apiKey">API Key</Label>
            <div className="flex gap-2">
              <Input
                id="settings-apiKey"
                type={showApiKey ? 'text' : 'password'}
                value={draft.apiKey}
                onChange={(e) => setDraft({ ...draft, apiKey: e.target.value })}
                placeholder="aitkey_..."
                className="font-mono"
              />
              <Button
                type="button"
                variant="outline"
                onClick={() => setShowApiKey((s) => !s)}
              >
                {showApiKey ? 'Hide' : 'Show'}
              </Button>
            </div>
            <p className="text-xs text-fg-muted">
              Output from <code>scripts/seed_tenant_data.py</code> first run (stdout
              <code> API_KEY=aitkey_...</code>).
            </p>
          </div>

          <div className="space-y-1">
            <Label htmlFor="settings-profileId">Profile ID</Label>
            <Input
              id="settings-profileId"
              value={draft.profileId}
              onChange={(e) => setDraft({ ...draft, profileId: e.target.value })}
              placeholder="profile-XXXXXXXX-XXXX"
              className="font-mono"
            />
            <p className="text-xs text-fg-muted">
              From backend. PSQL:{' '}
              <code>SELECT profile_id, tenant_name FROM tenant_profile LIMIT 5;</code>
            </p>
          </div>

          <div className="space-y-1">
            <Label htmlFor="settings-tenantId">Tenant ID</Label>
            <Input
              id="settings-tenantId"
              value={draft.tenantId}
              onChange={(e) => setDraft({ ...draft, tenantId: e.target.value })}
              placeholder="tenant-XXXXXXXX-XXXX"
              className="font-mono"
            />
            <p className="text-xs text-fg-muted">
              From backend. PSQL:{' '}
              <code>SELECT tenant_id, tenant_name FROM tenant LIMIT 5;</code>
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
