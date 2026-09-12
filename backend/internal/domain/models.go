package domain

import "time"

type RequestStatus string

const (
	RequestStatusProcessing        RequestStatus = "processing"
	RequestStatusAnswered          RequestStatus = "answered"
	RequestStatusNeedClarification RequestStatus = "need_clarification"
	RequestStatusBlocked           RequestStatus = "blocked"
	RequestStatusEscalated         RequestStatus = "escalated"
	RequestStatusAIFailed          RequestStatus = "ai_failed"
)

type AIStatus string

const (
	AIStatusPending           AIStatus = "pending"
	AIStatusAnswered          AIStatus = "answered"
	AIStatusNeedClarification AIStatus = "need_clarification"
	AIStatusBlocked           AIStatus = "blocked"
	AIStatusEscalated         AIStatus = "escalated"
	AIStatusFailed            AIStatus = "failed"
)

type TicketStatus string

const (
	TicketStatusWaitingForOperator TicketStatus = "WAITING_FOR_OPERATOR"
	TicketStatusInProgress         TicketStatus = "IN_PROGRESS"
	TicketStatusAnswered           TicketStatus = "ANSWERED"
	TicketStatusClosed             TicketStatus = "CLOSED"
)

type SenderType string

const (
	SenderUser     SenderType = "USER"
	SenderAI       SenderType = "AI"
	SenderOperator SenderType = "OPERATOR"
	SenderSystem   SenderType = "SYSTEM"
)

type Source struct {
	DocumentID string `json:"document_id"`
	Title      string `json:"title"`
	URL        string `json:"url"`
	Page       *int   `json:"page,omitempty"`
}

type SupportRequest struct {
	ID              string        `json:"id"`
	UserID          string        `json:"-"`
	OriginalMessage string        `json:"original_message"`
	Status          RequestStatus `json:"status"`
	Topic           string        `json:"topic,omitempty"`
	SupportLevel    string        `json:"support_level,omitempty"`
	AIStatus        AIStatus      `json:"ai_status"`
	AIAnswer        string        `json:"ai_answer,omitempty"`
	Confidence      *float64      `json:"confidence,omitempty"`
	Sources         []Source      `json:"sources,omitempty"`
	CreatedAt       time.Time     `json:"created_at"`
	UpdatedAt       time.Time     `json:"updated_at"`
}

type Message struct {
	ID        string     `json:"id"`
	RequestID string     `json:"support_request_id"`
	Sender    SenderType `json:"sender_type"`
	Text      string     `json:"text"`
	CreatedAt time.Time  `json:"created_at"`
}

type Ticket struct {
	ID                  string       `json:"id"`
	UserID              string       `json:"user_id"`
	SupportRequestID    string       `json:"support_request_id"`
	Status              TicketStatus `json:"status"`
	Topic               string       `json:"topic,omitempty"`
	SupportLevel        string       `json:"support_level,omitempty"`
	OriginalQuery       string       `json:"original_query"`
	ConversationContext string       `json:"conversation_context,omitempty"`
	AIAnswer            string       `json:"ai_answer,omitempty"`
	AIConfidence        *float64     `json:"ai_confidence,omitempty"`
	AISources           []Source     `json:"ai_sources,omitempty"`
	OperatorID          string       `json:"operator_id,omitempty"`
	OperatorAnswer      string       `json:"operator_answer,omitempty"`
	CreatedAt           time.Time    `json:"created_at"`
	UpdatedAt           time.Time    `json:"updated_at"`
	TakenAt             *time.Time   `json:"taken_at,omitempty"`
	AnsweredAt          *time.Time   `json:"answered_at,omitempty"`
	ClosedAt            *time.Time   `json:"closed_at,omitempty"`
}

type Feedback struct {
	ID               string    `json:"id"`
	UserID           string    `json:"-"`
	SupportRequestID string    `json:"support_request_id"`
	TicketID         string    `json:"ticket_id,omitempty"`
	Rating           int       `json:"rating"`
	Comment          string    `json:"comment,omitempty"`
	Resolved         bool      `json:"resolved"`
	CreatedAt        time.Time `json:"created_at"`
}
