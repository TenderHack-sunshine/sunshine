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
	Document string `json:"document"`
	Section  string `json:"section,omitempty"`
	Page     *int   `json:"page,omitempty"`
	ChunkID  string `json:"chunk_id"`
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

// Role distinguishes regular portal users from support staff.
type Role string

const (
	RoleUser           Role = "user"
	RoleTechSpecialist Role = "tech_specialist"
	RoleAdmin          Role = "admin"
)

// SupportLine is the tech specialist's assigned support line. It mirrors the
// support_level values ("L1"/"L2"/"L3") already produced by the RAG pipeline
// on SupportRequest/Ticket, so a specialist's line can be matched directly
// against a ticket's SupportLevel.
type SupportLine string

const (
	SupportLineNone SupportLine = ""
	SupportLineL1   SupportLine = "L1"
	SupportLineL2   SupportLine = "L2"
	SupportLineL3   SupportLine = "L3"
)

// SpecialistStatus tracks the approval workflow for a self-registered tech
// specialist. It is meaningless (empty) for role=user and role=admin.
type SpecialistStatus string

const (
	SpecialistStatusNone     SpecialistStatus = ""
	SpecialistStatusPending  SpecialistStatus = "pending"
	SpecialistStatusApproved SpecialistStatus = "approved"
	SpecialistStatusRejected SpecialistStatus = "rejected"
)

type User struct {
	ID               string           `json:"id"`
	Email            string           `json:"email"`
	PasswordHash     string           `json:"-"`
	DisplayName      string           `json:"display_name"`
	Role             Role             `json:"role"`
	Line             SupportLine      `json:"line,omitempty"`
	SpecialistStatus SpecialistStatus `json:"specialist_status,omitempty"`
	CreatedAt        time.Time        `json:"created_at"`
	UpdatedAt        time.Time        `json:"updated_at"`
}

// RefreshToken is stored hashed (never the raw token) so a leaked database
// cannot be used to mint sessions; it is looked up by TokenHash and can be
// revoked individually or in bulk per user.
type RefreshToken struct {
	ID        string     `json:"-"`
	UserID    string     `json:"-"`
	TokenHash string     `json:"-"`
	ExpiresAt time.Time  `json:"-"`
	RevokedAt *time.Time `json:"-"`
	CreatedAt time.Time  `json:"-"`
}
