package httptransport

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/TenderHack-sunshine/sunshine/backend/internal/application"
	"github.com/TenderHack-sunshine/sunshine/backend/internal/domain"
)

const maxBodyBytes = 1 << 20
const refreshCookieName = "refresh_token"
const bearerPrefix = "Bearer "

type Server struct {
	support        *application.SupportService
	tickets        *application.TicketService
	feedback       *application.FeedbackService
	analytics      *application.AnalyticsService
	auth           *application.AuthService
	admin          *application.AdminService
	frontendOrigin string
	cookieSecure   bool
	logger         *slog.Logger
}

func NewServer(support *application.SupportService, tickets *application.TicketService, feedback *application.FeedbackService, analytics *application.AnalyticsService, auth *application.AuthService, admin *application.AdminService, frontendOrigin string, cookieSecure bool, logger *slog.Logger) http.Handler {
	server := &Server{support: support, tickets: tickets, feedback: feedback, analytics: analytics, auth: auth, admin: admin, frontendOrigin: frontendOrigin, cookieSecure: cookieSecure, logger: logger}
	mux := http.NewServeMux()
	health := func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	}
	mux.HandleFunc("GET /health", health)
	mux.HandleFunc("GET /healthz", health)

	mux.HandleFunc("POST /auth/register", server.register)
	mux.HandleFunc("POST /auth/register-specialist", server.registerSpecialist)
	mux.HandleFunc("POST /auth/login", server.login)
	mux.HandleFunc("POST /auth/refresh", server.refresh)
	mux.HandleFunc("POST /auth/logout", server.logout)
	mux.HandleFunc("GET /auth/me", server.me)

	mux.HandleFunc("POST /support/requests", server.createRequest)
	mux.HandleFunc("GET /support/requests/{id}", server.getRequest)
	mux.HandleFunc("POST /support/requests/{id}/messages", server.addMessage)
	mux.HandleFunc("GET /support/requests/{id}/messages", server.listMessages)
	mux.HandleFunc("POST /feedback", server.createFeedback)

	mux.HandleFunc("GET /operator/tickets", server.listTickets)
	mux.HandleFunc("GET /operator/tickets/{id}", server.getTicket)
	mux.HandleFunc("POST /operator/tickets/{id}/take", server.takeTicket)
	mux.HandleFunc("POST /operator/tickets/{id}/answer", server.answerTicket)
	mux.HandleFunc("POST /operator/tickets/{id}/close", server.closeTicket)

	mux.HandleFunc("GET /analytics/overview", server.analyticsOverview)
	mux.HandleFunc("GET /analytics/requests", server.analyticsRequests)
	mux.HandleFunc("GET /analytics/summary", server.summary)
	mux.HandleFunc("GET /analytics/topics", server.topics)
	mux.HandleFunc("GET /analytics/feedback", server.feedbackStats)
	mux.HandleFunc("GET /analytics/conclusions", server.conclusions)

	mux.HandleFunc("GET /admin/users", server.adminListUsers)
	mux.HandleFunc("GET /admin/specialists/pending", server.adminPendingSpecialists)
	mux.HandleFunc("POST /admin/specialists/{id}/approve", server.adminApproveSpecialist)
	mux.HandleFunc("POST /admin/specialists/{id}/reject", server.adminRejectSpecialist)
	mux.HandleFunc("POST /admin/users/{id}/role", server.adminSetRole)

	return server.withLogging(server.withCORS(mux))
}

// --- Auth ---

func (s *Server) register(w http.ResponseWriter, r *http.Request) {
	var input struct {
		Email       string `json:"email"`
		Password    string `json:"password"`
		DisplayName string `json:"display_name"`
	}
	if !decode(w, r, &input) {
		return
	}
	result, err := s.auth.Register(r.Context(), input.Email, input.Password, input.DisplayName)
	if err != nil {
		writeServiceError(w, err)
		return
	}
	s.respondWithSession(w, http.StatusCreated, result)
}

