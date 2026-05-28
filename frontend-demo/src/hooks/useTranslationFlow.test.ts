import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useTranslationFlow } from './useTranslationFlow'
import { mockApi } from '@/services/mockApi'
import type { TranslateApi, TranslateRequest } from '@/services/types'

const baseReq: TranslateRequest = {
  text: 'Halo apa kabar hari ini',
  source_lang: 'id',
  target_lang: 'en',
  tenant_id: 'tnt_a3f9k2',
  profile_id: 'profile-default',
  model_id: 'claude-sonnet-4-6',
}

beforeEach(() => {
  mockApi._resetCache()
})

describe('useTranslationFlow', () => {
  it('starts in idle state', () => {
    const { result } = renderHook(() => useTranslationFlow())
    expect(result.current.state.status).toBe('idle')
  })

  it('transitions idle → running → done', async () => {
    const { result } = renderHook(() => useTranslationFlow())
    act(() => {
      result.current.start(baseReq)
    })
    await waitFor(() => {
      expect(result.current.state.status).toBe('running')
    })
    await waitFor(
      () => {
        expect(result.current.state.status).toBe('done')
      },
      { timeout: 5000 },
    )
    if (result.current.state.status === 'done') {
      expect(result.current.state.payload.translated_text).toBeTruthy()
    }
  })

  it('updates agent statuses as agents progress', async () => {
    const { result } = renderHook(() => useTranslationFlow())
    act(() => {
      result.current.start(baseReq)
    })
    await waitFor(() => {
      expect(result.current.state.status).toBe('running')
    })
    if (result.current.state.status === 'running') {
      // both agents should reach 'running' within parallel start window
      await waitFor(() => {
        if (result.current.state.status === 'running') {
          expect(result.current.state.agents.lang_detect_input.status).toBe(
            'running',
          )
          expect(result.current.state.agents.translate.status).toBe('running')
        }
      })
    }
    await waitFor(
      () => {
        expect(result.current.state.status).toBe('done')
      },
      { timeout: 5000 },
    )
    if (result.current.state.status === 'done') {
      expect(result.current.state.agents.lang_detect_input.status).toBe(
        'completed',
      )
      expect(result.current.state.agents.translate.status).toBe('completed')
    }
  })

  it('captures error state when api throws', async () => {
    const failingApi = {
      translate: () => Promise.reject(new Error('boom')),
    } as unknown as TranslateApi
    const { result } = renderHook(() => useTranslationFlow(failingApi))
    act(() => {
      result.current.start(baseReq)
    })
    await waitFor(
      () => {
        expect(result.current.state.status).toBe('error')
      },
      { timeout: 2000 },
    )
    if (result.current.state.status === 'error') {
      expect(result.current.state.message).toContain('boom')
    }
  })
})
