/**
 * HTTP client for the Go support backend (see backend/internal/transport/http/server.go
 * and backend/README.md for the authoritative contract).
 *
 * Base URL comes from VITE_API_BASE_URL (baked in at build time by Vite):
 *   - local dev without Docker: backend/.env.example has PORT=8080          -> http://localhost:8080
 *   - `docker compose up` from repo root: API is published on API_HOST_PORT -> http://localhost:8081 (default)
 * See frontend/.env.example.
 */

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8080").replace(/\/+$/, "");

// Keep the same browser identity as api/client.ts so all support endpoints
// address one persistent anonymous user.
const PORTAL_USER_ID_KEY = "sunshine.anonymous_user_id";

/**
 * The real Portal has no auth gateway wired into this hackathon build, so the
 * backend just trusts an `X-Portal-User-ID` header (see backend/README.md).
 * We mint one per browser and keep it stable so a page reload still owns the
 * same support requests.
 */
export function getPortalUserId(): string {
  try {
    const existing = window.localStorage.getItem(PORTAL_USER_ID_KEY);
    if (existing) return existing;
    const generated = crypto.randomUUID();
    window.localStorage.setItem(PORTAL_USER_ID_KEY, generated);
    return generated;
  } catch {
    // Storage can be unavailable (private mode, etc.) — fall back to a
    // per-session id so the app still works, just without persistence.
    return "user-anonymous";
  }
}

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        "X-Portal-User-ID": getPortalUserId(),
        ...(init?.headers ?? {}),
      },
    });
  } catch (cause) {
    throw new ApiError(0, "NETWORK_ERROR", "Не удалось связаться с сервером поддержки. Проверьте, что backend запущен.");
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const body = text ? JSON.parse(text) : {};

  if (!response.ok) {
    const message = body?.error?.message ?? `Backend вернул ошибку ${response.status}`;
    const code = body?.error?.code ?? "UNKNOWN_ERROR";
    throw new ApiError(response.status, code, message);
  }
  return body as T;
}

// ---- Types mirroring backend/internal/domain and transport/http/server.go ----

export type RequestStatus =
  | "processing"
  | "answered"
  | "need_clarification"
  | "blocked"
  | "escalated"
  | "ai_failed";

export type ApiSource = {
  document: string;
  section?: string;
  page?: number;
  chunk_id: string;
};

export type SupportResponse = {
  status: RequestStatus;
  request_id: string;
  answer?: string;
  clarification_question?: string;
  topic?: string;
  support_level?: string;
  confidence?: number;
  sources: ApiSource[];
  ticket_id?: string;
  support?: string;
  ticket_status?: string;
};

export type ApiSupportRequest = {
  id: string;
  original_message: string;
  status: RequestStatus;
  topic?: string;
  support_level?: string;
  ai_status: string;
  ai_answer?: string;
  confidence?: number;
  sources?: ApiSource[];
  created_at: string;
  updated_at: string;
};

export type ApiMessage = {
  id: string;
  support_request_id: string;
  sender_type: "USER" | "AI" | "OPERATOR" | "SYSTEM";
  text: string;
  created_at: string;
};

export type TicketStatus = "WAITING_FOR_OPERATOR" | "IN_PROGRESS" | "ANSWERED" | "CLOSED";

export type ApiTicket = {
  id: string;
  user_id: string;
  support_request_id: string;
  status: TicketStatus;
  topic?: string;
  support_level?: string;
  original_query: string;
  conversation_context?: string;
  ai_answer?: string;
  ai_confidence?: number;
  ai_sources?: ApiSource[];
  operator_id?: string;
  operator_answer?: string;
  created_at: string;
  updated_at: string;
  taken_at?: string;
  answered_at?: string;
  closed_at?: string;
};

export type AnalyticsSummary = {
  total_requests: number;
  answered_by_ai: number;
  escalated: number;
  escalation_rate: number;
  requests_by_topic: Record<string, number>;
  requests_by_support_level: Record<string, number>;
  tickets_by_status: Record<string, number>;
  average_feedback: number | null;
  unresolved_feedback_count: number;
};

export type AnalyticsConclusion = {
  type: string;
  topic: string;
  message: string;
  value: number;
};

// ---- Support (end-user chat) ----

export function createSupportRequest(message: string): Promise<SupportResponse> {
  return request("/support/requests", { method: "POST", body: JSON.stringify({ message }) });
}

export function listSupportRequests(): Promise<{ requests: ApiSupportRequest[] }> {
  return request("/support/requests");
}

export function addSupportMessage(requestId: string, message: string): Promise<SupportResponse> {
  return request(`/support/requests/${encodeURIComponent(requestId)}/messages`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

export function getSupportRequest(requestId: string): Promise<SupportResponse> {
  return request(`/support/requests/${encodeURIComponent(requestId)}`);
}

export function listSupportMessages(requestId: string): Promise<{ messages: ApiMessage[] }> {
  return request(`/support/requests/${encodeURIComponent(requestId)}/messages`);
}

export function createFeedback(
  supportRequestId: string,
  rating: number,
  comment: string,
  resolved: boolean
): Promise<{ id: string }> {
  return request("/feedback", {
    method: "POST",
    body: JSON.stringify({ support_request_id: supportRequestId, rating, comment, resolved }),
  });
}

// ---- Operator / admin ----

export function listTickets(status?: TicketStatus): Promise<{ tickets: ApiTicket[] }> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return request(`/operator/tickets${query}`);
}

export function getTicket(ticketId: string): Promise<{ ticket: ApiTicket; conversation: ApiMessage[] }> {
  return request(`/operator/tickets/${encodeURIComponent(ticketId)}`);
}

export function takeTicket(ticketId: string): Promise<ApiTicket> {
  return request(`/operator/tickets/${encodeURIComponent(ticketId)}/take`, { method: "POST" });
}

export function answerTicket(ticketId: string, answer: string): Promise<ApiTicket> {
  return request(`/operator/tickets/${encodeURIComponent(ticketId)}/answer`, {
    method: "POST",
    body: JSON.stringify({ answer }),
  });
}

export function closeTicket(ticketId: string): Promise<ApiTicket> {
  return request(`/operator/tickets/${encodeURIComponent(ticketId)}/close`, { method: "POST" });
}

export function getAnalyticsSummary(): Promise<AnalyticsSummary> {
  return request("/analytics/summary");
}

export function getAnalyticsConclusions(): Promise<{ conclusions: AnalyticsConclusion[] }> {
  return request("/analytics/conclusions");
}
