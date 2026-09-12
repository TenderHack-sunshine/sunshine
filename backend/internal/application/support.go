package application

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"log/slog"
	"strings"
	"time"

	"github.com/TenderHack-sunshine/sunshine/backend/internal/domain"
	"github.com/TenderHack-sunshine/sunshine/backend/internal/port"
)

const maxMessageLength = 8_000

const escalatedFollowUpAcknowledgement = "Сообщение добавлено в обращение технической поддержки."

type SupportService struct {
	store port.Store
	rag   port.RAGClient
	now   func() time.Time
	newID func() (string, error)
}

func NewSupportService(store port.Store, rag port.RAGClient) *SupportService {
	return &SupportService{store: store, rag: rag, now: time.Now, newID: newID}
}

func (s *SupportService) Create(ctx context.Context, actor Actor, text string) (domain.SupportRequest, *domain.Ticket, error) {
	if err := validateMessage(text); err != nil || strings.TrimSpace(actor.UserID) == "" {
		return domain.SupportRequest{}, nil, ErrInvalidInput
	}
	requestID, err := s.newID()
	if err != nil {
		return domain.SupportRequest{}, nil, err
	}
	messageID, err := s.newID()
	if err != nil {
		return domain.SupportRequest{}, nil, err
	}
	now := s.now().UTC()
	request := domain.SupportRequest{ID: requestID, UserID: actor.UserID, OriginalMessage: strings.TrimSpace(text), Status: domain.RequestStatusProcessing, AIStatus: domain.AIStatusPending, CreatedAt: now, UpdatedAt: now}
	message := domain.Message{ID: messageID, RequestID: requestID, Sender: domain.SenderUser, Text: request.OriginalMessage, CreatedAt: now}
	if err := s.store.CreateSupportRequest(ctx, request, message); err != nil {
		return domain.SupportRequest{}, nil, err
	}
	return s.process(ctx, request, []domain.Message{message})
}

func (s *SupportService) AddUserMessage(ctx context.Context, actor Actor, requestID, text string) (domain.SupportRequest, *domain.Ticket, error) {
	if err := validateMessage(text); err != nil {
		return domain.SupportRequest{}, nil, ErrInvalidInput
	}
	request, err := s.ownedRequest(ctx, actor, requestID)
	if err != nil {
		return domain.SupportRequest{}, nil, err
	}
	switch request.Status {
	case domain.RequestStatusAnswered, domain.RequestStatusBlocked, domain.RequestStatusNeedClarification, domain.RequestStatusOfferHandoff, domain.RequestStatusAIFailed, domain.RequestStatusEscalated:
		// A dialog remains open for follow-up questions after an answer,
		// an insufficient answer, a clarification request, or escalation.
	default:
		return domain.SupportRequest{}, nil, ErrInvalidState
	}
	messageID, err := s.newID()
	if err != nil {
		return domain.SupportRequest{}, nil, err
	}
	message := domain.Message{ID: messageID, RequestID: request.ID, Sender: domain.SenderUser, Text: strings.TrimSpace(text), CreatedAt: s.now().UTC()}
	if err := s.store.AddMessage(ctx, message); err != nil {
		return domain.SupportRequest{}, nil, err
	}
	if request.Status == domain.RequestStatusEscalated {
		// A ticket must not become a moderation bypass.  Check every new
		// message with the same RAG-side filter used before escalation, while
		// deliberately avoiding retrieval/generation for an operator follow-up.
		moderation, err := s.rag.Process(ctx, port.ProcessRequest{
			Query: message.Text, ConversationID: request.ID, ModerationOnly: true,
		})
		if err != nil {
			return domain.SupportRequest{}, nil, ErrRAGUnavailable
		}
		if moderation.Status == domain.AIStatusBlocked {
			blockedText := strings.TrimSpace(moderation.BlockedReason)
			if blockedText == "" {
				blockedText = "Пожалуйста, переформулируйте сообщение без нецензурной лексики."
			}
			blockedID, err := s.newID()
			if err != nil {
				return domain.SupportRequest{}, nil, err
			}
			blocked := domain.Message{ID: blockedID, RequestID: request.ID, Sender: domain.SenderAI, Text: blockedText, CreatedAt: s.now().UTC()}
			if err := s.store.AddMessage(ctx, blocked); err != nil {
				return domain.SupportRequest{}, nil, err
			}
			// Do not refresh the operator ticket with rejected content.
			return request, nil, nil
		}
		ackID, err := s.newID()
		if err != nil {
			return domain.SupportRequest{}, nil, err
		}
		ack := domain.Message{ID: ackID, RequestID: request.ID, Sender: domain.SenderAI, Text: escalatedFollowUpAcknowledgement, CreatedAt: s.now().UTC()}
		if err := s.store.AddMessage(ctx, ack); err != nil {
			return domain.SupportRequest{}, nil, err
		}
		if err := s.store.RefreshTicketContext(ctx, request.ID); err != nil {
			return domain.SupportRequest{}, nil, err
		}
		return request, nil, nil
	}
	messages, err := s.store.ListMessages(ctx, request.ID)
	if err != nil {
		return domain.SupportRequest{}, nil, err
	}
	return s.process(ctx, request, messages)
}

