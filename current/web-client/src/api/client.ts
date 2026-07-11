import { ApiError } from '../types/api'

const API_BASE = import.meta.env.VITE_API_URL ?? ''

function buildHeaders(init?: HeadersInit): Headers {
  const headers = new Headers(init)
  const token = localStorage.getItem('ctm.token')
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  if (!headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  return headers
}

async function parseResponse<T>(response: Response): Promise<T> {
  const contentType = response.headers.get('content-type') ?? ''
  if (!response.ok) {
    let details: unknown = null
    try {
      details = contentType.includes('application/json') ? await response.json() : await response.text()
    } catch {
      details = null
    }
    const message =
      typeof details === 'object' && details && 'detail' in (details as Record<string, unknown>)
        ? (() => {
            const detail = (details as Record<string, unknown>).detail
            if (Array.isArray(detail)) {
              // FastAPI validation error: array of {loc, msg, type}
              const first = detail[0] as Record<string, unknown> | undefined
              return first ? String(first.msg ?? detail) : `Request failed with status ${response.status}`
            }
            return String(detail)
          })()
        : `Request failed with status ${response.status}`
    if (response.status === 401) {
      localStorage.removeItem('ctm.token')
    }
    throw new ApiError(message, response.status, details)
  }

  if (contentType.includes('application/json')) {
    return (await response.json()) as T
  }
  return (await response.blob()) as T
}

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const isFormData = typeof FormData !== 'undefined' && init?.body instanceof FormData
  const headers = buildHeaders(init?.headers)
  if (isFormData) {
    headers.delete('Content-Type')
  }
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  })
  return parseResponse<T>(response)
}

export async function downloadRequest(path: string): Promise<Blob> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: buildHeaders(),
  })
  return parseResponse<Blob>(response)
}