func (s *Server) registerSpecialist(w http.ResponseWriter, r *http.Request) {
	var input struct {
		Email       string `json:"email"`
		Password    string `json:"password"`
		DisplayName string `json:"display_name"`
		Line        string `json:"line"`
	}
	if !decode(w, r, &input) {
		return
	}
	user, err := s.auth.RegisterSpecialist(r.Context(), input.Email, input.Password, input.DisplayName, domain.SupportLine(input.Line))
	if err != nil {
		writeServiceError(w, err)
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{
		"user":    user,
		"message": "Заявка отправлена. Доступ откроется после подтверждения администратором.",
	})
}

func (s *Server) login(w http.ResponseWriter, r *http.Request) {
	var input struct {
		Email    string `json:"email"`
		Password string `json:"password"`
	}
	if !decode(w, r, &input) {
		return
	}
	result, err := s.auth.Login(r.Context(), input.Email, input.Password)
	if err != nil {
		writeServiceError(w, err)
		return
	}
	s.respondWithSession(w, http.StatusOK, result)
}

func (s *Server) refresh(w http.ResponseWriter, r *http.Request) {
	cookie, err := r.Cookie(refreshCookieName)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "UNAUTHENTICATED", "Missing refresh token")
		return
	}
	result, err := s.auth.Refresh(r.Context(), cookie.Value)
	if err != nil {
		s.clearRefreshCookie(w)
		writeServiceError(w, err)
		return
	}
	s.respondWithSession(w, http.StatusOK, result)
}

func (s *Server) logout(w http.ResponseWriter, r *http.Request) {
	if cookie, err := r.Cookie(refreshCookieName); err == nil {
		_ = s.auth.Logout(r.Context(), cookie.Value)
	}
	s.clearRefreshCookie(w)
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (s *Server) me(w http.ResponseWriter, r *http.Request) {
	actor, ok := s.authenticate(r, w)
	if !ok {
		return
	}
	user, err := s.auth.Me(r.Context(), actor.UserID)
	if err != nil {
		writeServiceError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, user)
}

func (s *Server) respondWithSession(w http.ResponseWriter, status int, result application.AuthResult) {
	s.setRefreshCookie(w, result.RefreshToken, result.RefreshTTL)
	writeJSON(w, status, map[string]any{"access_token": result.AccessToken, "user": result.User})
}

// --- Support / feedback (any authenticated actor) ---

func (s *Server) createRequest(w http.ResponseWriter, r *http.Request) {
	actor, ok := s.authenticate(r, w)
	if !ok {
		return
	}
	var input struct {
		Message string `json:"message"`
	}
	if !decode(w, r, &input) {
		return
	}
	request, ticket, err := s.support.Create(r.Context(), actor, input.Message)
	if err != nil {
		writeServiceError(w, err)
		return
	}
	s.logger.Info("support request processed", "user_id", actor.UserID, "support_request_id", request.ID, "ai_status", request.AIStatus, "ticket_id", ticketID(ticket))
	writeJSON(w, http.StatusCreated, userResponse(request, ticket))
}

func (s *Server) analyticsRequests(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireStaff(r, w); !ok {
		return
	}

	result, err := s.analytics.Requests(r.Context())
	if err != nil {
		writeServiceError(w, err)
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"requests": result,
	})
}

func (s *Server) getRequest(w http.ResponseWriter, r *http.Request) {
	actor, ok := s.authenticate(r, w)
	if !ok {
		return
	}
	request, err := s.support.Get(r.Context(), actor, r.PathValue("id"))
	if err != nil {
		writeServiceError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, userResponse(request, nil))
}

