import { useState } from 'react'
import { Card } from '@/components/ui/card'
import { LanguageBar } from './LanguageBar'
import { InputBox } from './InputBox'
import { OutputBox } from './OutputBox'
import { TranslateButton } from './TranslateButton'
import { AgentPipeline } from '@/components/AgentPipeline'
import { PayloadViewer } from '@/components/PayloadViewer'
import { useTranslationFlow } from '@/hooks/useTranslationFlow'
import { useApiSettings } from '@/hooks/useApiSettings'
import { ApiError, NetworkError } from '@/services/errors'
import type { LangCode, ModelId, Tenant } from '@/services/types'

interface Props {
  tenant: Tenant
}

// Map error → human banner copy. Severity drawn from CLAUDE.md merah-putih
// palette per ADR-052 + ADR-064: amber = user-correctable (config/policy);
// crimson = system/error states needing operator attention.
function bannerCopyForError(
  err: unknown,
): { title: string; severity: 'amber' | 'crimson' } | null {
  if (err instanceof ApiError) {
    if (err.isLanguageNotAllowed()) {
      return { title: err.detail, severity: 'amber' }
    }
    if (err.isAuth()) {
      return {
        title: 'Authentication failed. Check API key in Settings.',
        severity: 'crimson',
      }
    }
    if (err.isRateLimited()) {
      return { title: `Rate limited: ${err.detail}`, severity: 'amber' }
    }
    if (err.isTransient()) {
      return {
        title: 'Translation service temporarily unavailable. Retry.',
        severity: 'crimson',
      }
    }
    return {
      title: `Translation failed: ${err.detail}`,
      severity: 'crimson',
    }
  }
  if (err instanceof NetworkError) {
    return {
      title: 'Cannot reach translation service. Check Settings → Base URL.',
      severity: 'crimson',
    }
  }
  return null
}

export function TranslationPlayground({ tenant }: Props) {
  const { settings, isConfigured } = useApiSettings()
  const [inputText, setInputText] = useState('Halo, apa kabar hari ini?')
  const [sourceLang, setSourceLang] = useState<LangCode>(tenant.source_lang)
  const [targetLang, setTargetLang] = useState<LangCode>(tenant.target_lang)
  const [modelId, setModelId] = useState<ModelId>('claude-sonnet-4-6')

  const flow = useTranslationFlow()

  const swap = () => {
    const s = sourceLang
    setSourceLang(targetLang)
    setTargetLang(s)
  }

  const translate = () => {
    // When configured via Settings, use real backend IDs. Otherwise fall back
    // to the mock tenant id + placeholder profile_id (mockApi ignores both).
    const apiMode = import.meta.env.VITE_API_MODE ?? 'mock'
    const usingReal = apiMode === 'real' && isConfigured
    flow.start({
      text: inputText,
      source_lang: sourceLang,
      target_lang: targetLang,
      tenant_id: usingReal ? settings.tenantId : tenant.id,
      profile_id: usingReal ? settings.profileId : 'profile-default',
      model_id: modelId,
    })
  }

  const status =
    flow.state.status === 'running'
      ? 'running'
      : flow.state.status === 'done'
        ? 'done'
        : flow.state.status === 'error'
          ? 'error'
          : 'idle'

  const translatedText =
    flow.state.status === 'done' ? flow.state.payload.translated_text : null
  const errorMessage =
    flow.state.status === 'error' ? flow.state.message : undefined
  const payload =
    flow.state.status === 'done' ? flow.state.payload : null
  const agents =
    flow.state.status === 'running' || flow.state.status === 'done'
      ? flow.state.agents
      : null

  // Banner derived from the typed error stashed on error-state. `'error' in`
  // narrowing keeps this resilient even if FlowState gains more variants.
  const errorBanner =
    flow.state.status === 'error' && 'error' in flow.state
      ? bannerCopyForError(flow.state.error)
      : null
  const errorTraceId =
    flow.state.status === 'error' &&
    'error' in flow.state &&
    flow.state.error instanceof ApiError
      ? flow.state.error.traceId
      : undefined

  return (
    <div className="space-y-6 p-6">
      {errorBanner && (
        <div
          className={
            errorBanner.severity === 'amber'
              ? 'rounded-md border border-accent-amber/50 bg-accent-amber/10 px-4 py-3 text-fg-primary'
              : 'rounded-md border border-accent-crimson/50 bg-accent-crimson/10 px-4 py-3 text-fg-primary'
          }
        >
          <div className="font-medium">{errorBanner.title}</div>
          {errorTraceId && (
            <button
              onClick={() => navigator.clipboard.writeText(errorTraceId)}
              className="mt-1 font-mono text-xs text-fg-muted hover:text-fg-body"
              title="Click to copy"
            >
              trace_id: {errorTraceId}
            </button>
          )}
        </div>
      )}

      <Card className="bg-bg-card border-border-default overflow-hidden">
        <LanguageBar
          sourceLang={sourceLang}
          targetLang={targetLang}
          modelId={modelId}
          onSourceChange={setSourceLang}
          onTargetChange={setTargetLang}
          onSwap={swap}
          onModelChange={setModelId}
        />
        <div className="grid grid-cols-2 gap-6 p-6">
          <InputBox
            value={inputText}
            sourceLang={sourceLang}
            onChange={setInputText}
            onSwitchSource={setSourceLang}
          />
          <OutputBox
            translatedText={translatedText}
            status={status}
            errorMessage={errorMessage}
            onRegenerate={status === 'done' ? translate : undefined}
          />
        </div>
        <div className="px-6 pb-6">
          <TranslateButton
            disabled={inputText.trim().length === 0}
            loading={status === 'running'}
            onClick={translate}
          />
        </div>
      </Card>

      <AgentPipeline agents={agents} elapsed={flow.elapsed} payload={payload} />

      <PayloadViewer payload={payload} />
    </div>
  )
}
