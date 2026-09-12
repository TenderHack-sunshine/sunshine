import { useState, useRef, useEffect } from "react";
import AdminPanel from "./AdminPanel";
import portalLogo from "@/imports/image-1.png";

type ChatState = "idle" | "processing" | "needs_clarification" | "answered" | "insufficient_knowledge" | "escalated";

type Source = { title: string; section: string; page?: string };

type RouteStep = { label: string; status: "done" | "skipped" | "escalated" };

type RouteInfo = {
  type: string;
  topic: string;
  direction: string;
  directionLevel: string;
  result: string;
  steps: RouteStep[];
};

type Message = {
  id: number;
  role: "user" | "assistant";
  time: string;
  text?: string;
  isProcessing?: boolean;
  processingLabel?: string;
  sources?: Source[];
  quickReplies?: string[];
  isEscalation?: boolean;
  isEscalated?: boolean;
  isClarification?: boolean;
};

const DEMO_SCENARIOS = {
  oferta: {
    clarification: null,
    routeInfo: {
      type: "Нетехнический",
      topic: "Создание оферты",
      direction: "Базовая поддержка",
      directionLevel: "l1",
      result: "Ответ найден",
      steps: [
        { label: "Запрос получен", status: "done" },
        { label: "Контекста достаточно", status: "done" },
        { label: "Тема: создание оферты", status: "done" },
        { label: "Базовая поддержка: L1", status: "done" },
        { label: "Поиск по базе знаний", status: "done" },
        { label: "Ответ достаточен", status: "done" },
      ] as RouteStep[],
    } as RouteInfo,
    answer: `Оферта — это ценовое предложение поставщика на конкретный товар или услугу. Чтобы создать и опубликовать оферту:\n\n1. Откройте раздел **«Товары и услуги»** в личном кабинете и выберите нужную позицию из каталога или создайте новую.\n2. Перейдите на вкладку **«Оферты»** и нажмите **«Добавить ценовое предложение»**.\n3. Заполните обязательные поля: цена за единицу, ставка НДС, срок поставки, минимальная партия.\n4. При необходимости прикрепите спецификацию или технические условия (СТЕ).\n5. Подпишите оферту действующей электронной подписью и отправьте на публикацию.\n\nПосле проверки модератором оферта появится в каталоге и станет доступна заказчикам.`,
    sources: [
      { title: "Инструкция по созданию оферты и СТЕ", section: "Раздел 2. Создание ценового предложения", page: "стр. 6–14" },
      { title: "Инструкция по работе с Порталом для поставщика", section: "Раздел 4. Товары и каталог", page: "стр. 22" },
    ] as Source[],
  },
  mchd: {
    clarification: null,
    routeInfo: {
      type: "Нетехнический",
      topic: "Машиночитаемые доверенности",
      direction: "Базовая поддержка",
      directionLevel: "l1",
      result: "Ответ найден",
      steps: [
        { label: "Запрос получен", status: "done" },
        { label: "Контекста достаточно", status: "done" },
        { label: "Тема: МЧД", status: "done" },
        { label: "Базовая поддержка: L1", status: "done" },
        { label: "Поиск по базе знаний", status: "done" },
        { label: "Ответ достаточен", status: "done" },
      ] as RouteStep[],
    } as RouteInfo,
    answer: `Для работы с машиночитаемой доверенностью (МЧД) выполните следующие действия:\n\n1. Перейдите в личный кабинет и откройте раздел **«Доверенности»**.\n2. Нажмите **«Создать доверенность»** и заполните данные представителя: ФИО, ИНН, перечень полномочий.\n3. Укажите срок действия доверенности.\n4. Подпишите документ действующей электронной подписью руководителя организации.\n5. После сохранения доверенность получит статус **«Активна»** и станет доступна для использования.`,
    sources: [
      { title: "Инструкция по работе с машиночитаемыми доверенностями", section: "Раздел 3. Создание и подпись МЧД", page: "стр. 12–18" },
      { title: "Инструкция по работе с Порталом для поставщика", section: "Раздел 7. Доверенности", page: "стр. 44" },
    ] as Source[],
  },
  ep: {
    clarification: "Уточните, пожалуйста: на каком этапе возникает проблема? Появляется ли сообщение об ошибке?",
    clarificationReplies: ["Кнопка не реагирует", "Появляется ошибка", "Не отображается сертификат"],
    routeInfo: {
      type: "Технический",
      topic: "Электронная подпись",
      direction: "Техническая поддержка",
      directionLevel: "l3",
      result: "Ответ найден",
      steps: [
        { label: "Запрос получен", status: "done" },
        { label: "Тип: технический", status: "done" },
        { label: "L1, L2 — не требуются", status: "skipped" },
        { label: "Техническая поддержка: L3", status: "done" },
        { label: "Поиск по базе знаний", status: "done" },
        { label: "Ответ достаточен", status: "done" },
      ] as RouteStep[],
    } as RouteInfo,
    answer: `Проблема с электронной подписью чаще всего вызвана одной из следующих причин:\n\n1. **Истёк срок сертификата** — проверьте дату действия ЭП в хранилище сертификатов.\n2. **Не установлен или устарел КриптоПро CSP** — требуется версия 5.0 и выше.\n3. **Браузер не поддерживает плагин** — используйте Яндекс Браузер с установленным расширением.\n4. **Сертификат не привязан к профилю** — перейдите в настройки профиля и добавьте сертификат вручную.\n\nЕсли после выполнения этих шагов проблема сохраняется, обратитесь в техническую поддержку.`,
    sources: [
      { title: "Инструкция по настройке рабочего места", section: "Раздел 2. Электронная подпись", page: "стр. 8–15" },
      { title: "Инструкция по работе с Порталом для поставщика", section: "Раздел 1. Требования к рабочему месту", page: "стр. 4" },
    ] as Source[],
  },
  file: {
    clarification: "Уточните, пожалуйста: что именно происходит при загрузке? Появляется ли сообщение об ошибке?",
    clarificationReplies: ["Ошибка формата файла", "Загрузка зависает", "Превышен допустимый размер"],
    routeInfo: {
      type: "Технический",
      topic: "Загрузка файлов",
      direction: "Техническая поддержка",
      directionLevel: "l3",
      result: "Недостаточно подтверждённой информации — передача специалисту",
      steps: [
        { label: "Запрос получен", status: "done" },
        { label: "Уточнение получено", status: "done" },
        { label: "Тип: технический", status: "done" },
        { label: "L1, L2 — не требуются", status: "skipped" },
        { label: "Техническая поддержка: L3", status: "done" },
        { label: "Ответа в базе недостаточно — передача специалисту", status: "escalated" },
      ] as RouteStep[],
    } as RouteInfo,
    answer: null,
    escalation: true,
  },
} as const;