func (s *Server) addMessage(w http.ResponseWriter, r *http.Request) {
	actor, ok := s.authenticate(r, w)
	if !ok {
		return
	}
	var input struct {
		Message string `json:"message"`
	}
	if !decode(w, r, &input) {
		return
	}
	request, ticket, err := s.support.AddUserMessage(r.Context(), actor, r.PathValue("id"), input.Message)
	if err != nil {
		writeServiceError(w, err)
		return
	}
	s.logger.Info("clarification processed", "user_id", actor.UserID, "support_request_id", request.ID, "ai_status", request.AIStatus, "ticket_id", ticketID(ticket))
	writeJSON(w, http.StatusOK, userResponse(request, ticket))
}

func (s *Server) listMessages(w http.ResponseWriter, r *http.Request) {
	actor, ok := s.authenticate(r, w)
	if !ok {
		return
	}
	messages, err := s.support.ListMessages(r.Context(), actor, r.PathValue("id"))
	if err != nil {
		writeServiceError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"messages": messages})
}

func (s *Server) createFeedback(w http.ResponseWriter, r *http.Request) {
	actor, ok := s.authenticate(r, w)
	if !ok {
		return
	}
	var input struct {
		SupportRequestID string `json:"support_request_id"`
		Rating           int    `json:"rating"`
		Comment          string `json:"comment"`
		Resolved         bool   `json:"resolved"`
	}
	if !decode(w, r, &input) {
		return
	}
	feedback, err := s.feedback.Create(r.Context(), actor, input.SupportRequestID, input.Rating, input.Comment, input.Resolved)
	if err != nil {
		writeServiceError(w, err)
		return
	}
	writeJSON(w, http.StatusCreated, feedback)
}

func (s *Server) analyticsOverview(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireStaff(r, w); !ok {
		return
	}

	result, err := s.analytics.OperationalOverview(r.Context())
	if err != nil {
		writeServiceError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

// --- Operator / tech-specialist ticket queue ---

func (s *Server) listTickets(w http.ResponseWriter, r *http.Request) {
	actor, ok := s.requireStaff(r, w)
	if !ok {
		return
	}
	var status *domain.TicketStatus
	if value := r.URL.Query().Get("status"); value != "" {
		parsed := domain.TicketStatus(value)
		switch parsed {
		case domain.TicketStatusWaitingForOperator, domain.TicketStatusInProgress, domain.TicketStatusAnswered, domain.TicketStatusClosed:
			status = &parsed
		default:
			writeError(w, http.StatusBadRequest, "INVALID_STATUS", "Unknown ticket status")
			return
		}
	}
	tickets, err := s.tickets.List(r.Context(), actor, status)
	if err != nil {
		writeServiceError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"tickets": tickets})
}

func (s *Server) getTicket(w http.ResponseWriter, r *http.Request) {
	actor, ok := s.requireStaff(r, w)
	if !ok {
		return
	}
	ticket, messages, err := s.tickets.GetDetail(r.Context(), actor, r.PathValue("id"))
	if err != nil {
		writeServiceError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ticket": ticket, "conversation": messages})
}

func (s *Server) takeTicket(w http.ResponseWriter, r *http.Request) {
	actor, ok := s.requireStaff(r, w)
	if !ok {
		return
	}
	ticket, err := s.tickets.Take(r.Context(), actor, r.PathValue("id"))
	if err != nil {
		writeServiceError(w, err)
		return
	}
	s.logger.Info("operator took ticket", "user_id", actor.UserID, "ticket_id", ticket.ID, "ticket_status", ticket.Status)
	writeJSON(w, http.StatusOK, ticket)
}

func (s *Server) answerTicket(w http.ResponseWriter, r *http.Request) {
	actor, ok := s.requireStaff(r, w)
	if !ok {
		return
	}
	var input struct {
		Answer string `json:"answer"`
	}
	if !decode(w, r, &input) {
		return
	}
	ticket, err := s.tickets.Answer(r.Context(), actor, r.PathValue("id"), input.Answer)
	if err != nil {
		writeServiceError(w, err)
		return
	}
	s.logger.Info("operator answered ticket", "user_id", actor.UserID, "ticket_id", ticket.ID, "ticket_status", ticket.Status)
	writeJSON(w, http.StatusOK, ticket)
}

func (s *Server) closeTicket(w http.ResponseWriter, r *http.Request) {
	actor, ok := s.requireStaff(r, w)
	if !ok {
		return
	}
	ticket, err := s.tickets.Close(r.Context(), actor, r.PathValue("id"))
	if err != nil {
		writeServiceError(w, err)
		return
	}
	s.logger.Info("operator closed ticket", "user_id", actor.UserID, "ticket_id", ticket.ID, "ticket_status", ticket.Status)
	writeJSON(w, http.StatusOK, ticket)
}

// --- Analytics (staff dashboard) ---

func (s *Server) summary(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireStaff(r, w); !ok {
		return
	}
	result, err := s.analytics.Summary(r.Context())
	if err != nil {
		writeServiceError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}
func (s *Server) topics(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireStaff(r, w); !ok {
		return
	}
	result, err := s.analytics.Snapshot(r.Context())
	if err != nil {
		writeServiceError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"requests_by_topic": result.RequestsByTopic, "requests_by_support_level": result.RequestsByLevel})
}
func (s *Server) feedbackStats(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireStaff(r, w); !ok {
		return
	}
	result, err := s.analytics.Snapshot(r.Context())
	if err != nil {
		writeServiceError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"average_feedback": result.AverageFeedback, "unresolved_feedback_count": result.UnresolvedFeedback})
}
func (s *Server) conclusions(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireStaff(r, w); !ok {
		return
	}
	result, err := s.analytics.Conclusions(r.Context())
	if err != nil {
		writeServiceError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"conclusions": result})
}

