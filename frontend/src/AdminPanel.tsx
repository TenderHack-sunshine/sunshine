import { useEffect, useState } from "react"
import { useAuth } from "./auth/AuthContext"
import RoleManagement from "./admin/RoleManagement"
import { apiGet } from "./api/client"

type RouteStep = { label: string; status: "done" | "skipped" | "escalated" }

type OverviewResponse = {
  total: number
  answered_by_ai: number
  answered_by_ai_percent: number
  escalated: number
  escalated_percent: number
  need_clarification: number
  need_clarification_percent: number
  in_progress: number
}

type ApiRequest = {
  id: string
  original_message: string
  status:
    | "processing"
    | "answered"
    | "need_clarification"
    | "blocked"
    | "escalated"
    | "ai_failed"
  topic?: string
  support_level?: string
  ai_status: string
  ai_answer?: string
  confidence?: number
  created_at: string
  updated_at: string
}

type RequestsResponse = {
  requests: ApiRequest[]
}

type Dialog = {
  id: string
  time: string
  date: string
  user: string
  org: string
  topic: string
  type: "non-technical" | "technical"
  direction: string
  directionLevel: "l1" | "l2" | "l3"
  result: "answered" | "escalated" | "insufficient" | "clarification"
  steps: RouteStep[]
  userMsg: string
  answer?: string
  sources?: string[]
  confidence?: number
}

