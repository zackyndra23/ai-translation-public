import { ApiError, NetworkError } from './errors'

export interface ApiClientOptions {
  baseUrl: string
  apiKey: string
  // Per-request timeout. Default 60s matches typical LLM end-to-end latency
  // ceiling (Opus on long prompts can push ~30-40s). Configurable so eval/load
  // harnesses can tighten it; or stretch it for batch endpoints if added later.
  timeoutMs?: number
}

const DEFAULT_TIMEOUT_MS = 60_000

// Thin fetch wrapper. Single responsibility: serialize request body, inject
// auth header, parse response, map error envelope. NOT a full HTTP client —
// realApi composes on top for streaming / domain-specific concerns.
//
// Auth header choice (X-Tenant-API-Key) matches sub-proyek I auth middleware
// fallback path (ADR-046). JWT-bearer support deferred to a future sub-project
// once login UI exists.
export class ApiClient {
  constructor(private opts: ApiClientOptions) {}

  async post<TResp>(path: string, body: unknown): Promise<TResp> {
    // AbortController guards against hung connections (server accepted TCP
    // but never replies — e.g. dead worker, network partition mid-stream).
    // Without this, a stalled fetch hangs forever and pins the UI's "running"
    // state; the user has no way to recover short of a page reload.
    const controller = new AbortController()
    const timeoutMs = this.opts.timeoutMs ?? DEFAULT_TIMEOUT_MS
    const timeoutHandle = setTimeout(() => controller.abort(), timeoutMs)

    let resp: Response
    try {
      resp = await fetch(`${this.opts.baseUrl}${path}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Tenant-API-Key': this.opts.apiKey,
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      })
    } catch (e) {
      // fetch() rejects on network failure (DNS, refused connection, CORS) AND
      // on AbortError when the timeout fires. Map both to NetworkError so
      // callers see one uniform error path; the AbortError message survives
      // inside NetworkError.cause for diagnostics.
      throw new NetworkError(e)
    } finally {
      clearTimeout(timeoutHandle)
    }

    if (!resp.ok) {
      // Try to parse the standard ErrorResponse envelope (ADR-019); fall back
      // to raw statusText if the response isn't JSON (proxy 502, gateway HTML).
      let errorCode = 'unknown'
      let detail = resp.statusText
      let traceId: string | undefined
      try {
        const errBody = (await resp.json()) as {
          error_code?: unknown
          detail?: unknown
          trace_id?: unknown
        }
        errorCode = typeof errBody.error_code === 'string' ? errBody.error_code : errorCode
        detail = typeof errBody.detail === 'string' ? errBody.detail : detail
        traceId = typeof errBody.trace_id === 'string' ? errBody.trace_id : undefined
      } catch {
        // Not JSON — keep fallback values from above.
      }
      throw new ApiError({ status: resp.status, errorCode, detail, traceId })
    }

    return (await resp.json()) as TResp
  }
}
