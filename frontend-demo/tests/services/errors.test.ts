import { describe, expect, it } from 'vitest'
import { ApiError, NetworkError } from '@/services/errors'

describe('ApiError', () => {
  it('exposes status + errorCode + detail + traceId', () => {
    const err = new ApiError({
      status: 400,
      errorCode: 'language_not_allowed',
      detail: "target 'ja' not allowed",
      traceId: 'abc123',
    })
    expect(err.status).toBe(400)
    expect(err.errorCode).toBe('language_not_allowed')
    expect(err.detail).toBe("target 'ja' not allowed")
    expect(err.traceId).toBe('abc123')
    expect(err.message).toContain('language_not_allowed')
  })

  it('isLanguageNotAllowed() is true only for that code', () => {
    const a = new ApiError({ status: 400, errorCode: 'language_not_allowed', detail: '' })
    const b = new ApiError({ status: 400, errorCode: 'other', detail: '' })
    expect(a.isLanguageNotAllowed()).toBe(true)
    expect(b.isLanguageNotAllowed()).toBe(false)
  })

  it('isAuth() covers missing_credentials, provider_auth_failed, authentication_failed, tenant_not_found', () => {
    expect(new ApiError({ status: 401, errorCode: 'missing_credentials', detail: '' }).isAuth()).toBe(true)
    expect(new ApiError({ status: 500, errorCode: 'provider_auth_failed', detail: '' }).isAuth()).toBe(true)
    expect(new ApiError({ status: 401, errorCode: 'authentication_failed', detail: '' }).isAuth()).toBe(true)
    expect(new ApiError({ status: 401, errorCode: 'tenant_not_found', detail: '' }).isAuth()).toBe(true)
    expect(new ApiError({ status: 400, errorCode: 'other', detail: '' }).isAuth()).toBe(false)
  })

  it('isTransient() covers upstream_transient + 5xx', () => {
    expect(new ApiError({ status: 503, errorCode: 'upstream_transient', detail: '' }).isTransient()).toBe(true)
    expect(new ApiError({ status: 500, errorCode: 'whatever', detail: '' }).isTransient()).toBe(true)
    expect(new ApiError({ status: 400, errorCode: 'other', detail: '' }).isTransient()).toBe(false)
  })

  it('isRateLimited() exactly matches rate_limited', () => {
    expect(new ApiError({ status: 429, errorCode: 'rate_limited', detail: '' }).isRateLimited()).toBe(true)
    expect(new ApiError({ status: 429, errorCode: 'other', detail: '' }).isRateLimited()).toBe(false)
  })
})

describe('NetworkError', () => {
  it('wraps an underlying cause', () => {
    const cause = new TypeError('Failed to fetch')
    const err = new NetworkError(cause)
    expect(err.cause).toBe(cause)
    expect(err.message).toBe('Network error')
  })
})