// --- Admin: specialist approval queue + direct role grants ---

func (s *Server) adminListUsers(w http.ResponseWriter, r *http.Request) {
	actor, ok := s.authenticate(r, w)
	if !ok {
		return
	}
	users, err := s.admin.ListUsers(r.Context(), actor)
	if err != nil {
		writeServiceError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"users": users})
}

func (s *Server) adminPendingSpecialists(w http.ResponseWriter, r *http.Request) {
	actor, ok := s.authenticate(r, w)
	if !ok {
		return
	}
	users, err := s.admin.ListPendingSpecialists(r.Context(), actor)
	if err != nil {
		writeServiceError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"specialists": users})
}

func (s *Server) adminApproveSpecialist(w http.ResponseWriter, r *http.Request) {
	actor, ok := s.authenticate(r, w)
	if !ok {
		return
	}
	if err := s.admin.ApproveSpecialist(r.Context(), actor, r.PathValue("id")); err != nil {
		writeServiceError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "approved"})
}

func (s *Server) adminRejectSpecialist(w http.ResponseWriter, r *http.Request) {
	actor, ok := s.authenticate(r, w)
	if !ok {
		return
	}
	if err := s.admin.RejectSpecialist(r.Context(), actor, r.PathValue("id")); err != nil {
		writeServiceError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "rejected"})
}

func (s *Server) adminSetRole(w http.ResponseWriter, r *http.Request) {
	actor, ok := s.authenticate(r, w)
	if !ok {
		return
	}
	var input struct {
		Role string `json:"role"`
		Line string `json:"line"`
	}
	if !decode(w, r, &input) {
		return
	}
	if err := s.admin.SetRole(r.Context(), actor, r.PathValue("id"), domain.Role(input.Role), domain.SupportLine(input.Line)); err != nil {
		writeServiceError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "updated"})
}

// --- Shared response helpers (unchanged from the pre-auth version) ---

type supportResponse struct {
	Status                domain.RequestStatus `json:"status"`
	RequestID             string               `json:"request_id"`
	Answer                string               `json:"answer,omitempty"`
	ClarificationQuestion string               `json:"clarification_question,omitempty"`
	Topic                 string               `json:"topic,omitempty"`
	SupportLevel          string               `json:"support_level,omitempty"`
	Confidence            *float64             `json:"confidence,omitempty"`
	Sources               []domain.Source      `json:"sources"`
	TicketID              string               `json:"ticket_id,omitempty"`
	Support               string               `json:"support,omitempty"`
	TicketStatus          string               `json:"ticket_status,omitempty"`
}

