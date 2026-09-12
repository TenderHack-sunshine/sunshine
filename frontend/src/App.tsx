import { useState, useRef, useEffect } from "react";
import AdminPanel from "./AdminPanel";
import portalLogo from "@/imports/image-1.png";
import { apiPost } from "./api/client";
import { apiGet } from "./api/client";
import type { ApiMessage, ApiSource, ApiSupportRequest, RequestStatus, SupportResponse } from "./api";

type ChatState = "idle" | "processing" | "needs_clarification" | "answered" | "insufficient_knowledge" | "escalated";

type Source = { title: string; section: string; page?: string };

type Message = {
  id: number;
  role: "user" | "assistant";
  time: string;
  text?: string;
  isProcessing?: boolean;
  processingLabel?: string;
  sources?: Source[];
  quickReplies?: string[];
  isEscalated?: boolean;
  isClarification?: boolean;
  requestId?: string;
};

type HistoryStatus = "active" | "done" | "escalated" | "info";

type HistoryItem = {
  id: string;
  title: string;
  preview: string;
  date: string;
  status: HistoryStatus;
  request: ApiSupportRequest;
};

const STATUS_LABELS: Record<HistoryStatus, string> = { active: "В работе", done: "Завершено", escalated: "Специалисту", info: "Уточнение" };
const STATUS_CLASSES: Record<HistoryStatus, string> = { active: "status-active", done: "status-done", escalated: "status-escalated", info: "status-info" };

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

function toSources(sources: ApiSource[] = []): Source[] {
  return sources.map((source) => ({
    title: source.document,
    section: source.section || "Материал базы знаний",
    page: source.page ? `стр. ${source.page}` : undefined,
  }));
}

function historyStatus(status: RequestStatus): HistoryStatus {
  if (status === "processing" || status === "ai_failed") return "active";
  if (status === "need_clarification") return "info";
  if (status === "escalated") return "escalated";
  return "done";
}

function formatDate(value: string): string {
  const date = new Date(value);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  const sameDay = (left: Date, right: Date) => left.toDateString() === right.toDateString();
  if (sameDay(date, today)) return "сегодня";
  if (sameDay(date, yesterday)) return "вчера";
  return date.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
}

