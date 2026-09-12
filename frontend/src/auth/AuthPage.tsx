import { useState } from 'react'
import portalLogo from '@/imports/image-1.png'
import { useAuth, ApiRequestError, type SupportLine } from './AuthContext'
import './auth.css'

type Mode = 'login' | 'register-user' | 'register-specialist'

const LINE_OPTIONS: { value: SupportLine; label: string }[] = [
  { value: 'L1', label: 'L1 — Базовая поддержка' },
  { value: 'L2', label: 'L2 — Методологическая поддержка' },
  { value: 'L3', label: 'L3 — Техническая поддержка' },
]

const ERROR_MESSAGES: Record<string, string> = {
  EMAIL_TAKEN: 'Этот email уже зарегистрирован.',
  INVALID_CREDENTIALS: 'Неверный email или пароль.',
  PENDING_APPROVAL: 'Заявка ещё ожидает подтверждения администратором.',
  REGISTRATION_REJECTED: 'Заявка на статус тех.специалиста была отклонена.',
  INVALID_REQUEST: 'Проверьте правильность заполнения формы.',
}

function describeError(error: unknown): string {
  if (error instanceof ApiRequestError) {
    return ERROR_MESSAGES[error.code] ?? error.message ?? 'Не удалось выполнить запрос.'
  }
  return 'Не удалось связаться с сервером. Попробуйте ещё раз.'
}

export default function AuthPage() {
  const auth = useAuth()
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [line, setLine] = useState<SupportLine>('L1')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  function switchMode(next: Mode) {
    setMode(next)
    setError(null)
    setNotice(null)
    setPassword('')
    setConfirmPassword('')
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setNotice(null)

    if (mode !== 'login') {
      if (password.length < 8) {
        setError('Пароль должен быть не короче 8 символов.')
        return
      }
      if (password !== confirmPassword) {
        setError('Пароли не совпадают.')
        return
      }
      if (!displayName.trim()) {
        setError('Укажите имя.')
        return
      }
    }

    setSubmitting(true)
    try {
      if (mode === 'login') {
        await auth.login(email, password)
      } else if (mode === 'register-user') {
        await auth.registerUser(email, password, displayName)
      } else {
        const result = await auth.registerSpecialist(email, password, displayName, line)
        setNotice(result.message)
        switchMode('login')
      }
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSubmitting(false)
    }
  }

  const isRegister = mode !== 'login'

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <div className="auth-logo">
          <img src={portalLogo} alt="" aria-hidden="true" />
          <span>
            Портал <strong>поставщиков</strong>
          </span>
        </div>

        <h1 className="auth-title">{mode === 'login' ? 'Вход' : 'Регистрация'}</h1>
        <p className="auth-subtitle">
          {mode === 'login'
            ? 'Войдите, чтобы обратиться в поддержку Портала'
            : mode === 'register-user'
              ? 'Аккаунт поставщика/заказчика Портала'
              : 'Заявка на статус технического специалиста поддержки'}
        </p>

        <div className="auth-tabs" role="tablist" aria-label="Способ входа">
          <button type="button" role="tab" aria-selected={mode === 'login'} className={`auth-tab${mode === 'login' ? ' active' : ''}`} onClick={() => switchMode('login')}>
            Вход
          </button>
          <button type="button" role="tab" aria-selected={mode === 'register-user'} className={`auth-tab${mode === 'register-user' ? ' active' : ''}`} onClick={() => switchMode('register-user')}>
            Я поставщик
          </button>
          <button type="button" role="tab" aria-selected={mode === 'register-specialist'} className={`auth-tab${mode === 'register-specialist' ? ' active' : ''}`} onClick={() => switchMode('register-specialist')}>
            Я тех.специалист
          </button>
        </div>

        {notice && <div className="auth-success">{notice}</div>}
        {error && (
          <div className="auth-error" role="alert">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          {isRegister && (
            <div className="auth-field">
              <label htmlFor="auth-name">Имя</label>
              <input id="auth-name" type="text" autoComplete="name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
            </div>
          )}

          <div className="auth-field">
            <label htmlFor="auth-email">Email</label>
            <input id="auth-email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>

          <div className="auth-field">
            <label htmlFor="auth-password">Пароль</label>
            <input
              id="auth-password"
              type="password"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={isRegister ? 8 : undefined}
              required
            />
            {isRegister && <div className="auth-hint">Не короче 8 символов.</div>}
          </div>

          {isRegister && (
            <div className="auth-field">
              <label htmlFor="auth-confirm">Повторите пароль</label>
              <input id="auth-confirm" type="password" autoComplete="new-password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required />
            </div>
          )}

          {mode === 'register-specialist' && (
            <div className="auth-field">
              <label htmlFor="auth-line">Линия поддержки</label>
              <select id="auth-line" value={line} onChange={(e) => setLine(e.target.value as SupportLine)}>
                {LINE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <div className="auth-hint">Доступ откроется после подтверждения администратором.</div>
            </div>
          )}

          <button type="submit" className="auth-submit" disabled={submitting}>
            {submitting ? 'Отправка…' : mode === 'login' ? 'Войти' : mode === 'register-user' ? 'Зарегистрироваться' : 'Отправить заявку'}
          </button>
        </form>

        <div className="auth-switch">
          {mode === 'login' ? (
            <span>
              Нет аккаунта? <button onClick={() => switchMode('register-user')}>Зарегистрироваться</button>
            </span>
          ) : (
            <span>
              Уже есть аккаунт? <button onClick={() => switchMode('login')}>Войти</button>
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
