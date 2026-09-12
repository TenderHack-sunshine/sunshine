// Thin fetch wrapper for the Go backend. The hackathon MVP is anonymous: a
// stable browser UUID keeps one visitor's requests separate without login,
// passwords, JWTs, or refresh cookies.

export const API_BASE_URL: string =
  (import.meta as any).env?.VITE_API_BASE_URL ?? 'http://localhost:8080'

export type ApiErrorBody = { code: string; message: string }

const ANONYMOUS_USER_ID_KEY = 'sunshine.anonymous_user_id'

function anonymousUserID(): string {
  try {
    const existing = window.localStorage.getItem(ANONYMOUS_USER_ID_KEY)
    if (existing) return existing
    const created = crypto.randomUUID()
    window.localStorage.setItem(ANONYMOUS_USER_ID_KEY, created)
    return created
  } catch {
    return 'anonymous-browser-session'
  }
}

export class ApiRequestError extends Error {
  code: string
  status: number
  constructor(status: number, body: ApiErrorBody) {
    super(body.message || body.code || 'Request failed')
    this.code = body.code || 'UNKNOWN'
    this.status = status
  }
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
  headers['X-Portal-User-ID'] = anonymousUserID()
  return headers
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: buildHeaders(init),
  })

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