function formatTime(value: string): string {
  return new Date(value).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

function historyItem(request: ApiSupportRequest): HistoryItem {
  const preview = request.original_message.trim();
  return {
    id: request.id,
    title: request.topic?.trim() || (preview.length > 36 ? `${preview.slice(0, 36)}…` : preview),
    preview: preview.length > 72 ? `${preview.slice(0, 72)}…` : preview,
    date: formatDate(request.created_at),
    status: historyStatus(request.status),
    request,
  };
}

function chatStateForRequest(status: RequestStatus): ChatState {
  if (status === "processing") return "processing";
  if (status === "need_clarification") return "needs_clarification";
  if (status === "escalated") return "escalated";
  if (status === "answered" || status === "blocked") return "answered";
  return "idle";
}

function messagesFromApi(messages: ApiMessage[], request: ApiSupportRequest): Message[] {
  return messages.map((message, index) => {
    const isAssistant = message.sender_type !== "USER";
    const isAnswer = isAssistant && (request.status === "answered" || request.status === "blocked") && request.ai_answer === message.text;
    const sources = isAnswer ? toSources(request.sources) : [];
    return {
      id: index + 1,
      role: isAssistant ? "assistant" : "user",
      time: formatTime(message.created_at),
      text: message.text,
      requestId: request.id,
      isClarification: isAssistant && request.status === "need_clarification",
      isEscalated: isAssistant && request.status === "escalated",
      sources: sources.length ? sources : undefined,
    };
  });
}

export default function App() {
  const [page, setPage] = useState<"support" | "admin">("support");
  const [historyItems, setHistoryItems] = useState<HistoryItem[]>([]);
  const [selectedHistory, setSelectedHistory] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [messages, setMessages] = useState<Message[]>([]);
  const [chatState, setChatState] = useState<ChatState>("idle");
  const [inputText, setInputText] = useState("");
  const [openSources, setOpenSources] = useState<Set<number>>(new Set());
  const [feedbackGiven, setFeedbackGiven] = useState<Record<number, "yes" | "no">>({});
  const [showPostFeedback, setShowPostFeedback] = useState<Set<number>>(new Set());
  const [activeRequestId, setActiveRequestId] = useState<string | null>(null);
  const [chatError, setChatError] = useState("");
  const msgIdRef = useRef(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const liveRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function loadHistory() {
    try {
      setHistoryLoading(true);
      const response = await apiGet<{ requests: ApiSupportRequest[] }>("/support/requests");
      setHistoryItems(response.requests.map(historyItem));
    } catch (error) {
      setChatError(error instanceof Error ? error.message : "Не удалось загрузить историю диалогов.");
    } finally {
      setHistoryLoading(false);
    }
  }

  useEffect(() => {
    void loadHistory();
  }, []);

  function announce(s: string) {
    if (liveRef.current) liveRef.current.textContent = s;
  }

  function addMsg(m: Omit<Message, "id" | "time">): number {
    const id = ++msgIdRef.current;
    setMessages(prev => [...prev, { ...m, id, time: nowTime() }]);
    return id;
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
    setActiveRequestId(null);
    setChatError("");
    msgIdRef.current = 0;
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }

  function startNewDialog() {
    if (chatState === "processing") return;
    setSelectedHistory(null);
    resetChat();
  }

  async function selectHistory(item: HistoryItem) {
    if (chatState === "processing") return;
    setSelectedHistory(item.id);
    setActiveRequestId(item.id);
    setMessages([]);
    setOpenSources(new Set());
    setFeedbackGiven({});
    setShowPostFeedback(new Set());
    setChatError("");
    setChatState(chatStateForRequest(item.request.status));
    msgIdRef.current = 0;
    try {
      const response = await apiGet<{ messages: ApiMessage[] }>(`/support/requests/${encodeURIComponent(item.id)}/messages`);
      const loaded = messagesFromApi(response.messages, item.request);
      msgIdRef.current = loaded.length;
      setMessages(loaded);
    } catch (error) {
      setChatState("idle");
      setChatError(error instanceof Error ? error.message : "Не удалось загрузить диалог.");
    }
  }

  function showBackendResponse(response: SupportResponse) {
    const shared = { role: "assistant" as const, requestId: response.request_id };
    if (response.status === "answered" || response.status === "blocked") {
      const sources = toSources(response.sources);
      addMsg({ ...shared, text: response.answer || "Ответ не найден.", sources: sources.length ? sources : undefined });
      setChatState("answered");
      announce("Ответ получен");
      return;
    }
    if (response.status === "need_clarification") {
      addMsg({ ...shared, text: response.clarification_question || "Уточните детали обращения.", isClarification: true });
      setChatState("needs_clarification");
      announce("Нужно уточнение");
      return;
    }
    if (response.status === "escalated") {
      addMsg({ ...shared, text: response.support || "Диалог передан специалисту технической поддержки.", isEscalated: true });
      setChatState("escalated");
      announce("Обращение передано специалисту");
      return;
    }
    addMsg({ ...shared, text: response.answer || "Не удалось обработать обращение." });
    setChatState("idle");
  }

  async function submitToBackend(text: string) {
    const continuationId = activeRequestId;
    addMsg({ role: "user", text });
    const processingId = addMsg({ role: "assistant", isProcessing: true, processingLabel: PROC_STAGES[0] });
    setChatState("processing");
    setChatError("");
    try {
      const response = continuationId
        ? await apiPost<SupportResponse>(`/support/requests/${encodeURIComponent(continuationId)}/messages`, { message: text })
        : await apiPost<SupportResponse>("/support/requests", { message: text });
      removeMsg(processingId);
      setSelectedHistory(response.request_id);
      setActiveRequestId(response.request_id);
      showBackendResponse(response);
      void loadHistory();
    } catch (error) {
      removeMsg(processingId);
      setChatState("idle");
      setChatError(error instanceof Error ? error.message : "Не удалось отправить обращение.");
    }
  }

  async function handleClarificationReply(reply: string) {
    await submitToBackend(reply);
  }

  async function handleArbitrary(text: string) {
    await submitToBackend(text);
  }

  async function handleSend() {
    const text = inputText.trim();
    if (!text || chatState === "processing") return;
    setInputText("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    if (chatState === "needs_clarification") {
      void handleClarificationReply(text);
      return;
    }
    void handleArbitrary(text);
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

  async function giveFeedback(id: number, val: "yes" | "no", requestId?: string) {
    setFeedbackGiven(prev => ({ ...prev, [id]: val }));
    if (val === "no") setShowPostFeedback(prev => new Set(prev).add(id));
    if (!requestId) return;
    try {
      await apiPost("/feedback", { support_request_id: requestId, rating: val === "yes" ? 5 : 1, comment: "", resolved: val === "yes" });
    } catch (error) {
      setChatError(error instanceof Error ? error.message : "Не удалось сохранить оценку.");
    }
  }

  const QUICK_Q = [
    "Как создать оферту?",
    "Работа с МЧД",
    "Проблема с электронной подписью",
    "Ошибка при загрузке файла",
  ];

  return (
    <>
      <header className="portal-header">
        <a className="portal-logo" href="#" aria-label="Портал поставщиков">
          <img src={portalLogo} alt="" aria-hidden="true" style={{ width: 32, height: 32, objectFit: 'contain' }} />
          <span className="portal-logo-text">Портал <span>поставщиков</span></span>
        </a>

        <nav className="portal-nav-main" aria-label="Основная навигация">
          <button className={`nav-item${page === "support" ? " active" : ""}`} aria-current={page === "support" ? "page" : undefined} onClick={() => setPage("support")}>Поддержка</button>
          <button className={`nav-item${page === "admin" ? " active" : ""}`} aria-current={page === "admin" ? "page" : undefined} onClick={() => setPage("admin")}>Аналитика</button>
        </nav>

        <div className="portal-header-right">
          <button className="header-icon-btn" aria-label="Уведомления">
            <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
              <path d="M7.5 1a4.5 4.5 0 0 1 4.5 4.5v2l1 2H2l1-2V5.5A4.5 4.5 0 0 1 7.5 1z" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
              <path d="M6 12.5a1.5 1.5 0 0 0 3 0" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
            </svg>
          </button>
        </div>
      </header>

      {page === "admin" && <AdminPanel />}

      {page === "support" && <main className="page-content">
        <div className="page-heading-row">
          <h1 className="page-heading">Поддержка</h1>
          <span className="page-subheading">Задайте вопрос о работе с Порталом</span>
        </div>

        <div className="support-workspace">
          <aside className="history-panel" aria-label="Диалоги">
            <div className="history-panel-header">
              <span className="panel-title">Диалоги</span>
              <button className="btn-new" onClick={startNewDialog} disabled={chatState === "processing"}>
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true">
                  <path d="M5 1v8M1 5h8" stroke="#fff" strokeWidth="1.7" strokeLinecap="round" />
                </svg>
                Новый диалог
              </button>
            </div>
            <div className="history-list" role="list">
              {historyLoading && <div className="history-empty">Загрузка диалогов…</div>}
              {!historyLoading && historyItems.length === 0 && <div className="history-empty">Здесь появятся ваши диалоги</div>}
              {!historyLoading && historyItems.map(item => (
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
                       {QUICK_Q.map(question => (
                         <button key={question} className="quick-btn" onClick={() => void submitToBackend(question)}>
                           {question}
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
                            {msg.text && renderText(msg.text)}
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
                                <button className="feedback-btn yes" onClick={() => void giveFeedback(msg.id, "yes", msg.requestId)}>
                                  <svg width="11" height="11" viewBox="0 0 11 11" fill="none" aria-hidden="true">
                                    <path d="M2 5.5l2.5 2.5 4.5-4.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
                                  </svg>
                                  Да
                                </button>
                                <button className="feedback-btn no" onClick={() => void giveFeedback(msg.id, "no", msg.requestId)}>Нет</button>
                              </>
                            ) : fb === "yes" ? (
                              <span style={{ fontSize: 13, color: "#238636" }}>Спасибо за оценку</span>
                            ) : showPost ? (
                              <div className="post-feedback">
                                <span className="post-feedback-label">Спасибо, учтём замечание</span>
                                <button className="text-btn" onClick={() => textareaRef.current?.focus()}>Уточнить вопрос</button>
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
                {chatError && <div role="alert" style={{ color: "#b42318", padding: "0 16px 8px" }}>{chatError}</div>}
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
