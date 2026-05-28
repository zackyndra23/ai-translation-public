import { useState } from 'react'
import { motion } from 'framer-motion'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { LANGUAGE_LABELS, type LangCode, type ModelTier, type Tenant } from '@/services/types'
import { generateTenantId } from '@/mocks/tenants'
import { cn } from '@/lib/cn'

interface Props {
  onCreate: (tenant: Tenant) => void
}

export function TenantForm({ onCreate }: Props) {
  const [name, setName] = useState('')
  const [tenantId, setTenantId] = useState(generateTenantId())
  const [sourceLang, setSourceLang] = useState<LangCode>('en')
  const [targetLang, setTargetLang] = useState<LangCode>('id')
  const [modelTier, setModelTier] = useState<ModelTier>('Standard')
  const [langDetection, setLangDetection] = useState(true)
  const [outputStreaming, setOutputStreaming] = useState(true)
  const [logPayloads, setLogPayloads] = useState(true)

  const langs: LangCode[] = ['en', 'id', 'es', 'fr', 'de', 'ja', 'zh', 'ar', 'pt', 'ru']
  const tiers: ModelTier[] = ['Standard', 'Premium', 'Enterprise']

  const canSubmit = name.trim().length > 0

  const submit = () => {
    if (!canSubmit) return
    onCreate({
      id: tenantId,
      name: name.trim(),
      source_lang: sourceLang,
      target_lang: targetLang,
      model_tier: modelTier,
      language_detection: langDetection,
      output_streaming: outputStreaming,
      log_payloads: logPayloads,
      created_at: new Date().toISOString(),
      status: 'active',
    })
    setName('')
    setTenantId(generateTenantId())
  }

  return (
    <Card className="bg-bg-card border-border-default p-6">
      <div className="mb-6">
        <h2 className="text-lg font-medium text-fg-primary">Create Tenant</h2>
        <p className="mt-1 text-sm text-fg-muted">
          Add a new tenant to manage translation behaviour.
        </p>
      </div>

      <div className="space-y-4">
        <Field label="Tenant Name">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Acme Localization"
            className={inputClass}
          />
        </Field>

        <Field label="Tenant ID">
          <input
            value={tenantId}
            onChange={(e) => setTenantId(e.target.value)}
            className={cn(inputClass, 'font-mono text-sm')}
          />
        </Field>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Default Source Language">
            <Select value={sourceLang} onValueChange={(v) => setSourceLang(v as LangCode)}>
              <SelectTrigger className={selectTriggerClass}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-bg-elevated border-border-default">
                {langs.map((l) => (
                  <SelectItem key={l} value={l}>
                    {LANGUAGE_LABELS[l].flag} {LANGUAGE_LABELS[l].name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>

          <Field label="Default Target Language">
            <Select value={targetLang} onValueChange={(v) => setTargetLang(v as LangCode)}>
              <SelectTrigger className={selectTriggerClass}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-bg-elevated border-border-default">
                {langs.map((l) => (
                  <SelectItem key={l} value={l}>
                    {LANGUAGE_LABELS[l].flag} {LANGUAGE_LABELS[l].name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        </div>

        <Field label="Model Tier">
          <div className="flex rounded-lg border border-border-default bg-bg-base p-1">
            {tiers.map((t) => (
              <button
                key={t}
                onClick={() => setModelTier(t)}
                className={cn(
                  'flex-1 rounded-md px-4 py-1.5 text-sm transition-colors',
                  modelTier === t
                    ? 'bg-bg-elevated text-fg-primary'
                    : 'text-fg-muted hover:text-fg-body',
                )}
              >
                {t}
              </button>
            ))}
          </div>
        </Field>

        <Toggle
          label="Enable language detection"
          checked={langDetection}
          onChange={setLangDetection}
        />
        <Toggle
          label="Enable output streaming"
          checked={outputStreaming}
          onChange={setOutputStreaming}
        />
        <Toggle
          label="Log full payloads"
          checked={logPayloads}
          onChange={setLogPayloads}
        />

        <motion.div whileTap={canSubmit ? { scale: 0.98 } : undefined}>
          <Button
            disabled={!canSubmit}
            onClick={submit}
            className={cn(
              'mt-4 w-full bg-red-rose text-white border-0',
              'hover:opacity-90 transition-opacity',
              !canSubmit && 'opacity-50',
            )}
          >
            Create Tenant
          </Button>
        </motion.div>
      </div>
    </Card>
  )
}

const inputClass =
  'w-full rounded-lg border border-border-default bg-bg-base px-3 py-2 text-sm text-fg-primary placeholder:text-fg-placeholder focus:border-border-active focus:outline-none transition-colors'

const selectTriggerClass =
  'w-full bg-bg-base border-border-default text-fg-body'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1.5 block text-xs uppercase tracking-wider text-fg-muted">
        {label}
      </label>
      {children}
    </div>
  )
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <label className="flex cursor-pointer items-center justify-between rounded-lg border border-border-default bg-bg-base px-3 py-2.5">
      <span className="text-sm text-fg-body">{label}</span>
      <button
        onClick={() => onChange(!checked)}
        className={cn(
          'relative h-5 w-9 rounded-full transition-colors',
          checked ? 'bg-accent-red' : 'bg-bg-elevated',
        )}
      >
        <span
          className={cn(
            'absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform',
            checked ? 'translate-x-4' : 'translate-x-0.5',
          )}
        />
      </button>
    </label>
  )
}
