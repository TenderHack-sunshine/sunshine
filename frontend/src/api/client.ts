// Thin fetch wrapper for the Go backend. The access token lives only in
// memory (a module-level variable) — never in localStorage/sessionStorage —
// so it disappears on tab close; a page reload gets a fresh one from
// POST /auth/refresh, which relies on the httpOnly refresh cookie the
// backend sets on login (see AuthProvider). credentials: 'include' is what
// makes that cookie actually go out with every request.

export const API_BASE_URL: string =
  (import.meta as any).env?.VITE_API_BASE_URL ?? 'http://localhost:8080'

export type ApiErrorBody = { code: string; message: string }

export class ApiRequestError extends Error {
  code: string
  status: number
  constructor(status: number, body: ApiErrorBody) {
    super(body.message || body.code || 'Request failed')
    this.code = body.code || 'UNKNOWN'
    this.status = status
  }
}

let accessToken: string | null = null
const listeners = new Set<(token: string | null) => void>()

export function getAccessToken(): string | null {
  return accessToken
}

export function setAccessToken(token: string | null): void {
  accessToken = token
  listeners.forEach((listen) => listen(token))
}

export function onAccessTokenChange(listener: (token: string | null) => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

async function parseBody(response: Response): Promise<any> {
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

function buildHeaders(init: RequestInit): HeadersInit {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string> | undefined) }
  if (init.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json'
  if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`
  return headers
}

let refreshInFlight: Promise<string | null> | null = null

// refreshAccessToken de-duplicates concurrent refreshes: if three requests
// 401 at once, only one POST /auth/refresh is sent and all three await it.
function refreshAccessToken(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/auth/refresh`, { method: 'POST', credentials: 'include' })
        if (!response.ok) {
          setAccessToken(null)
          return null
        }
        const data = await parseBody(response)
        const token = data?.access_token ?? null
        setAccessToken(token)
        return token
      } catch {
        setAccessToken(null)
        return null
      } finally {
        refreshInFlight = null
      }
    })()
  }
  return refreshInFlight
}

const NO_RETRY_PATHS = new Set(['/auth/login', '/auth/refresh', '/auth/register', '/auth/register-specialist'])

export async function apiRequest<T>(path: string, init: RequestInit = {}, allowRetry = true): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: 'include',
    headers: buildHeaders(init),
  })

  if (response.status === 401 && allowRetry && !NO_RETRY_PATHS.has(path)) {
    const token = await refreshAccessToken()
    if (token) return apiRequest<T>(path, init, false)
  }

  const data = await parseBody(response)
  if (!response.ok) {
    throw new ApiRequestError(response.status, data?.error ?? { code: 'UNKNOWN', message: 'Request failed' })
  }
  return data as T
}

export function apiGet<T>(path: string): Promise<T> {
  return apiRequest<T>(path, { method: 'GET' })
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return apiRequest<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })
}