func (s *SupportService) Get(ctx context.Context, actor Actor, requestID string) (domain.SupportRequest, error) {
	return s.ownedRequest(ctx, actor, requestID)
}

func (s *SupportService) List(ctx context.Context, actor Actor) ([]domain.SupportRequest, error) {
	if strings.TrimSpace(actor.UserID) == "" {
		return nil, ErrInvalidInput
	}
	return s.store.ListSupportRequestsByUser(ctx, actor.UserID)
}

func (s *SupportService) ListMessages(ctx context.Context, actor Actor, requestID string) ([]domain.Message, error) {
	if _, err := s.ownedRequest(ctx, actor, requestID); err != nil {
		return nil, err
	}
	return s.store.ListMessages(ctx, requestID)
}

func (s *SupportService) ownedRequest(ctx context.Context, actor Actor, requestID string) (domain.SupportRequest, error) {
	request, err := s.store.GetSupportRequest(ctx, requestID)
	if err != nil {
		return domain.SupportRequest{}, err
	}
	if request.UserID != actor.UserID {
		return domain.SupportRequest{}, ErrForbidden
	}
	return request, nil
}

func (s *SupportService) process(ctx context.Context, request domain.SupportRequest, conversation []domain.Message) (domain.SupportRequest, *domain.Ticket, error) {
	last := conversation[len(conversation)-1]
	result, err := s.rag.Process(ctx, port.ProcessRequest{Query: last.Text, ConversationID: request.ID, Context: conversation, DialogState: request.DialogState})
	if err != nil {
		slog.Error("RAG processing failed", "support_request_id", request.ID, "user_id", request.UserID, "error", err)
		_ = s.store.MarkRAGFailed(ctx, request.ID)
		return domain.SupportRequest{}, nil, ErrRAGUnavailable
	}

	aiMessage, ticket, err := s.resultArtifacts(request, conversation, result)
	if err != nil {
		return domain.SupportRequest{}, nil, err
	}
	if err := s.store.ApplyRAGResult(ctx, request.ID, result, aiMessage, ticket); err != nil {
		return domain.SupportRequest{}, nil, err
	}
	updated, err := s.store.GetSupportRequest(ctx, request.ID)
	if err != nil {
		return domain.SupportRequest{}, nil, err
	}
	return updated, ticket, nil
}

func (s *SupportService) resultArtifacts(request domain.SupportRequest, conversation []domain.Message, result port.ProcessResponse) (*domain.Message, *domain.Ticket, error) {
	now := s.now().UTC()
	messageText := ""
	switch result.Status {
	case domain.AIStatusAnswered:
		messageText = strings.TrimSpace(result.Answer)
	case domain.AIStatusNeedClarification:
		messageText = strings.TrimSpace(result.ClarificationQuestion)
	case domain.AIStatusBlocked:
		messageText = strings.TrimSpace(result.BlockedReason)
	case domain.AIStatusOfferHandoff:
		messageText = strings.TrimSpace(result.Answer)
	case domain.AIStatusEscalateConfirmed, domain.AIStatusEscalated:
		messageText = strings.TrimSpace(result.Answer)
		if messageText == "" {
			messageText = "К сожалению, ответ требует участия специалиста. Я передал обращение в техническую поддержку."
		}
	default:
		return nil, nil, ErrInvalidRAGResult
	}
	if messageText == "" {
		return nil, nil, ErrInvalidRAGResult
	}
	messageID, err := s.newID()
	if err != nil {
		return nil, nil, err
	}
	aiMessage := &domain.Message{ID: messageID, RequestID: request.ID, Sender: domain.SenderAI, Text: messageText, CreatedAt: now}
	if result.Status != domain.AIStatusEscalateConfirmed && result.Status != domain.AIStatusEscalated {
		return aiMessage, nil, nil
	}
	ticketID, err := s.newID()
	if err != nil {
		return nil, nil, err
	}
	ticket := &domain.Ticket{ID: ticketID, UserID: request.UserID, SupportRequestID: request.ID, Status: domain.TicketStatusWaitingForOperator, Topic: result.Topic, Subtopic: result.Subtopic, MatchedTaxonomyID: result.MatchedTaxonomyID, SupportLevel: result.SupportLevel, OriginalQuery: request.OriginalMessage, ConversationContext: conversationText(conversation), AIAnswer: result.Answer, AIConfidence: result.Confidence, AISources: result.Sources, ResolvedQuery: result.ResolvedQuery, IntentFrame: result.DialogState, RoutingReason: result.RoutingReason, EscalationReason: result.EscalationReason, CreatedAt: now, UpdatedAt: now}
	return aiMessage, ticket, nil
}

func validateMessage(text string) error {
	trimmed := strings.TrimSpace(text)
	if trimmed == "" || len([]rune(trimmed)) > maxMessageLength {
		return ErrInvalidInput
	}
	return nil
}

func conversationText(messages []domain.Message) string {
	parts := make([]string, 0, len(messages))
	for _, message := range messages {
		parts = append(parts, string(message.Sender)+": "+message.Text)
	}
	return strings.Join(parts, "\n")
}

func newID() (string, error) {
	bytes := make([]byte, 16)
	if _, err := rand.Read(bytes); err != nil {
		return "", err
	}
	return hex.EncodeToString(bytes), nil
}