const DIALOGS: Dialog[] = [
  {
    id: "D-1042",
    time: "14:32",
    date: "сегодня",
    user: "Смирнова И.В.",
    org: "ООО «Альфа»",
    topic: "Создание оферты",
    type: "non-technical",
    direction: "Базовая поддержка",
    directionLevel: "l1",
    result: "answered",
    userMsg: "Как создать и опубликовать оферту?",
    answer:
      "Ответ сформирован по материалам Портала. Инструкция по созданию оферты и СТЕ.",
    sources: [
      "Инструкция по созданию оферты и СТЕ: Раздел 2",
      "Инструкция по работе с Порталом для поставщика: Раздел 4",
    ],
    steps: [
      { label: "Запрос получен", status: "done" },
      { label: "Контекста достаточно", status: "done" },
      { label: "Тип: нетехнический", status: "done" },
      { label: "Тема: создание оферты", status: "done" },
      { label: "Базовая поддержка: L1", status: "done" },
      { label: "Поиск по базе знаний", status: "done" },
      { label: "Ответ достаточен", status: "done" },
    ],
  },
  {
    id: "D-1041",
    time: "13:55",
    date: "сегодня",
    user: "Петров А.С.",
    org: "ИП Петров",
    topic: "Электронная подпись",
    type: "technical",
    direction: "Техническая поддержка",
    directionLevel: "l3",
    result: "answered",
    userMsg: "Проблема с электронной подписью — сертификат не отображается",
    answer: "Ответ сформирован. Рекомендована проверка версии КриптоПро CSP.",
    sources: ["Инструкция по настройке рабочего места: Раздел 2"],
    steps: [
      { label: "Запрос получен", status: "done" },
      { label: "Тип: технический", status: "done" },
      { label: "L1, L2 — не требуются", status: "skipped" },
      { label: "Тема: электронная подпись", status: "done" },
      { label: "Техническая поддержка: L3", status: "done" },
      { label: "Поиск по базе знаний", status: "done" },
      { label: "Ответ достаточен", status: "done" },
    ],
  },
  {
    id: "D-1040",
    time: "13:21",
    date: "сегодня",
    user: "Козлова М.Н.",
    org: "ООО «Ресурс»",
    topic: "Загрузка файлов",
    type: "technical",
    direction: "Техническая поддержка",
    directionLevel: "l3",
    result: "escalated",
    userMsg: "Ошибка при загрузке документа — файл зависает",
    steps: [
      { label: "Запрос получен", status: "done" },
      { label: "Уточнение запрошено и получено", status: "done" },
      { label: "Тип: технический", status: "done" },
      { label: "L1, L2 — не требуются", status: "skipped" },
      { label: "Техническая поддержка: L3", status: "done" },
      { label: "Ответа в базе недостаточно", status: "escalated" },
      { label: "Передача специалисту", status: "escalated" },
    ],
  },
  {
    id: "D-1039",
    time: "12:47",
    date: "сегодня",
    user: "Фёдоров Д.К.",
    org: "АО «Снабжение»",
    topic: "Работа с МЧД",
    type: "non-technical",
    direction: "Базовая поддержка",
    directionLevel: "l1",
    result: "answered",
    userMsg: "Как создать машиночитаемую доверенность для сотрудника?",
    answer: "Ответ сформирован по материалам Портала.",
    sources: ["Инструкция по работе с МЧД: Раздел 3"],
    steps: [
      { label: "Запрос получен", status: "done" },
      { label: "Контекста достаточно", status: "done" },
      { label: "Тип: нетехнический", status: "done" },
      { label: "Тема: МЧД", status: "done" },
      { label: "Базовая поддержка: L1", status: "done" },
      { label: "Поиск по базе знаний", status: "done" },
      { label: "Ответ достаточен", status: "done" },
    ],
  },
  {
    id: "D-1038",
    time: "11:30",
    date: "сегодня",
    user: "Новикова Т.Г.",
    org: "ООО «Импульс»",
    topic: "Статус закупки",
    type: "non-technical",
    direction: "Методологическая поддержка",
    directionLevel: "l2",
    result: "answered",
    userMsg: "Как проверить статус закупки и есть ли возможность участия?",
    answer: "Ответ сформирован по материалам.",
    sources: ["Инструкция по работе с Порталом для поставщика: Раздел 5"],
    steps: [
      { label: "Запрос получен", status: "done" },
      { label: "Тип: нетехнический", status: "done" },
      { label: "Тема: статус закупки", status: "done" },
      { label: "Базовая поддержка — недостаточно", status: "done" },
      { label: "Методологическая поддержка: L2", status: "done" },
      { label: "Поиск по базе знаний", status: "done" },
      { label: "Ответ достаточен", status: "done" },
    ],
  },
  {
    id: "D-1037",
    time: "10:12",
    date: "сегодня",
    user: "Зайцев В.П.",
    org: "ИП Зайцев",
    topic: "Авторизация",
    type: "technical",
    direction: "Техническая поддержка",
    directionLevel: "l3",
    result: "escalated",
    userMsg: "Не могу войти в личный кабинет, выдаёт ошибку авторизации",
    steps: [
      { label: "Запрос получен", status: "done" },
      { label: "Тип: технический", status: "done" },
      { label: "L1, L2 — не требуются", status: "skipped" },
      { label: "Тема: авторизация", status: "done" },
      { label: "Техническая поддержка: L3", status: "done" },
      { label: "Ответа в базе недостаточно", status: "escalated" },
      { label: "Передача специалисту", status: "escalated" },
    ],
  },
  {
    id: "D-1036",
    time: "09:45",
    date: "сегодня",
    user: "Морозова Е.А.",
    org: "ООО «Техпоставка»",
    topic: "Создание оферты",
    type: "non-technical",
    direction: "Базовая поддержка",
    directionLevel: "l1",
    result: "answered",
    userMsg: "Как прикрепить технические условия к оферте?",
    answer: "Ответ сформирован.",
    sources: ["Инструкция по созданию оферты и СТЕ: Раздел 4"],
    steps: [
      { label: "Запрос получен", status: "done" },
      { label: "Уточнение запрошено и получено", status: "done" },
      { label: "Тип: нетехнический", status: "done" },
      { label: "Тема: создание оферты", status: "done" },
      { label: "Базовая поддержка: L1", status: "done" },
      { label: "Поиск по базе знаний", status: "done" },
      { label: "Ответ достаточен", status: "done" },
    ],
  },
]

const RESULT_LABEL: Record<string, string> = {
  answered: "Ответ дан",
  escalated: "Передано",
  insufficient: "Нет ответа",
  clarification: "Требуется уточнение",
}

const RESULT_CLASS: Record<string, string> = {
  answered: "ra-done",
  escalated: "ra-escalated",
  insufficient: "ra-insufficient",
  clarification: "ra-insufficient",
}

const TYPE_LABEL: Record<string, string> = {
  "non-technical": "Нетехнический",
  technical: "Технический",
}

type FilterDir = "all" | "l1" | "l2" | "l3"
type FilterResult = "all" | "answered" | "escalated"

