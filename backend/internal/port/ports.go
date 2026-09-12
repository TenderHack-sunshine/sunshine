package port

import (
	"context"

	"github.com/TenderHack-sunshine/sunshine/backend/internal/domain"
)

type ProcessResponse struct {
	Status                domain.AIStatus `json:"status"`
	Answer                string          `json:"answer,omitempty"`
	ClarificationQuestion string          `json:"clarification_question,omitempty"`
	BlockedReason         string          `json:"blocked_reason,omitempty"`
	Topic                 string          `json:"topic,omitempty"`
	SupportLevel          string          `json:"support_level,omitempty"`
	Confidence            *float64        `json:"confidence,omitempty"`
	Sources               []domain.Source `json:"sources,omitempty"`
}

type ProcessRequest struct {
	Query          string           `json:"query"`
	ConversationID string           `json:"conversation_id,omitempty"`
	Context        []domain.Message `json:"context,omitempty"`
}

type RAGClient interface {
	Process(ctx context.Context, request ProcessRequest) (ProcessResponse, error)
}

type Store interface {
	CreateSupportRequest(ctx context.Context, request domain.SupportRequest, initialMessage domain.Message) error
	GetSupportRequest(ctx context.Context, requestID string) (domain.SupportRequest, error)
	AddMessage(ctx context.Context, message domain.Message) error
	ListMessages(ctx context.Context, requestID string) ([]domain.Message, error)
	ApplyRAGResult(ctx context.Context, requestID string, result ProcessResponse, aiMessage *domain.Message, ticket *domain.Ticket) error
	MarkRAGFailed(ctx context.Context, requestID string) error

	ListTickets(ctx context.Context, status *domain.TicketStatus) ([]domain.Ticket, error)
	GetTicket(ctx context.Context, ticketID string) (domain.Ticket, error)
	TakeTicket(ctx context.Context, ticketID, operatorID string) (domain.Ticket, error)
	AnswerTicket(ctx context.Context, ticketID, operatorID, answer string, message domain.Message) (domain.Ticket, error)
	CloseTicket(ctx context.Context, ticketID, operatorID string) (domain.Ticket, error)
	CreateFeedback(ctx context.Context, feedback domain.Feedback) error
	Analytics(ctx context.Context) (AnalyticsSnapshot, error)
}

type AnalyticsSnapshot struct {
	TotalRequests        int64
	AnsweredByAI         int64
	Escalated            int64
	RequestsByTopic      map[string]int64
	RequestsByLevel      map[string]int64
	TicketsByStatus      map[string]int64
	AverageFeedback      *float64
	UnresolvedFeedback   int64
	EscalationsByTopic   map[string]int64
	NegativeByTopic      map[string]int64
	FeedbackCountByTopic map[string]int64
}
