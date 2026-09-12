import { useEffect, useState } from 'react'
import { apiGet, apiPost, ApiRequestError } from '../api/client'
import type { AuthUser, Role, SupportLine } from '../auth/AuthContext'
import './admin.css'

const ROLE_LABEL: Record<Role, string> = {
  user: 'Пользователь',
  tech_specialist: 'Тех.специалист',
  admin: 'Администратор',
}

const LINE_OPTIONS: { value: SupportLine; label: string }[] = [
  { value: '', label: '— без линии —' },
  { value: 'L1', label: 'L1' },
  { value: 'L2', label: 'L2' },
  { value: 'L3', label: 'L3' },
]

function errorMessage(err: unknown): string {
  if (err instanceof ApiRequestError) return err.message
  return 'Не удалось выполнить запрос.'
}

export default function RoleManagement() {
  const [users, setUsers] = useState<AuthUser[] | null>(null)
  const [pending, setPending] = useState<AuthUser[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  // Per-row draft role/line selection, keyed by user id, so editing one
  // row's dropdowns doesn't touch the others before "Сохранить" is pressed.
  const [drafts, setDrafts] = useState<Record<string, { role: Role; line: SupportLine }>>({})

  async function load() {
    setError(null)
    try {
      const [usersRes, pendingRes] = await Promise.all([
        apiGet<{ users: AuthUser[] }>('/admin/users'),
        apiGet<{ specialists: AuthUser[] }>('/admin/specialists/pending'),
      ])
      setUsers(usersRes.users)
      setPending(pendingRes.specialists)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  useEffect(() => {
    load()
  }, [])

  function draftFor(user: AuthUser) {
    return drafts[user.id] ?? { role: user.role, line: user.line ?? '' }
  }

  function setDraft(id: string, patch: Partial<{ role: Role; line: SupportLine }>) {
    setDrafts((prev) => ({ ...prev, [id]: { ...(prev[id] ?? { role: 'user', line: '' }), ...patch } }))
  }

  async function decide(id: string, action: 'approve' | 'reject') {
    setBusyId(id)
    setError(null)
    try {
      await apiPost(`/admin/specialists/${id}/${action}`)
      await load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusyId(null)
    }
  }

  async function saveRole(user: AuthUser) {
    const draft = draftFor(user)
    setBusyId(user.id)
    setError(null)
    try {
      await apiPost(`/admin/users/${user.id}/role`, { role: draft.role, line: draft.line })
      await load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="rm-page">
      {error && (
        <div className="rm-error" role="alert">
          {error}
        </div>
      )}

      <section>
        <h3 className="rm-section-title">Заявки на статус тех.специалиста</h3>
        {pending === null ? (
          <p className="rm-hint">Загрузка…</p>
        ) : pending.length === 0 ? (
          <p className="rm-hint">Нет заявок, ожидающих решения.</p>
        ) : (
          <div className="rm-table-wrap">
            <table className="rm-table">
              <thead>
                <tr>
                  <th>Имя</th>
                  <th>Email</th>
                  <th>Линия</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {pending.map((u) => (
                  <tr key={u.id}>
                    <td>{u.display_name}</td>
                    <td>{u.email}</td>
                    <td>{u.line || '—'}</td>
                    <td className="rm-actions">
                      <button className="rm-btn rm-btn-approve" disabled={busyId === u.id} onClick={() => decide(u.id, 'approve')}>
                        Одобрить
                      </button>
                      <button className="rm-btn rm-btn-reject" disabled={busyId === u.id} onClick={() => decide(u.id, 'reject')}>
                        Отклонить
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section style={{ marginTop: 28 }}>
        <h3 className="rm-section-title">Все пользователи</h3>
        {users === null ? (
          <p className="rm-hint">Загрузка…</p>
        ) : (
          <div className="rm-table-wrap">
            <table className="rm-table">
              <thead>
                <tr>
                  <th>Имя</th>
                  <th>Email</th>
                  <th>Роль</th>
                  <th>Линия</th>
                  <th>Статус заявки</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => {
                  const draft = draftFor(u)
                  const dirty = draft.role !== u.role || draft.line !== (u.line ?? '')
                  return (
                    <tr key={u.id}>
                      <td>{u.display_name}</td>
                      <td>{u.email}</td>
                      <td>
                        <select value={draft.role} onChange={(e) => setDraft(u.id, { role: e.target.value as Role })}>
                          {(Object.keys(ROLE_LABEL) as Role[]).map((r) => (
                            <option key={r} value={r}>
                              {ROLE_LABEL[r]}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <select value={draft.line} onChange={(e) => setDraft(u.id, { line: e.target.value as SupportLine })}>
                          {LINE_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>{u.specialist_status || '—'}</td>
                      <td className="rm-actions">
                        <button className="rm-btn rm-btn-save" disabled={!dirty || busyId === u.id} onClick={() => saveRole(u)}>
                          Сохранить
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
