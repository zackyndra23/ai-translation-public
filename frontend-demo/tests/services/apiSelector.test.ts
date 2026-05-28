import { describe, expect, it, vi, beforeEach } from 'vitest'

describe('apiSelector', () => {
  beforeEach(() => {
    vi.resetModules()
    window.localStorage.clear()
  })

  it('returns mockApi when VITE_API_MODE !== real', async () => {
    vi.stubEnv('VITE_API_MODE', 'mock')
    const { getTranslateApi } = await import('@/services/apiSelector')
    const { mockApi } = await import('@/services/mockApi')
    expect(getTranslateApi()).toBe(mockApi)
  })

  it('returns mockApi fallback when real mode but no apiKey configured', async () => {
    vi.stubEnv('VITE_API_MODE', 'real')
    const { getTranslateApi } = await import('@/services/apiSelector')
    const { mockApi } = await import('@/services/mockApi')
    expect(getTranslateApi()).toBe(mockApi)
  })

  it('returns a real API factory result when real mode + apiKey set', async () => {
    vi.stubEnv('VITE_API_MODE', 'real')
    window.localStorage.setItem(
      'aitegrity_api_settings',
      JSON.stringify({
        baseUrl: '/api',
        apiKey: 'aitkey_xyz',
        profileId: 'profile-aaaaaaaa-bbbb',
        tenantId: 'tenant-cccccccc-dddd',
      }),
    )
    const { getTranslateApi } = await import('@/services/apiSelector')
    const { mockApi } = await import('@/services/mockApi')
    const api = getTranslateApi()
    // Identity comparison — more robust than sniffing optional methods on the
    // mock (a probe that becomes stale if mockApi loses _resetCache).
    expect(api).not.toBe(mockApi)
    expect(api).toHaveProperty('translate')
  })
})
