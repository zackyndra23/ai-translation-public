import type { Tenant } from '@/services/types'

export const SEED_TENANTS: Tenant[] = [
  {
    id: 'tnt_a3f9k2',
    name: 'Acme Localization',
    source_lang: 'en',
    target_lang: 'es',
    model_tier: 'Premium',
    language_detection: true,
    output_streaming: true,
    log_payloads: true,
    created_at: '2026-04-15T08:23:00.000Z',
    status: 'active',
  },
  {
    id: 'tnt_x7m2q5',
    name: 'TravelGenie Inc.',
    source_lang: 'en',
    target_lang: 'ja',
    model_tier: 'Enterprise',
    language_detection: true,
    output_streaming: true,
    log_payloads: false,
    created_at: '2026-03-02T14:11:00.000Z',
    status: 'active',
  },
  {
    id: 'tnt_b8h4n1',
    name: 'Globex Trading Pte Ltd',
    source_lang: 'zh',
    target_lang: 'en',
    model_tier: 'Standard',
    language_detection: false,
    output_streaming: true,
    log_payloads: true,
    created_at: '2026-05-01T11:48:00.000Z',
    status: 'active',
  },
  {
    id: 'tnt_q5k9p7',
    name: 'Lumen Health Network',
    source_lang: 'en',
    target_lang: 'pt',
    model_tier: 'Premium',
    language_detection: true,
    output_streaming: false,
    log_payloads: true,
    created_at: '2026-05-12T09:30:00.000Z',
    status: 'inactive',
  },
  {
    id: 'tnt_d2v6c8',
    name: 'Aitegrity Internal',
    source_lang: 'id',
    target_lang: 'en',
    model_tier: 'Standard',
    language_detection: true,
    output_streaming: true,
    log_payloads: true,
    created_at: '2026-05-20T16:00:00.000Z',
    status: 'active',
  },
]

export function generateTenantId(): string {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789'
  let s = 'tnt_'
  for (let i = 0; i < 6; i++) s += chars[Math.floor(Math.random() * chars.length)]
  return s
}
