import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { apiPost, setAccessToken, ApiRequestError } from '../api/client'

export type Role = 'user' | 'tech_specialist' | 'admin'
export type SupportLine = '' | 'L1' | 'L2' | 'L3'
export type SpecialistStatus = '' | 'pending' | 'approved' | 'rejected'

export type AuthUser = {
  id: string
  email: string
  display_name: string
  role: Role
  line?: SupportLine
  specialist_status?: SpecialistStatus
}

type SessionResponse = { access_token: string; user: AuthUser }

type AuthStatus = 'loading' | 'authenticated' | 'anonymous'

type AuthContextValue = {
  status: AuthStatus
  user: AuthUser | null
  isStaff: boolean
  isAdmin: boolean
  login: (email: string, password: string) => Promise<void>
  registerUser: (email: string, password: string, displayName: string) => Promise<void>
  registerSpecialist: (
    email: string,
    password: string,
    displayName: string,
    line: SupportLine,
  ) => Promise<{ message: string }>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [user, setUser] = useState<AuthUser | null>(null)

  const applySession = useCallback((session: SessionResponse) => {
    setAccessToken(session.access_token)
    setUser(session.user)
    setStatus('authenticated')
  }, [])

  const clearSession = useCallback(() => {
    setAccessToken(null)
    setUser(null)
    setStatus('anonymous')
  }, [])

  // On first mount, try to turn the httpOnly refresh cookie (if any, from a
  // previous visit) into a fresh access token, so a page reload doesn't
  // bounce an already-logged-in user back to the login screen.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const session = await apiPost<SessionResponse>('/auth/refresh')
        if (!cancelled) applySession(session)
      } catch {
        if (!cancelled) clearSession()
      }
    })()
    return () => {
      cancelled = true
    }
  }, [applySession, clearSession])

  const login = useCallback(
    async (email: string, password: string) => {
      const session = await apiPost<SessionResponse>('/auth/login', { email, password })
      applySession(session)
    },
    [applySession],
  )

  const registerUser = useCallback(
    async (email: string, password: string, displayName: string) => {
      const session = await apiPost<SessionResponse>('/auth/register', {
        email,
        password,
        display_name: displayName,
      })
      applySession(session)
    },
    [applySession],
  )

  // Deliberately does not log the caller in: the backend keeps a
  // self-registered specialist in "pending" status until an admin approves
  // them (see AdminPanel's "Пользователи и роли" tab).
  const registerSpecialist = useCallback(
    async (email: string, password: string, displayName: string, line: SupportLine) => {
      return apiPost<{ message: string }>('/auth/register-specialist', {
        email,
        password,
        display_name: displayName,
        line,
      })
    },
    [],
  )

  const logout = useCallback(async () => {
    try {
      await apiPost('/auth/logout')
    } catch {
      // Clear local state regardless of whether the server call succeeded.
    }
    clearSession()
  }, [clearSession])

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      isStaff: user?.role === 'tech_specialist' || user?.role === 'admin',
      isAdmin: user?.role === 'admin',
      login,
      registerUser,
      registerSpecialist,
      logout,
    }),
    [status, user, login, registerUser, registerSpecialist, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within an AuthProvider')
  return context
}

export { ApiRequestError }