func userResponse(request domain.SupportRequest, ticket *domain.Ticket) supportResponse {
	response := supportResponse{Status: request.Status, RequestID: request.ID, Topic: request.Topic, SupportLevel: request.SupportLevel, Confidence: request.Confidence, Sources: request.Sources}
	switch request.Status {
	case domain.RequestStatusAnswered:
		response.Answer = request.AIAnswer
	case domain.RequestStatusNeedClarification:
		response.ClarificationQuestion = request.AIAnswer
	case domain.RequestStatusBlocked:
		response.Answer = request.AIAnswer
	case domain.RequestStatusEscalated:
		if ticket != nil {
			response.TicketID = ticket.ID
		}
		response.Support = "Техническая поддержка"
		response.TicketStatus = "Ожидает специалиста"
	}
	return response
}

// authenticate verifies the Authorization: Bearer <access token> header and
// resolves it to an Actor. This replaces the old X-Portal-User-ID dev header
// entirely: every request now carries a signed, expiring token instead of a
// caller-supplied identity.
func (s *Server) authenticate(r *http.Request, w http.ResponseWriter) (application.Actor, bool) {
	header := r.Header.Get("Authorization")
	if !strings.HasPrefix(header, bearerPrefix) {
		writeError(w, http.StatusUnauthorized, "UNAUTHENTICATED", "Missing or malformed Authorization header")
		return application.Actor{}, false
	}
	token := strings.TrimSpace(strings.TrimPrefix(header, bearerPrefix))
	if token == "" {
		writeError(w, http.StatusUnauthorized, "UNAUTHENTICATED", "Missing or malformed Authorization header")
		return application.Actor{}, false
	}
	actor, err := s.auth.ParseAccessToken(token)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "UNAUTHENTICATED", "Invalid or expired token")
		return application.Actor{}, false
	}
	return actor, true
}

// requireStaff authenticates and additionally rejects a plain "user" actor.
// Used for the operator ticket queue and the analytics dashboard, both of
// which are staff-only surfaces.
func (s *Server) requireStaff(r *http.Request, w http.ResponseWriter) (application.Actor, bool) {
	actor, ok := s.authenticate(r, w)
	if !ok {
		return application.Actor{}, false
	}
	if !actor.IsStaff() {
		writeError(w, http.StatusForbidden, "FORBIDDEN", "Access denied")
		return application.Actor{}, false
	}
	return actor, true
}

func (s *Server) setRefreshCookie(w http.ResponseWriter, token string, ttl time.Duration) {
	http.SetCookie(w, &http.Cookie{
		Name:     refreshCookieName,
		Value:    token,
		Path:     "/auth",
		Expires:  time.Now().Add(ttl),
		HttpOnly: true,
		Secure:   s.cookieSecure,
		SameSite: http.SameSiteLaxMode,
	})
}

func (s *Server) clearRefreshCookie(w http.ResponseWriter) {
	http.SetCookie(w, &http.Cookie{
		Name:     refreshCookieName,
		Value:    "",
		Path:     "/auth",
		Expires:  time.Unix(0, 0),
		MaxAge:   -1,
		HttpOnly: true,
		Secure:   s.cookieSecure,
		SameSite: http.SameSiteLaxMode,
	})
}

func decode(w http.ResponseWriter, r *http.Request, target any) bool {
	r.Body = http.MaxBytesReader(w, r.Body, maxBodyBytes)
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_REQUEST", "Invalid JSON body")
		return false
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		writeError(w, http.StatusBadRequest, "INVALID_REQUEST", "Request body must contain one JSON object")
		return false
	}
	return true
}

