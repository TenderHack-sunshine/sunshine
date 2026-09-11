package application

import (
	"context"
	"strings"
	"time"

	"github.com/TenderHack-sunshine/sunshine/backend/internal/domain"
	"github.com/TenderHack-sunshine/sunshine/backend/internal/port"
)

type TicketService struct {
	store port.Store
	now   func() time.Time
	newID func() (string, error)
}

func NewTicketService(store port.Store) *TicketService {
	return &TicketService{store: store, now: timeNow, newID: newID}
}

func timeNow() time.Time { return time.Now() }

func (s *TicketService) List(ctx context.Context, status *domain.TicketStatus) ([]domain.Ticket, error) {
	return s.store.ListTickets(ctx, status)
}

func (s *TicketService) Get(ctx context.Context, ticketID string) (domain.Ticket, error) {
	return s.store.GetTicket(ctx, ticketID)
}

func (s *TicketService) GetDetail(ctx context.Context, ticketID string) (domain.Ticket, []domain.Message, error) {
	ticket, err := s.store.GetTicket(ctx, ticketID)
	if err != nil {
		return domain.Ticket{}, nil, err
	}
	messages, err := s.store.ListMessages(ctx, ticket.SupportRequestID)
	if err != nil {
		return domain.Ticket{}, nil, err
	}
	return ticket, messages, nil
}

func (s *TicketService) Take(ctx context.Context, operatorID, ticketID string) (domain.Ticket, error) {
	if strings.TrimSpace(operatorID) == "" || strings.TrimSpace(ticketID) == "" {
		return domain.Ticket{}, ErrInvalidInput
	}
	return s.store.TakeTicket(ctx, ticketID, operatorID)
}

func (s *TicketService) Answer(ctx context.Context, operatorID, ticketID, text string) (domain.Ticket, error) {
	if strings.TrimSpace(operatorID) == "" || validateMessage(text) != nil {
		return domain.Ticket{}, ErrInvalidInput
	}
	messageID, err := s.newID()
	if err != nil {
		return domain.Ticket{}, err
	}
	message := domain.Message{ID: messageID, Sender: domain.SenderOperator, Text: strings.TrimSpace(text), CreatedAt: s.now().UTC()}
	return s.store.AnswerTicket(ctx, ticketID, operatorID, message.Text, message)
}

func (s *TicketService) Close(ctx context.Context, operatorID, ticketID string) (domain.Ticket, error) {
	if strings.TrimSpace(operatorID) == "" || strings.TrimSpace(ticketID) == "" {
		return domain.Ticket{}, ErrInvalidInput
	}
	return s.store.CloseTicket(ctx, ticketID, operatorID)
}