type ScenarioKey = keyof typeof DEMO_SCENARIOS;

const HISTORY_ITEMS = [
  { id: 1, title: "Создание оферты", preview: "Как создать и опубликовать оферту?", date: "сегодня", status: "active" as const, scenario: "oferta" as ScenarioKey },
  { id: 2, title: "Работа с МЧД", preview: "Как создать машиночитаемую доверенность?", date: "вчера", status: "done" as const, scenario: "mchd" as ScenarioKey },
  { id: 3, title: "Ошибка при загрузке", preview: "Ошибка при загрузке файла документа", date: "23 мая", status: "escalated" as const, scenario: "file" as ScenarioKey },
  { id: 4, title: "Статус закупки", preview: "Как отследить статус закупки?", date: "21 мая", status: "done" as const, scenario: "mchd" as ScenarioKey },
];

const STATUS_LABELS = { active: "В работе", done: "Завершено", escalated: "Специалисту", info: "Уточнение" };
const STATUS_CLASSES = { active: "status-active", done: "status-done", escalated: "status-escalated", info: "status-info" };

const PROC_STAGES = ["Помощник проверяет материалы Портала…", "Определяю тему обращения", "Проверяю официальные материалы", "Формирую ответ"];

function nowTime() {
  return new Date().toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" });
}

