package adapter

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"github.com/TenderHack-sunshine/sunshine/backend/internal/application"
	"github.com/TenderHack-sunshine/sunshine/backend/internal/domain"
	"github.com/TenderHack-sunshine/sunshine/backend/internal/port"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

type PostgresStore struct{ pool *pgxpool.Pool }

func NewPostgresStore(pool *pgxpool.Pool) *PostgresStore { return &PostgresStore{pool: pool} }

func (s *PostgresStore) CreateSupportRequest(ctx context.Context, request domain.SupportRequest, initial domain.Message) error {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	if _, err = tx.Exec(ctx, `INSERT INTO users (id) VALUES ($1) ON CONFLICT (id) DO NOTHING`, request.UserID); err != nil {
		return err
	}
	if _, err = tx.Exec(ctx, `INSERT INTO support_requests (id,user_id,original_message,status,ai_status,dialog_state,created_at,updated_at) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)`, request.ID, request.UserID, request.OriginalMessage, request.Status, request.AIStatus, dialogState(request.DialogState), request.CreatedAt, request.UpdatedAt); err != nil {
		return err
	}
	if _, err = tx.Exec(ctx, `INSERT INTO messages (id,support_request_id,sender_type,text,created_at) VALUES ($1,$2,$3,$4,$5)`, initial.ID, initial.RequestID, initial.Sender, initial.Text, initial.CreatedAt); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

func (s *PostgresStore) GetSupportRequest(ctx context.Context, requestID string) (domain.SupportRequest, error) {
	return scanRequest(s.pool.QueryRow(ctx, `SELECT id,user_id,original_message,status,topic,support_level,ai_status,ai_answer,confidence,ai_sources,dialog_state,created_at,updated_at FROM support_requests WHERE id=$1`, requestID))
}

func (s *PostgresStore) AddMessage(ctx context.Context, message domain.Message) error {
	_, err := s.pool.Exec(ctx, `INSERT INTO messages (id,support_request_id,sender_type,text,created_at) VALUES ($1,$2,$3,$4,$5)`, message.ID, message.RequestID, message.Sender, message.Text, message.CreatedAt)
	return err
}

func (s *PostgresStore) RefreshTicketContext(ctx context.Context, requestID string) error {
	_, err := s.pool.Exec(ctx, `
		UPDATE tickets
		SET conversation_context = COALESCE((
			SELECT string_agg(sender_type || ': ' || text, chr(10) ORDER BY created_at, id)
			FROM messages
			WHERE support_request_id=$1
		), ''), updated_at=NOW()
		WHERE support_request_id=$1
	`, requestID)
	return err
}

func (s *PostgresStore) ListSupportRequests(ctx context.Context) ([]domain.SupportRequest, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT
			id,
			user_id,
			original_message,
			status,
			topic,
			support_level,
			ai_status,
			ai_answer,
			confidence,
			ai_sources,
			dialog_state,
			created_at,
			updated_at
		FROM support_requests
		ORDER BY created_at DESC
	`)
	if err != nil {
		return nil, err
	}

	defer rows.Close()

	items := make([]domain.SupportRequest, 0)

	for rows.Next() {
		request, err := scanRequest(rows)
		if err != nil {
			return nil, err
		}

		items = append(items, request)
	}

	return items, rows.Err()
}

func (s *PostgresStore) ListSupportRequestsByUser(ctx context.Context, userID string) ([]domain.SupportRequest, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT
			id,
			user_id,
			original_message,
			status,
			topic,
			support_level,
			ai_status,
			ai_answer,
			confidence,
			ai_sources,
			dialog_state,
			created_at,
			updated_at
		FROM support_requests
		WHERE user_id=$1
		ORDER BY created_at DESC
	`, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	items := make([]domain.SupportRequest, 0)
	for rows.Next() {
		request, err := scanRequest(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, request)
	}
	return items, rows.Err()
}

func (s *PostgresStore) ListMessages(ctx context.Context, requestID string) ([]domain.Message, error) {
	rows, err := s.pool.Query(ctx, `SELECT id,support_request_id,sender_type,text,created_at FROM messages WHERE support_request_id=$1 ORDER BY created_at,id`, requestID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	messages := make([]domain.Message, 0)
	for rows.Next() {
		var message domain.Message
		if err := rows.Scan(&message.ID, &message.RequestID, &message.Sender, &message.Text, &message.CreatedAt); err != nil {
			return nil, err
		}
		messages = append(messages, message)
	}
	return messages, rows.Err()
}

func (s *PostgresStore) ApplyRAGResult(ctx context.Context, requestID string, result port.ProcessResponse, aiMessage *domain.Message, ticket *domain.Ticket) error {
	status, answer := requestStatus(result)
	sources, err := json.Marshal(result.Sources)
	if err != nil {
		return err
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	command, err := tx.Exec(ctx, `UPDATE support_requests SET status=$2,topic=$3,support_level=$4,ai_status=$5,ai_answer=$6,confidence=$7,ai_sources=$8,dialog_state=$9,updated_at=NOW() WHERE id=$1`, requestID, status, result.Topic, result.SupportLevel, result.Status, answer, result.Confidence, sources, dialogState(result.DialogState))
	if err != nil {
		return err
	}
	if command.RowsAffected() == 0 {
		return application.ErrNotFound
	}
	if aiMessage != nil {
		if _, err := tx.Exec(ctx, `INSERT INTO messages (id,support_request_id,sender_type,text,created_at) VALUES ($1,$2,$3,$4,$5)`, aiMessage.ID, aiMessage.RequestID, aiMessage.Sender, aiMessage.Text, aiMessage.CreatedAt); err != nil {
			return err
		}
	}
	if ticket != nil {
		ticketSources, err := json.Marshal(ticket.AISources)
		if err != nil {
			return err
		}
		if _, err := tx.Exec(ctx, `INSERT INTO tickets (id,user_id,support_request_id,status,topic,subtopic,matched_taxonomy_id,support_level,original_query,conversation_context,ai_answer,ai_confidence,ai_sources,resolved_query,intent_frame,routing_reason,escalation_reason,created_at,updated_at) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)`, ticket.ID, ticket.UserID, ticket.SupportRequestID, ticket.Status, ticket.Topic, ticket.Subtopic, ticket.MatchedTaxonomyID, ticket.SupportLevel, ticket.OriginalQuery, ticket.ConversationContext, ticket.AIAnswer, ticket.AIConfidence, ticketSources, ticket.ResolvedQuery, dialogState(ticket.IntentFrame), ticket.RoutingReason, ticket.EscalationReason, ticket.CreatedAt, ticket.UpdatedAt); err != nil {
			return err
		}
	}
	return tx.Commit(ctx)
}

func (s *PostgresStore) MarkRAGFailed(ctx context.Context, requestID string) error {
	command, err := s.pool.Exec(ctx, `UPDATE support_requests SET status=$2,ai_status=$3,updated_at=NOW() WHERE id=$1`, requestID, domain.RequestStatusAIFailed, domain.AIStatusFailed)
	if err != nil {
		return err
	}
	if command.RowsAffected() == 0 {
		return application.ErrNotFound
	}
	return nil
}

func (s *PostgresStore) ListTickets(ctx context.Context, status *domain.TicketStatus, line *domain.SupportLine) ([]domain.Ticket, error) {
	query := `SELECT id,user_id,support_request_id,status,topic,subtopic,matched_taxonomy_id,support_level,original_query,conversation_context,ai_answer,ai_confidence,ai_sources,resolved_query,intent_frame,routing_reason,escalation_reason,operator_id,operator_answer,created_at,updated_at,taken_at,answered_at,closed_at FROM tickets`
	conditions := []string{}
	args := []any{}
	if status != nil {
		args = append(args, *status)
		conditions = append(conditions, fmt.Sprintf("status=$%d", len(args)))
	}
	if line != nil {
		args = append(args, string(*line))
		conditions = append(conditions, fmt.Sprintf("support_level=$%d", len(args)))
	}
	if len(conditions) > 0 {
		query += " WHERE " + strings.Join(conditions, " AND ")
	}
	query += ` ORDER BY created_at DESC`
	rows, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]domain.Ticket, 0)
	for rows.Next() {
		ticket, err := scanTicket(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, ticket)
	}
	return items, rows.Err()
}

func (s *PostgresStore) GetTicket(ctx context.Context, ticketID string) (domain.Ticket, error) {
	return scanTicket(s.pool.QueryRow(ctx, `SELECT id,user_id,support_request_id,status,topic,subtopic,matched_taxonomy_id,support_level,original_query,conversation_context,ai_answer,ai_confidence,ai_sources,resolved_query,intent_frame,routing_reason,escalation_reason,operator_id,operator_answer,created_at,updated_at,taken_at,answered_at,closed_at FROM tickets WHERE id=$1`, ticketID))
}

func (s *PostgresStore) TakeTicket(ctx context.Context, ticketID, operatorID string) (domain.Ticket, error) {
	return s.updateTicket(ctx, ticketID, `UPDATE tickets SET status=$2,operator_id=$3,taken_at=NOW(),updated_at=NOW() WHERE id=$1 AND status=$4 RETURNING id,user_id,support_request_id,status,topic,subtopic,matched_taxonomy_id,support_level,original_query,conversation_context,ai_answer,ai_confidence,ai_sources,resolved_query,intent_frame,routing_reason,escalation_reason,operator_id,operator_answer,created_at,updated_at,taken_at,answered_at,closed_at`, domain.TicketStatusInProgress, operatorID, domain.TicketStatusWaitingForOperator)
}

func (s *PostgresStore) AnswerTicket(ctx context.Context, ticketID, operatorID, answer string, message domain.Message) (domain.Ticket, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.Ticket{}, err
	}
	defer tx.Rollback(ctx)
	ticket, err := scanTicket(tx.QueryRow(ctx, `UPDATE tickets SET status=$2,operator_answer=$3,answered_at=NOW(),updated_at=NOW() WHERE id=$1 AND status=$4 AND operator_id=$5 RETURNING id,user_id,support_request_id,status,topic,subtopic,matched_taxonomy_id,support_level,original_query,conversation_context,ai_answer,ai_confidence,ai_sources,resolved_query,intent_frame,routing_reason,escalation_reason,operator_id,operator_answer,created_at,updated_at,taken_at,answered_at,closed_at`, ticketID, domain.TicketStatusAnswered, answer, domain.TicketStatusInProgress, operatorID))
	if err != nil {
		return domain.Ticket{}, s.ticketMutationError(ctx, ticketID, err)
	}
	message.RequestID = ticket.SupportRequestID
	if _, err := tx.Exec(ctx, `INSERT INTO messages (id,support_request_id,sender_type,text,created_at) VALUES ($1,$2,$3,$4,$5)`, message.ID, message.RequestID, message.Sender, message.Text, message.CreatedAt); err != nil {
		return domain.Ticket{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return domain.Ticket{}, err
	}
	return ticket, nil
}

func (s *PostgresStore) CloseTicket(ctx context.Context, ticketID, operatorID string) (domain.Ticket, error) {
	return s.updateTicket(ctx, ticketID, `UPDATE tickets SET status=$2,closed_at=NOW(),updated_at=NOW() WHERE id=$1 AND status=$3 AND operator_id=$4 RETURNING id,user_id,support_request_id,status,topic,subtopic,matched_taxonomy_id,support_level,original_query,conversation_context,ai_answer,ai_confidence,ai_sources,resolved_query,intent_frame,routing_reason,escalation_reason,operator_id,operator_answer,created_at,updated_at,taken_at,answered_at,closed_at`, domain.TicketStatusClosed, domain.TicketStatusAnswered, operatorID)
}

func (s *PostgresStore) updateTicket(ctx context.Context, ticketID, query string, args ...any) (domain.Ticket, error) {
	args = append([]any{ticketID}, args...)
	ticket, err := scanTicket(s.pool.QueryRow(ctx, query, args...))
	if err != nil {
		return domain.Ticket{}, s.ticketMutationError(ctx, ticketID, err)
	}
	return ticket, nil
}

func (s *PostgresStore) CreateFeedback(ctx context.Context, feedback domain.Feedback) error {
	_, err := s.pool.Exec(ctx, `INSERT INTO feedback (id,user_id,support_request_id,ticket_id,rating,comment,resolved,created_at) VALUES ($1,$2,$3,(SELECT id FROM tickets WHERE support_request_id=$3),$4,$5,$6,$7)`, feedback.ID, feedback.UserID, feedback.SupportRequestID, feedback.Rating, feedback.Comment, feedback.Resolved, feedback.CreatedAt)
	var pgErr *pgconn.PgError
	if errors.As(err, &pgErr) && pgErr.Code == "23505" {
		return application.ErrDuplicateFeedback
	}
	return err
}

func (s *PostgresStore) OperationalAnalytics(ctx context.Context) (port.OperationalAnalyticsSnapshot, error) {
	var result port.OperationalAnalyticsSnapshot

	err := s.pool.QueryRow(ctx, `
		SELECT
			COUNT(*),
			COUNT(*) FILTER (WHERE status = 'answered'),
			COUNT(*) FILTER (WHERE status = 'escalated'),
			COUNT(*) FILTER (WHERE status = 'need_clarification'),
			COUNT(*) FILTER (WHERE status = 'processing')
		FROM support_requests
		WHERE created_at::date = CURRENT_DATE
	`).Scan(
		&result.Total,
		&result.AnsweredByAI,
		&result.Escalated,
		&result.NeedClarification,
		&result.InProgress,
	)

	return result, err
}

func (s *PostgresStore) Analytics(ctx context.Context) (port.AnalyticsSnapshot, error) {
	result := port.AnalyticsSnapshot{RequestsByTopic: map[string]int64{}, RequestsByLevel: map[string]int64{}, TicketsByStatus: map[string]int64{}, EscalationsByTopic: map[string]int64{}, NegativeByTopic: map[string]int64{}, FeedbackCountByTopic: map[string]int64{}}
	if err := s.pool.QueryRow(ctx, `SELECT COUNT(*),COUNT(*) FILTER (WHERE status='answered'),COUNT(*) FILTER (WHERE status='escalated') FROM support_requests`).Scan(&result.TotalRequests, &result.AnsweredByAI, &result.Escalated); err != nil {
		return result, err
	}
	if err := scanCounts(ctx, s.pool, `SELECT COALESCE(NULLIF(topic,''),'unknown'),COUNT(*) FROM support_requests GROUP BY 1`, result.RequestsByTopic); err != nil {
		return result, err
	}
	if err := scanCounts(ctx, s.pool, `SELECT COALESCE(NULLIF(support_level,''),'unknown'),COUNT(*) FROM support_requests GROUP BY 1`, result.RequestsByLevel); err != nil {
		return result, err
	}
	if err := scanCounts(ctx, s.pool, `SELECT status,COUNT(*) FROM tickets GROUP BY 1`, result.TicketsByStatus); err != nil {
		return result, err
	}
	if err := scanCounts(ctx, s.pool, `SELECT COALESCE(NULLIF(topic,''),'unknown'),COUNT(*) FROM support_requests WHERE status='escalated' GROUP BY 1`, result.EscalationsByTopic); err != nil {
		return result, err
	}
	if err := s.pool.QueryRow(ctx, `SELECT AVG(rating),COUNT(*) FILTER (WHERE NOT resolved) FROM feedback`).Scan(&result.AverageFeedback, &result.UnresolvedFeedback); err != nil {
		return result, err
	}
	if err := scanCounts(ctx, s.pool, `SELECT COALESCE(NULLIF(sr.topic,''),'unknown'),COUNT(*) FROM feedback f JOIN support_requests sr ON sr.id=f.support_request_id WHERE f.rating<=2 GROUP BY 1`, result.NegativeByTopic); err != nil {
		return result, err
	}
	if err := scanCounts(ctx, s.pool, `SELECT COALESCE(NULLIF(sr.topic,''),'unknown'),COUNT(*) FROM feedback f JOIN support_requests sr ON sr.id=f.support_request_id GROUP BY 1`, result.FeedbackCountByTopic); err != nil {
		return result, err
	}
	return result, nil
}

func (s *PostgresStore) CreateUser(ctx context.Context, user domain.User) error {
	_, err := s.pool.Exec(ctx, `INSERT INTO users (id,email,password_hash,display_name,role,line,specialist_status,created_at,updated_at) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)`,
		user.ID, user.Email, user.PasswordHash, user.DisplayName, user.Role, user.Line, user.SpecialistStatus, user.CreatedAt, user.UpdatedAt)
	var pgErr *pgconn.PgError
	if errors.As(err, &pgErr) && pgErr.Code == "23505" {
		return application.ErrEmailTaken
	}
	return err
}

func (s *PostgresStore) GetUserByEmail(ctx context.Context, email string) (domain.User, error) {
	return scanUser(s.pool.QueryRow(ctx, `SELECT id,email,password_hash,display_name,role,line,specialist_status,created_at,updated_at FROM users WHERE email=$1`, email))
}

func (s *PostgresStore) GetUserByID(ctx context.Context, id string) (domain.User, error) {
	return scanUser(s.pool.QueryRow(ctx, `SELECT id,email,password_hash,display_name,role,line,specialist_status,created_at,updated_at FROM users WHERE id=$1`, id))
}

func (s *PostgresStore) ListUsers(ctx context.Context) ([]domain.User, error) {
	rows, err := s.pool.Query(ctx, `SELECT id,email,password_hash,display_name,role,line,specialist_status,created_at,updated_at FROM users WHERE email<>'' ORDER BY created_at DESC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	users := make([]domain.User, 0)
	for rows.Next() {
		user, err := scanUser(rows)
		if err != nil {
			return nil, err
		}
		user.PasswordHash = ""
		users = append(users, user)
	}
	return users, rows.Err()
}

func (s *PostgresStore) ListSpecialistsByStatus(ctx context.Context, status domain.SpecialistStatus) ([]domain.User, error) {
	rows, err := s.pool.Query(ctx, `SELECT id,email,password_hash,display_name,role,line,specialist_status,created_at,updated_at FROM users WHERE role='tech_specialist' AND specialist_status=$1 ORDER BY created_at`, status)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	users := make([]domain.User, 0)
	for rows.Next() {
		user, err := scanUser(rows)
		if err != nil {
			return nil, err
		}
		user.PasswordHash = ""
		users = append(users, user)
	}
	return users, rows.Err()
}

func (s *PostgresStore) UpdateUserRole(ctx context.Context, userID string, role domain.Role, line domain.SupportLine, status domain.SpecialistStatus) error {
	command, err := s.pool.Exec(ctx, `UPDATE users SET role=$2,line=$3,specialist_status=$4,updated_at=NOW() WHERE id=$1`, userID, role, line, status)
	if err != nil {
		return err
	}
	if command.RowsAffected() == 0 {
		return application.ErrNotFound
	}
	return nil
}

func (s *PostgresStore) UpdateSpecialistStatus(ctx context.Context, userID string, status domain.SpecialistStatus) error {
	command, err := s.pool.Exec(ctx, `UPDATE users SET specialist_status=$2,updated_at=NOW() WHERE id=$1`, userID, status)
	if err != nil {
		return err
	}
	if command.RowsAffected() == 0 {
		return application.ErrNotFound
	}
	return nil
}

func (s *PostgresStore) CreateRefreshToken(ctx context.Context, token domain.RefreshToken) error {
	_, err := s.pool.Exec(ctx, `INSERT INTO refresh_tokens (id,user_id,token_hash,expires_at,created_at) VALUES ($1,$2,$3,$4,$5)`, token.ID, token.UserID, token.TokenHash, token.ExpiresAt, token.CreatedAt)
	return err
}

func (s *PostgresStore) GetRefreshToken(ctx context.Context, tokenHash string) (domain.RefreshToken, error) {
	var t domain.RefreshToken
	err := s.pool.QueryRow(ctx, `SELECT id,user_id,token_hash,expires_at,revoked_at,created_at FROM refresh_tokens WHERE token_hash=$1`, tokenHash).
		Scan(&t.ID, &t.UserID, &t.TokenHash, &t.ExpiresAt, &t.RevokedAt, &t.CreatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return t, application.ErrNotFound
	}
	return t, err
}

func (s *PostgresStore) RevokeRefreshToken(ctx context.Context, tokenHash string) error {
	_, err := s.pool.Exec(ctx, `UPDATE refresh_tokens SET revoked_at=NOW() WHERE token_hash=$1 AND revoked_at IS NULL`, tokenHash)
	return err
}

func (s *PostgresStore) RevokeUserRefreshTokens(ctx context.Context, userID string) error {
	_, err := s.pool.Exec(ctx, `UPDATE refresh_tokens SET revoked_at=NOW() WHERE user_id=$1 AND revoked_at IS NULL`, userID)
	return err
}

func scanUser(row pgx.Row) (domain.User, error) {
	var u domain.User
	err := row.Scan(&u.ID, &u.Email, &u.PasswordHash, &u.DisplayName, &u.Role, &u.Line, &u.SpecialistStatus, &u.CreatedAt, &u.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return u, application.ErrNotFound
	}
	return u, err
}

func requestStatus(result port.ProcessResponse) (domain.RequestStatus, string) {
	switch result.Status {
	case domain.AIStatusAnswered:
		return domain.RequestStatusAnswered, result.Answer
	case domain.AIStatusNeedClarification:
		return domain.RequestStatusNeedClarification, result.ClarificationQuestion
	case domain.AIStatusBlocked:
		return domain.RequestStatusBlocked, result.BlockedReason
	case domain.AIStatusOfferHandoff:
		return domain.RequestStatusOfferHandoff, result.Answer
	case domain.AIStatusEscalateConfirmed:
		return domain.RequestStatusEscalated, result.Answer
	case domain.AIStatusEscalated:
		return domain.RequestStatusEscalated, result.Answer
	default:
		return domain.RequestStatusAIFailed, ""
	}
}
func scanCounts(ctx context.Context, pool *pgxpool.Pool, query string, target map[string]int64) error {
	rows, err := pool.Query(ctx, query)
	if err != nil {
		return err
	}
	defer rows.Close()
	for rows.Next() {
		var key string
		var value int64
		if err := rows.Scan(&key, &value); err != nil {
			return err
		}
		target[key] = value
	}
	return rows.Err()
}
func (s *PostgresStore) ticketMutationError(ctx context.Context, ticketID string, err error) error {
	if !errors.Is(err, pgx.ErrNoRows) && !errors.Is(err, application.ErrNotFound) {
		return err
	}
	if _, getErr := s.GetTicket(ctx, ticketID); getErr != nil {
		return getErr
	}
	return application.ErrInvalidState
}
func dialogState(value json.RawMessage) []byte {
	if len(value) == 0 {
		return []byte("{}")
	}
	return value
}

func scanRequest(row pgx.Row) (domain.SupportRequest, error) {
	var r domain.SupportRequest
	var raw, state []byte
	err := row.Scan(&r.ID, &r.UserID, &r.OriginalMessage, &r.Status, &r.Topic, &r.SupportLevel, &r.AIStatus, &r.AIAnswer, &r.Confidence, &raw, &state, &r.CreatedAt, &r.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return r, application.ErrNotFound
	}
	if err != nil {
		return r, err
	}
	if err := json.Unmarshal(raw, &r.Sources); err != nil {
		return r, fmt.Errorf("decode request sources: %w", err)
	}
	r.DialogState = state
	return r, nil
}
func scanTicket(row pgx.Row) (domain.Ticket, error) {
	var t domain.Ticket
	var raw, intent []byte
	err := row.Scan(&t.ID, &t.UserID, &t.SupportRequestID, &t.Status, &t.Topic, &t.Subtopic, &t.MatchedTaxonomyID, &t.SupportLevel, &t.OriginalQuery, &t.ConversationContext, &t.AIAnswer, &t.AIConfidence, &raw, &t.ResolvedQuery, &intent, &t.RoutingReason, &t.EscalationReason, &t.OperatorID, &t.OperatorAnswer, &t.CreatedAt, &t.UpdatedAt, &t.TakenAt, &t.AnsweredAt, &t.ClosedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return t, application.ErrNotFound
	}
	if err != nil {
		return t, err
	}
	if err := json.Unmarshal(raw, &t.AISources); err != nil {
		return t, fmt.Errorf("decode ticket sources: %w", err)
	}
	t.IntentFrame = intent
	return t, nil
}