function apiRequestToDialog(request: ApiRequest): Dialog {
  const created = new Date(request.created_at)

  const time = created.toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  })

  const level = request.support_level?.toLowerCase()

  const directionLevel: "l1" | "l2" | "l3" =
    level === "l2" ? "l2" : level === "l3" ? "l3" : "l1"

  const direction =
    directionLevel === "l3"
      ? "Техническая поддержка"
      : directionLevel === "l2"
        ? "Методологическая поддержка"
        : "Базовая поддержка"

  const result: Dialog["result"] =
    request.status === "escalated"
      ? "escalated"
      : request.status === "answered"
        ? "answered"
        : request.status === "need_clarification"
          ? "clarification"
          : "insufficient"

  const type: Dialog["type"] =
    directionLevel === "l3" ? "technical" : "non-technical"

  const steps: RouteStep[] = [
    {
      label: "Запрос получен",
      status: "done",
    },
    {
      label: `Тема: ${request.topic || "не определена"}`,
      status: "done",
    },
    {
      label: `${direction}: ${request.support_level || "—"}`,
      status: "done",
    },
  ]

  if (request.status === "need_clarification") {
    steps.push({
      label: "Запрошено уточнение",
      status: "done",
    })
  }

  if (request.status === "escalated") {
    steps.push({
      label: "Передача специалисту",
      status: "escalated",
    })
  }

  if (request.status === "answered") {
    steps.push({
      label: "Ответ сформирован",
      status: "done",
    })
  }

  return {
    id: request.id,
    time,
    date: "сегодня",

    // user_id backend сейчас скрывает, поэтому временно:
    user: "Пользователь",
    org: "Портал поставщиков",

    topic: request.topic || "Без темы",
    type,
    direction,
    directionLevel,
    result,
    steps,
    userMsg: request.original_message,
    answer: request.ai_answer,
    confidence: request.confidence,
  }
}

