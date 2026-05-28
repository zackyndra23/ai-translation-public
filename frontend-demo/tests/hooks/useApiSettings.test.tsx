import { renderHook, render, act } from '@testing-library/react'
import { describe, expect, it, beforeEach } from 'vitest'
import type { ReactNode } from 'react'
import {
  ApiSettingsProvider,
  useApiSettings,
  type ApiSettings,
} from '@/hooks/useApiSettings'

beforeEach(() => {
  window.localStorage.clear()
})

// Shared wrapper so each renderHook gets its own Provider instance — the
// hook now throws if it's mounted outside a Provider, so bare renderHook
// is no longer valid.
const wrapper = ({ children }: { children: ReactNode }) => (
  <ApiSettingsProvider>{children}</ApiSettingsProvider>
)

describe('useApiSettings', () => {
  it('starts with defaults when localStorage is empty', () => {
    const { result } = renderHook(() => useApiSettings(), { wrapper })
    expect(result.current.settings).toEqual({
      baseUrl: '/api',
      apiKey: '',
      profileId: '',
      tenantId: '',
    })
    expect(result.current.isConfigured).toBe(false)
  })

  it('save() persists to localStorage and exposes isConfigured=true once all set', () => {
    const { result } = renderHook(() => useApiSettings(), { wrapper })
    act(() => {
      result.current.save({
        apiKey: 'aitkey_xyz',
        profileId: 'profile-aaaaaaaa-bbbb',
        tenantId: 'tenant-cccccccc-dddd',
      })
    })
    expect(result.current.settings.apiKey).toBe('aitkey_xyz')
    expect(result.current.isConfigured).toBe(true)
    const stored = JSON.parse(window.localStorage.getItem('aitegrity_api_settings')!)
    expect(stored.apiKey).toBe('aitkey_xyz')
  })

  it('rehydrates from localStorage on mount', () => {
    window.localStorage.setItem(
      'aitegrity_api_settings',
      JSON.stringify({
        baseUrl: 'http://custom:9000',
        apiKey: 'aitkey_pre',
        profileId: 'profile-11111111-2222',
        tenantId: 'tenant-33333333-4444',
      }),
    )
    const { result } = renderHook(() => useApiSettings(), { wrapper })
    expect(result.current.settings.baseUrl).toBe('http://custom:9000')
    expect(result.current.isConfigured).toBe(true)
  })

  it('isConfigured=false when apiKey does not start with aitkey_', () => {
    const { result } = renderHook(() => useApiSettings(), { wrapper })
    act(() => {
      result.current.save({
        apiKey: 'wrong_prefix',
        profileId: 'profile-aaaaaaaa-bbbb',
        tenantId: 'tenant-cccccccc-dddd',
      })
    })
    expect(result.current.isConfigured).toBe(false)
  })

  // Regression test for the multi-instance staleness bug that motivated the
  // Provider refactor. Two consumers under ONE Provider must see save() from
  // either consumer reflected in both reads — proves we removed the previous
  // useState-per-call divergence between TopBar / SettingsModal / App.
  it('multiple consumers under one Provider share state on save()', () => {
    let topbarSnapshot: { isConfigured: boolean } | null = null
    let modalSnapshot: { save: (s: Partial<ApiSettings>) => void } | null = null

    function TopBarLike() {
      const { isConfigured } = useApiSettings()
      topbarSnapshot = { isConfigured }
      return null
    }
    function ModalLike() {
      const { save } = useApiSettings()
      modalSnapshot = { save }
      return null
    }

    render(
      <ApiSettingsProvider>
        <TopBarLike />
        <ModalLike />
      </ApiSettingsProvider>,
    )

    expect(topbarSnapshot!.isConfigured).toBe(false)

    act(() => {
      modalSnapshot!.save({
        apiKey: 'aitkey_x',
        profileId: 'profile-aaaaaaaa-bbbb',
        tenantId: 'tenant-cccccccc-dddd',
      })
    })

    expect(topbarSnapshot!.isConfigured).toBe(true)
  })
})