func writeServiceError(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, application.ErrInvalidInput):
		writeError(w, http.StatusBadRequest, "INVALID_REQUEST", "Invalid request")
	case errors.Is(err, application.ErrNotFound):
		writeError(w, http.StatusNotFound, "NOT_FOUND", "Resource not found")
	case errors.Is(err, application.ErrForbidden):
		writeError(w, http.StatusForbidden, "FORBIDDEN", "Access denied")
	case errors.Is(err, application.ErrInvalidState):
		writeError(w, http.StatusConflict, "INVALID_STATE", "Operation is not allowed in the current state")
	case errors.Is(err, application.ErrDuplicateFeedback):
		writeError(w, http.StatusConflict, "FEEDBACK_EXISTS", "Feedback already exists")
	case errors.Is(err, application.ErrRAGUnavailable):
		writeError(w, http.StatusServiceUnavailable, "RAG_UNAVAILABLE", "Сервис обработки обращения временно недоступен")
	case errors.Is(err, application.ErrInvalidRAGResult):
		writeError(w, http.StatusBadGateway, "RAG_INVALID_RESPONSE", "Сервис обработки обращения вернул некорректный ответ")
	case errors.Is(err, application.ErrEmailTaken):
		writeError(w, http.StatusConflict, "EMAIL_TAKEN", "Этот email уже зарегистрирован")
	case errors.Is(err, application.ErrInvalidCredentials):
		writeError(w, http.StatusUnauthorized, "INVALID_CREDENTIALS", "Неверный email или пароль")
	case errors.Is(err, application.ErrPendingApproval):
		writeError(w, http.StatusForbidden, "PENDING_APPROVAL", "Заявка ожидает подтверждения администратором")
	case errors.Is(err, application.ErrRegistrationRejected):
		writeError(w, http.StatusForbidden, "REGISTRATION_REJECTED", "Заявка была отклонена администратором")
	default:
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "Internal server error")
	}
}
func writeError(w http.ResponseWriter, status int, code, message string) {
	writeJSON(w, status, map[string]any{"error": map[string]string{"code": code, "message": message}})
}
func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

type statusWriter struct {
	http.ResponseWriter
	status int
}

func (w *statusWriter) WriteHeader(status int) {
	w.status = status
	w.ResponseWriter.WriteHeader(status)
}
func (s *Server) withLogging(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestID := r.Header.Get("X-Request-ID")
		if requestID == "" {
			requestID = newRequestID()
		}
		w.Header().Set("X-Request-ID", requestID)
		started := time.Now()
		wrapped := &statusWriter{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(wrapped, r.WithContext(context.WithValue(r.Context(), requestIDKey{}, requestID)))
		s.logger.Info("http request", "request_id", requestID, "method", r.Method, "path", r.URL.Path, "status", wrapped.status, "duration_ms", time.Since(started).Milliseconds())
	})
}

// withCORS allows the configured single-page-app origin to call the API
// with credentials (the refresh-token cookie), which requires echoing back
// one concrete origin rather than "*". If FRONTEND_ORIGIN is unset it falls
// back to reflecting the request's own Origin header, which keeps local
// development (arbitrary ports) working without extra configuration.
func (s *Server) withCORS(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		origin := r.Header.Get("Origin")
		allowed := s.frontendOrigin
		if allowed == "" {
			allowed = origin
		}
		if allowed != "" {
			w.Header().Set("Access-Control-Allow-Origin", allowed)
			w.Header().Set("Vary", "Origin")
		}
		w.Header().Set("Access-Control-Allow-Credentials", "true")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Request-ID")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

type requestIDKey struct{}

func newRequestID() string {
	bytes := make([]byte, 8)
	if _, err := rand.Read(bytes); err != nil {
		return "unknown"
	}
	return hex.EncodeToString(bytes)
}

func ticketID(ticket *domain.Ticket) string {
	if ticket == nil {
		return ""
	}
	return ticket.ID
}
