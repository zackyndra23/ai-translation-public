import { describe, expect, it, vi, beforeEach } from 'vitest'
import { ApiClient } from '@/services/apiClient'
import { ApiError, NetworkError } from '@/services/errors'

const okResponse = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })

const errorResponse = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('ApiClient', () => {
  it('parses JSON success and injects X-Tenant-API-Key header', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(okResponse({ translation: 'Hello' }))
    const client = new ApiClient({ baseUrl: '/api', apiKey: 'aitkey_xyz' })
    const result = await client.post<{ translation: string }>('/translate', { text: 'Halo' })

    expect(result).toEqual({ translation: 'Hello' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/translate')
    expect((init as RequestInit).method).toBe('POST')
    expect((init as RequestInit).headers).toMatchObject({
      'Content-Type': 'application/json',
      'X-Tenant-API-Key': 'aitkey_xyz',
    })
    expect((init as RequestInit).body).toBe(JSON.stringify({ text: 'Halo' }))
  })

  it('maps 400 error envelope to ApiError with error_code + detail + trace_id', async () => {
    // Use a fresh Response per call — Response bodies are single-read streams,
    // so reusing the same instance across two awaited posts consumes it.
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () =>
      errorResponse(400, {
        error_code: 'language_not_allowed',
        detail: "target 'ja' not allowed",
        trace_id: 'abc123',
      }),
    )
    const client = new ApiClient({ baseUrl: '/api', apiKey: 'aitkey_xyz' })

    await expect(client.post('/translate', {})).rejects.toBeInstanceOf(ApiError)
    try {
      await client.post('/translate', {})
    } catch (e) {
      expect((e as ApiError).status).toBe(400)
      expect((e as ApiError).errorCode).toBe('language_not_allowed')
      expect((e as ApiError).traceId).toBe('abc123')
    }
  })

  it('falls back to statusText when error body is not JSON', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('Internal Server Error', { status: 500, statusText: 'Internal Server Error' }),
    )
    const client = new ApiClient({ baseUrl: '/api', apiKey: 'aitkey_xyz' })

    try {
      await client.post('/translate', {})
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError)
      expect((e as ApiError).status).toBe(500)
      expect((e as ApiError).errorCode).toBe('unknown')
    }
  })

  it('wraps network/fetch failures in NetworkError', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
    const client = new ApiClient({ baseUrl: '/api', apiKey: 'aitkey_xyz' })

    await expect(client.post('/translate', {})).rejects.toBeInstanceOf(NetworkError)
  })

  it('aborts and throws NetworkError after timeout', async () => {
    // Real fetch behavior under AbortController: when controller.abort()
    // fires, the in-flight fetch rejects with an AbortError. We simulate by
    // resolving the mock promise only when controller.signal fires — that
    // way the test exercises the AbortController wiring end-to-end (timeout
    // fires → controller aborts → fetch rejects → caught by NetworkError mapper).
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      (_input, init) =>
        new Promise((_resolve, reject) => {
          const signal = (init as RequestInit | undefined)?.signal
          if (signal) {
            signal.addEventListener('abort', () => {
              const err = new DOMException('The operation was aborted.', 'AbortError')
              reject(err)
            })
          }
        }),
    )
    vi.useFakeTimers()
    const client = new ApiClient({ baseUrl: '/api', apiKey: 'aitkey_x', timeoutMs: 100 })
    const promise = client.post('/translate', {})
    // Attach a no-op catch so the unhandled-rejection trap is silent until
    // we await the assertion below; advanceTimersByTimeAsync drives the
    // setTimeout that triggers controller.abort().
    promise.catch(() => {})
    await vi.advanceTimersByTimeAsync(150)
    await expect(promise).rejects.toBeInstanceOf(NetworkError)
    vi.useRealTimers()
  })
})
