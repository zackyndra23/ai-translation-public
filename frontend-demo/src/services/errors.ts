// Typed API errors. Used by apiClient + realApi + TranslationPlayground.
// Predicates keep the call sites readable (`err.isLanguageNotAllowed()` reads
// better than `err.errorCode === 'language_not_allowed'` scattered everywhere).

export interface ApiErrorOpts {
  status: number
  errorCode: string
  detail: string
  traceId?: string
}

export class ApiError extends Error {
  status: number
  errorCode: string
  detail: string
  traceId?: string

  constructor(opts: ApiErrorOpts) {
    super(opts.detail ? `${opts.errorCode}: ${opts.detail}` : opts.errorCode)
    this.name = 'ApiError'
    this.status = opts.status
    this.errorCode = opts.errorCode
    this.detail = opts.detail
    this.traceId = opts.traceId
  }

  isLanguageNotAllowed(): boolean {
    return this.errorCode === 'language_not_allowed'
  }

  isAuth(): boolean {
    // Backend emits 'missing_credentials' (auth middleware: no header) and
    // 'provider_auth_failed' (Anthropic SDK rejected our key). Also keep
    // 'authentication_failed' + 'tenant_not_found' as forward-compat slots.
    return (
      this.errorCode === 'missing_credentials' ||
      this.errorCode === 'provider_auth_failed' ||
      this.errorCode === 'authentication_failed' ||
      this.errorCode === 'tenant_not_found'
    )
  }

  isRateLimited(): boolean {
    return this.errorCode === 'rate_limited'
  }

  isTransient(): boolean {
    return this.errorCode === 'upstream_transient' || this.status >= 500
  }
}

export class NetworkError extends Error {
  cause: unknown

  constructor(cause: unknown) {
    super('Network error')
    this.name = 'NetworkError'
    this.cause = cause
  }
}