export default function AdminPanel() {
  const [overview, setOverview] = useState<OverviewResponse | null>(null)
  const [dialogs, setDialogs] = useState<Dialog[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Dialog | null>(null)
  const auth = useAuth()
  const [tab, setTab] = useState<"log" | "roles">("log")
  const [filterDir, setFilterDir] = useState<FilterDir>("all")
  const [filterResult, setFilterResult] = useState<FilterResult>("all")
  const [search, setSearch] = useState("")

  useEffect(() => {
    async function loadAnalytics() {
      try {
        setLoading(true)
        setError(null)

        const [overviewData, requestsData] = await Promise.all([
          apiGet<OverviewResponse>("/analytics/overview"),
          apiGet<RequestsResponse>("/analytics/requests"),
        ])

        const mapped = requestsData.requests.map(apiRequestToDialog)

        setOverview(overviewData)
        setDialogs(mapped)

        if (mapped.length > 0) {
          setSelected(mapped[0])
        }
      } catch (err) {
        console.error(err)
        setError("Не удалось загрузить аналитику")
      } finally {
        setLoading(false)
      }
    }

    loadAnalytics()

    const interval = window.setInterval(loadAnalytics, 10000)

    return () => {
      window.clearInterval(interval)
    }
  }, [auth.isStaff])

    const stats = [
    {
      label: "Диалогов сегодня",
      value: overview?.total ?? 0,
    },
    {
      label: "Ответил помощник",
      value: overview?.answered_by_ai ?? 0,
      sub: `${Math.round(overview?.answered_by_ai_percent ?? 0)}%`,
    },
    {
      label: "Передано специалисту",
      value: overview?.escalated ?? 0,
      sub: `${Math.round(overview?.escalated_percent ?? 0)}%`,
    },
    {
      label: "Требовалось уточнение",
      value: overview?.need_clarification ?? 0,
      sub: `${Math.round(overview?.need_clarification_percent ?? 0)}% диалогов`,
    },
  ]

  const filtered = dialogs.filter((d) => {
    if (filterDir !== "all" && d.directionLevel !== filterDir) return false
    if (filterResult !== "all" && d.result !== filterResult) return false
    if (search) {
      const q = search.toLowerCase()
      if (
        !d.topic.toLowerCase().includes(q) &&
        !d.user.toLowerCase().includes(q) &&
        !d.id.toLowerCase().includes(q)
      )
        return false
    }
    return true
  })

  if (loading && dialogs.length === 0) {
    return (
      <div className="ra-page">
        <div className="ra-page-header">
          <div>
            <h2 className="ra-page-title">Журнал обращений</h2>
            <p className="ra-page-sub">Загрузка аналитики…</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="ra-page">
      <div className="ra-page-header">
        <div>
          <h2 className="ra-page-title">
            {tab === "log" ? "Журнал обращений" : "Пользователи и роли"}
          </h2>
          <p className="ra-page-sub">
            {tab === "log"
              ? "Маршрутизация и результаты обработки диалогов"
              : "Заявки на статус тех.специалиста и назначение ролей"}
          </p>
        </div>
        {auth.isAdmin && (
          <div className="ra-filter-group" role="tablist" aria-label="Раздел администрирования">
            <button
              role="tab"
              aria-selected={tab === "log"}
              className={`ra-filter-btn${tab === "log" ? " active" : ""}`}
              onClick={() => setTab("log")}
            >
              Журнал обращений
            </button>
            <button
              role="tab"
              aria-selected={tab === "roles"}
              className={`ra-filter-btn${tab === "roles" ? " active" : ""}`}
              onClick={() => setTab("roles")}
            >
              Пользователи и роли
            </button>
          </div>
        )}
      </div>

      {tab === "roles" && auth.isAdmin ? (
        <RoleManagement />
      ) : (
        <>
      <div className="ra-stats-row">
        {stats.map((s) => (
          <div key={s.label} className="ra-stat-card">
            <div className="ra-stat-value">
              {s.value}
              {s.sub && <span className="ra-stat-pct">: {s.sub}</span>}
            </div>
            <div className="ra-stat-label">{s.label}</div>
          </div>
        ))}
      </div>

      <div className="ra-workspace">
        <div className="ra-table-side">
          <div className="ra-filters">
            <input
              className="ra-search"
              type="search"
              placeholder="Поиск по теме, пользователю, ID"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="Поиск"
            />
            <div
              className="ra-filter-group"
              role="group"
              aria-label="Направление"
            >
              {(["all", "l1", "l2", "l3"] as FilterDir[]).map((f) => (
                <button
                  key={f}
                  className={`ra-filter-btn${filterDir === f ? " active" : ""}`}
                  onClick={() => setFilterDir(f)}
                >
                  {f === "all" ? "Все" : f.toUpperCase()}
                </button>
              ))}
            </div>
            <div
              className="ra-filter-group"
              role="group"
              aria-label="Результат"
            >
              {(["all", "answered", "escalated"] as FilterResult[]).map((f) => (
                <button
                  key={f}
                  className={`ra-filter-btn${
                    filterResult === f ? " active" : ""
                  }`}
                  onClick={() => setFilterResult(f)}
                >
                  {f === "all"
                    ? "Все"
                    : f === "answered"
                      ? "Ответ дан"
                      : "Передано"}
                </button>
              ))}
            </div>
          </div>

          <div className="ra-table-wrap">
            <table className="ra-table" aria-label="Список диалогов">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Время</th>
                  <th>Тема</th>
                  <th>Тип</th>
                  <th>Направление</th>
                  <th>Результат</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((d) => (
                  <tr
                    key={d.id}
                    className={selected?.id === d.id ? "selected" : ""}
                    onClick={() => setSelected(d)}
                    tabIndex={0}
                    aria-selected={selected?.id === d.id}
                    onKeyDown={(e) => e.key === "Enter" && setSelected(d)}
                  >
                    <td className="ra-td-id">{d.id}</td>
                    <td className="ra-td-time">
                      {d.date === "сегодня" ? d.time : `${d.date}, ${d.time}`}
                    </td>
                    <td className="ra-td-topic">
                      <div className="ra-topic">{d.topic}</div>
                      <div className="ra-user-line">
                        {d.user}: {d.org}
                      </div>
                    </td>
                    <td>{TYPE_LABEL[d.type]}</td>
                    <td>
                      <div className="ra-dir-cell">
                        <span className={`ra-level-badge ${d.directionLevel}`}>
                          {d.directionLevel.toUpperCase()}
                        </span>
                        {d.direction}
                      </div>
                    </td>
                    <td>
                      <span
                        className={`ra-result-badge ${RESULT_CLASS[d.result]}`}
                      >
                        {RESULT_LABEL[d.result]}
                      </span>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={6} className="ra-empty">
                      Нет диалогов по выбранным фильтрам
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {selected && (
          <aside className="ra-detail" aria-label="Детали обращения">
            <div className="ra-detail-header">
              <div>
                <div className="ra-detail-id">{selected.id}</div>
                <div className="ra-detail-who">
                  {selected.user}: {selected.org}
                </div>
              </div>
              <span
                className={`ra-result-badge ${RESULT_CLASS[selected.result]}`}
              >
                {RESULT_LABEL[selected.result]}
              </span>
            </div>

            <div className="ra-detail-msg">
              <div className="ra-detail-msg-label">Вопрос пользователя</div>
              <div className="ra-detail-msg-text">«{selected.userMsg}»</div>
            </div>

            <div className="ra-detail-section-title">Как обработан запрос</div>

            {[
  	      { label: "Тип обращения", value: TYPE_LABEL[selected.type] },
              { label: "Тема", value: selected.topic },
              {
    		label: "Направление",
    		value: selected.direction,
    		level: selected.directionLevel,
  	      },
  	      { label: "Результат", value: RESULT_LABEL[selected.result] },
  	      {
    		label: "Уверенность AI",
    		value:
      		  selected.confidence !== undefined
        	    ? `${Math.round(selected.confidence * 100)}%`
                    : "—",
  	      },
            ].map((f) => (
              <div key={f.label} className="ra-detail-field">
                <div className="ra-detail-field-label">{f.label}</div>
                <div className="ra-detail-field-value">
                  {f.value}
                  {(f as any).level && (
                    <span className={`ra-level-badge ${(f as any).level}`}>
                      {(f as any).level.toUpperCase()}
                    </span>
                  )}
                </div>
              </div>
            ))}

            <div className="ra-steps-label">Шаги обработки</div>
            <div className="ra-steps">
              {selected.steps.map((step, i) => (
                <div key={i} className={`ra-step ${step.status}`}>
                  <div className="ra-step-dot" aria-hidden="true">
                    {step.status === "done" && (
                      <svg width="9" height="9" viewBox="0 0 9 9" fill="none">
                        <path
                          d="M1.5 4.5l2 2 4-4"
                          stroke="#238636"
                          strokeWidth="1.5"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    )}
                    {step.status === "skipped" && (
                      <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
                        <path
                          d="M2 2l4 4M6 2l-4 4"
                          stroke="#adb5c4"
                          strokeWidth="1.2"
                          strokeLinecap="round"
                        />
                      </svg>
                    )}
                    {step.status === "escalated" && (
                      <svg width="9" height="9" viewBox="0 0 9 9" fill="none">
                        <path
                          d="M4.5 2v2.5M4.5 6h.01"
                          stroke="#92400e"
                          strokeWidth="1.4"
                          strokeLinecap="round"
                        />
                      </svg>
                    )}
                  </div>
                  <div className="ra-step-label">{step.label}</div>
                </div>
              ))}
            </div>

            {selected.sources && selected.sources.length > 0 && (
              <>
                <div className="ra-steps-label" style={{ marginTop: 16 }}>
                  Источники
                </div>
                <div className="ra-sources-list">
                  {selected.sources.map((src, i) => (
                    <div key={i} className="ra-source-row">
                      <svg
                        width="12"
                        height="12"
                        viewBox="0 0 12 12"
                        fill="none"
                        aria-hidden="true"
                        style={{
                          flexShrink: 0,
                          color: "#adb5c4",
                          marginTop: 1,
                        }}
                      >
                        <rect
                          x="1"
                          y="1"
                          width="10"
                          height="10"
                          rx="1.5"
                          stroke="currentColor"
                          strokeWidth="1.1"
                        />
                        <path
                          d="M3.5 4h5M3.5 6.5h5M3.5 9h3"
                          stroke="currentColor"
                          strokeWidth="1"
                          strokeLinecap="round"
                        />
                      </svg>
                      <span className="ra-source-text">{src}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </aside>
        )}
      </div>
        </>
      )}
    </div>
  )
}