function renderText(text: string) {
  const lines = text.split("\n");
  const out: React.ReactNode[] = [];
  let listItems: string[] = [];

  const flushList = (key: string) => {
    if (!listItems.length) return;
    out.push(
      <ol key={key}>
        {listItems.map((li, i) => (
          <li key={i} dangerouslySetInnerHTML={{ __html: li.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>") }} />
        ))}
      </ol>
    );
    listItems = [];
  };

  lines.forEach((line, i) => {
    const m = line.match(/^\d+\.\s+(.*)/);
    if (m) {
      listItems.push(m[1]);
    } else {
      flushList(`list-${i}`);
      if (line.trim())
        out.push(<p key={i} dangerouslySetInnerHTML={{ __html: line.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>") }} />);
    }
  });
  flushList("list-end");
  return <div className="msg-reply-text">{out}</div>;
}

function delay(ms: number) { return new Promise(r => setTimeout(r, ms)); }

export default function App() {
  const [page, setPage] = useState<"support" | "admin">("support");
  const [selectedHistory, setSelectedHistory] = useState(1);
  const [messages, setMessages] = useState<Message[]>([]);
  const [chatState, setChatState] = useState<ChatState>("idle");
  const [inputText, setInputText] = useState("");
  const [openSources, setOpenSources] = useState<Set<number>>(new Set());
  const [feedbackGiven, setFeedbackGiven] = useState<Record<number, "yes" | "no">>({});
  const [showPostFeedback, setShowPostFeedback] = useState<Set<number>>(new Set());
  const [pendingScenario, setPendingScenario] = useState<ScenarioKey | null>(null);
  const msgIdRef = useRef(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const liveRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function announce(s: string) {
    if (liveRef.current) liveRef.current.textContent = s;
  }

  function addMsg(m: Omit<Message, "id" | "time">): number {
    const id = ++msgIdRef.current;
    setMessages(prev => [...prev, { ...m, id, time: nowTime() }]);
    return id;
  }

  function patchMsg(id: number, patch: Partial<Message>) {
    setMessages(prev => prev.map(m => m.id === id ? { ...m, ...patch } : m));
  }

  function removeMsg(id: number) {
    setMessages(prev => prev.filter(m => m.id !== id));
  }

  function resetChat() {
    setMessages([]);
    setChatState("idle");
    setInputText("");
    setOpenSources(new Set());
    setFeedbackGiven({});
    setShowPostFeedback(new Set());
    setPendingScenario(null);
    msgIdRef.current = 0;
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }

  function selectHistory(item: typeof HISTORY_ITEMS[0]) {
    setSelectedHistory(item.id);
    resetChat();
  }

  async function runScenario(key: ScenarioKey, userText: string) {
    const s = DEMO_SCENARIOS[key];
    addMsg({ role: "user", text: userText });

    if ((s as any).clarification) {
      await delay(600);
      addMsg({
        role: "assistant",
        text: (s as any).clarification,
        isClarification: true,
        quickReplies: (s as any).clarificationReplies,
      });
      setChatState("needs_clarification");
      setPendingScenario(key);
      announce("Нужно уточнение");
    } else {
      await runProcessing(key);
    }
  }

  async function runProcessing(key: ScenarioKey) {
    const s = DEMO_SCENARIOS[key];
    const procId = addMsg({ role: "assistant", isProcessing: true, processingLabel: PROC_STAGES[0] });
    setChatState("processing");

    for (let i = 1; i < PROC_STAGES.length; i++) {
      await delay(850);
      patchMsg(procId, { processingLabel: PROC_STAGES[i] });
      announce(PROC_STAGES[i]);
    }
    await delay(600);
    removeMsg(procId);

    if ((s as any).escalation) {
      addMsg({ role: "assistant", isEscalation: true });
      setChatState("insufficient_knowledge");
    } else {
      addMsg({
        role: "assistant",
        text: (s as any).answer,
        sources: (s as any).sources,
      });
      setChatState("answered");
      announce("Ответ получен");
    }
  }

  async function handleClarificationReply(reply: string) {
    addMsg({ role: "user", text: reply });
    setPendingScenario(null);
    if (pendingScenario) await runProcessing(pendingScenario);
  }

  async function handleArbitrary(text: string) {
    addMsg({ role: "user", text });
    await delay(700);
    addMsg({
      role: "assistant",
      text: "Уточните, пожалуйста: к какому разделу Портала относится ваш вопрос? Это поможет быстрее найти нужную информацию.",
      isClarification: true,
    });
    setChatState("needs_clarification");
  }

  function handleEscalate() {
    addMsg({ role: "assistant", isEscalated: true });
    setChatState("escalated");
  }

  async function handleSend() {
    const text = inputText.trim();
    if (!text || chatState === "processing") return;
    setInputText("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    if (chatState === "needs_clarification") {
      handleClarificationReply(text);
      return;
    }
    handleArbitrary(text);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  }

  function handleTextarea(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setInputText(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
  }

  function toggleSources(id: number) {
    setOpenSources(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function giveFeedback(id: number, val: "yes" | "no") {
    setFeedbackGiven(prev => ({ ...prev, [id]: val }));
    if (val === "no") setShowPostFeedback(prev => new Set(prev).add(id));
  }

  const QUICK_Q = [
    { label: "Как создать оферту?", key: "oferta" as ScenarioKey },
    { label: "Работа с МЧД", key: "mchd" as ScenarioKey },
    { label: "Проблема с электронной подписью", key: "ep" as ScenarioKey },
    { label: "Ошибка при загрузке файла", key: "file" as ScenarioKey },
  ];

  return (
    <>
      <header className="portal-header">
        <a className="portal-logo" href="#" aria-label="Портал поставщиков">
          <img src={portalLogo} alt="" aria-hidden="true" style={{ width: 32, height: 32, objectFit: 'contain' }} />
          <span className="portal-logo-text">Портал <span>поставщиков</span></span>
        </a>

        <nav className="portal-nav-main" aria-label="Основная навигация">
          {["Главная", "Закупки", "Товары", "Договоры", "Поддержка", "Аналитика"].map(item => (
  	    <button
    	      key={item}
    	      className={`nav-item${
      		(item === "Поддержка" && page === "support") ||
      		(item === "Аналитика" && page === "admin")
        	  ? " active"
        	  : ""
   	      }`}
   	      aria-current={
     		(item === "Поддержка" && page === "support") ||
      		(item === "Аналитика" && page === "admin")
        	  ? "page"
        	  : undefined
    	      }
    	      onClick={() => {
      		if (item === "Поддержка") {
        	  setPage("support")
      		}

      		if (item === "Аналитика") {
        	  setPage("admin")
      		}
    	      }}
  	    >
    	      {item}
  	    </button>
	  ))}
        </nav>

        <div className="portal-header-right">
          <button
            className={`nav-item${page === "admin" ? " active" : ""}`}
            style={{ height: 52, fontSize: 13 }}
            onClick={() => setPage(page === "admin" ? "support" : "admin")}
            aria-current={page === "admin" ? "page" : undefined}
          >
            Администрирование
          </button>
          <button className="header-icon-btn" aria-label="Уведомления">
            <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
              <path d="M7.5 1a4.5 4.5 0 0 1 4.5 4.5v2l1 2H2l1-2V5.5A4.5 4.5 0 0 1 7.5 1z" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
              <path d="M6 12.5a1.5 1.5 0 0 0 3 0" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
            </svg>
          </button>
          <button className="user-badge" aria-label="Профиль">
            <div className="user-avatar" aria-hidden="true">АО</div>
            <span className="user-name">ООО «Альфа»</span>
          </button>
        </div>
      </header>

      {page === "admin" && <AdminPanel />}

      {page === "support" && <main className="page-content">
        <nav className="breadcrumbs" aria-label="Навигационная цепочка">
          <a href="#">Главная</a>
          <span className="sep" aria-hidden="true">/</span>
          <span className="current">Поддержка</span>
        </nav>

        <div className="page-heading-row">
          <h1 className="page-heading">Поддержка</h1>
          <span className="page-subheading">Задайте вопрос о работе с Порталом</span>
        </div>

        <div className="support-workspace">
          <aside className="history-panel" aria-label="Диалоги">
            <div className="history-panel-header">
              <span className="panel-title">Диалоги</span>
              <button className="btn-new" onClick={resetChat}>
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true">
                  <path d="M5 1v8M1 5h8" stroke="#fff" strokeWidth="1.7" strokeLinecap="round" />
                </svg>
                Новый диалог
              </button>
            </div>
            <div className="history-list" role="list">
              {HISTORY_ITEMS.map(item => (
                <div
                  key={item.id}
                  className={`history-item${selectedHistory === item.id ? " selected" : ""}`}
                  role="listitem"
                  tabIndex={0}
                  aria-selected={selectedHistory === item.id}
                  onClick={() => selectHistory(item)}
                  onKeyDown={e => e.key === "Enter" && selectHistory(item)}
                >
                  <div className="history-item-title">{item.title}</div>
                  <div className="history-item-preview">{item.preview}</div>
                  <div className="history-item-meta">
                    <span className="history-item-date">{item.date}</span>
                    <span className={`status-pill ${STATUS_CLASSES[item.status]}`}>
                      {STATUS_LABELS[item.status]}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </aside>

          <div style={{ position: "relative", display: "flex", flexDirection: "column", minHeight: 0 }}>
            <section className="chat-panel" aria-label="Переписка">
              <div className="chat-header">
                <div className="chat-header-icon" aria-hidden="true">
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M2 11.5l.5-3L2 3h12l-.5 5.5L14 11.5l-4.5 1-1 2-1-2L2 11.5z" stroke="#697386" strokeWidth="1.3" strokeLinejoin="round" />
                  </svg>
                </div>
                <div className="chat-header-info">
                  <div className="chat-title">Поддержка Портала</div>
                  <div className="chat-desc">Автоматический помощник или специалист поддержки</div>
                </div>
              </div>

              <div className="chat-messages" role="log" aria-live="polite" aria-label="Переписка">
                {messages.length === 0 && (
                  <div className="chat-empty">
                    <p className="chat-greeting-text">
                      Здравствуйте! Опишите, что вы хотите сделать на Портале или какая ошибка возникла. Если информации будет недостаточно, я задам уточняющий вопрос.
                    </p>
                    <div className="quick-questions">
                      {QUICK_Q.map(q => (
                        <button key={q.key} className="quick-btn" onClick={() => runScenario(q.key, q.label)}>
                          {q.label}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {messages.map(msg => {
                  if (msg.role === "user") {
                    return (
                      <div key={msg.id} className="msg-block user">
                        <div className="msg-meta">
                          <span className="msg-meta-name">Вы</span>
                          <span>·</span>
                          <span>{msg.time}</span>
                        </div>
                        <div className="msg-bubble-user">{msg.text}</div>
                      </div>
                    );
                  }

                  if (msg.isProcessing) {
                    return (
                      <div key={msg.id} className="msg-block assistant">
                        <div className="msg-meta">
                          <span className="msg-meta-name">Помощник Портала</span>
                          <span>·</span>
                          <span>{msg.time}</span>
                        </div>
                        <div className="processing-row">
                          <div className="dots" aria-hidden="true">
                            <div className="dot-anim" /><div className="dot-anim" /><div className="dot-anim" />
                          </div>
                          <span>{msg.processingLabel}</span>
                        </div>
                      </div>
                    );
                  }

                  if (msg.isEscalation) {
                    return (
                      <div key={msg.id} className="msg-block assistant">
                        <div className="msg-meta">
                          <span className="msg-meta-name">Помощник Портала</span>
                          <span>·</span>
                          <span>{msg.time}</span>
                        </div>
                        <div className="msg-reply">
                          <div className="escalation-block">
                            В базе знаний нет подтверждённого решения для описанной ситуации. Чтобы не вводить вас в заблуждение, я могу передать диалог специалисту.
                          </div>
                          <div className="escalation-actions">
                            <button className="btn-primary" onClick={handleEscalate}>Передать специалисту</button>
                            <button className="btn-secondary-sm">Дополнить описание</button>
                          </div>
                        </div>
                      </div>
                    );
                  }

                  if (msg.isEscalated) {
                    return (
                      <div key={msg.id} className="msg-block assistant">
                        <div className="msg-meta">
                          <span className="msg-meta-name">Помощник Портала</span>
                          <span>·</span>
                          <span>{msg.time}</span>
                        </div>
                        <div className="msg-reply">
                          <div className="escalated-note">
                            <strong>Диалог передан в техническую поддержку.</strong><br />
                            Специалист получит историю диалога, ваши уточнения и найденные материалы. Повторно описывать ситуацию не потребуется.
                          </div>
                          <div className="escalated-context" style={{ marginTop: 10 }}>
                            <div className="escalated-context-title">Что получит специалист</div>
                            <div className="ctx-row"><span className="ctx-key">Тема:</span> Загрузка файлов</div>
                            <div className="ctx-row"><span className="ctx-key">Тип:</span> Технический</div>
                            <div className="ctx-row"><span className="ctx-key">Направление:</span> Техническая поддержка: L3</div>
                            <div className="ctx-row"><span className="ctx-key">Проверено:</span> База знаний — ответа недостаточно</div>
                            <div className="ctx-row"><span className="ctx-key">История:</span> Вопрос и уточнения пользователя</div>
                          </div>
                        </div>
                      </div>
                    );
                  }

                  const srcOpen = openSources.has(msg.id);
                  const fb = feedbackGiven[msg.id];
                  const showPost = showPostFeedback.has(msg.id);

                  return (
                    <div key={msg.id} className="msg-block assistant">
                      <div className="msg-meta">
                        <span className="msg-meta-name">Помощник Портала</span>
                        <span>·</span>
                        <span>{msg.time}</span>
                        {!msg.isClarification && <span className="msg-auto-tag">Автоматический ответ</span>}
                      </div>
                      <div className="msg-reply">
                        {msg.text && renderText(msg.text)}

                        {msg.quickReplies && (
                          <div className="chat-replies">
                            {msg.quickReplies.map(r => (
                              <button key={r} className="quick-btn" onClick={() => handleClarificationReply(r)}>{r}</button>
                            ))}
                          </div>
                        )}

                        {msg.sources && (
                          <div className="msg-sources-wrap">
                            <div className="sources-note">Ответ подготовлен по материалам Портала</div>
                            <button
                              className={`sources-toggle${srcOpen ? " open" : ""}`}
                              onClick={() => toggleSources(msg.id)}
                              aria-expanded={srcOpen}
                            >
                              <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true">
                                <path d="M3 2l4 3-4 3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
                              </svg>
                              Источники ответа: {msg.sources.length}
                            </button>
                            {srcOpen && (
                              <div className="sources-list">
                                {msg.sources.map((src, i) => (
                                  <div key={i} className="source-row">
                                    <div className="source-row-icon" aria-hidden="true">
                                      <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
                                        <rect x="1.5" y="1" width="10" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.2" />
                                        <path d="M4 4.5h5M4 7h5M4 9.5h3" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
                                      </svg>
                                    </div>
                                    <div className="source-row-body">
                                      <div className="source-row-title">{src.title}</div>
                                      <div className="source-row-desc">{src.section}{src.page ? `, ${src.page}` : ""}</div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}

                        {msg.sources && (
                          <div className="msg-feedback">
                            {!fb ? (
                              <>
                                <span className="feedback-label">Ответ помог?</span>
                                <button className="feedback-btn yes" onClick={() => giveFeedback(msg.id, "yes")}>
                                  <svg width="11" height="11" viewBox="0 0 11 11" fill="none" aria-hidden="true">
                                    <path d="M2 5.5l2.5 2.5 4.5-4.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
                                  </svg>
                                  Да
                                </button>
                                <button className="feedback-btn no" onClick={() => giveFeedback(msg.id, "no")}>Нет</button>
                              </>
                            ) : fb === "yes" ? (
                              <span style={{ fontSize: 13, color: "#238636" }}>Спасибо за оценку</span>
                            ) : showPost ? (
                              <div className="post-feedback">
                                <span className="post-feedback-label">Что сделать дальше?</span>
                                <button className="text-btn">Уточнить вопрос</button>
                                <button className="text-btn danger" onClick={handleEscalate}>Передать специалисту</button>
                              </div>
                            ) : null}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
                <div ref={messagesEndRef} />
              </div>

              <div className="chat-composer">
                <form onSubmit={e => { e.preventDefault(); handleSend(); }}>
                  <label htmlFor="chat-input" className="sr-only">Введите вопрос</label>
                  <div className="composer-field">
                    <textarea
                      id="chat-input"
                      ref={textareaRef}
                      className="composer-textarea"
                      placeholder="Опишите вопрос или приложите скриншот ошибки"
                      value={inputText}
                      onChange={handleTextarea}
                      onKeyDown={handleKeyDown}
                      rows={1}
                      disabled={chatState === "processing"}
                    />
                    <div className="composer-btns">
                      <button type="button" className="composer-icon-btn" aria-label="Прикрепить файл">
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                          <path d="M11.5 6L6 11.5a3.5 3.5 0 0 1-5-5l5.5-5.5a2 2 0 0 1 2.8 2.8L4 9.1a.5.5 0 0 1-.7-.7L8.5 3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
                        </svg>
                      </button>
                      <button
                        type="submit"
                        className="send-btn"
                        disabled={!inputText.trim() || chatState === "processing"}
                        aria-label="Отправить"
                      >
                        <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
                          <path d="M2 6.5h9M8 3l3.5 3.5L8 10" stroke="#fff" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      </button>
                    </div>
                  </div>
                </form>
                <div className="composer-hint">Ответ формируется на основе официальной базы знаний Портала.</div>
              </div>
            </section>

          </div>
        </div>
      </main>}

      <span ref={liveRef} aria-live="polite" className="sr-only" />
    </>
  );
}
