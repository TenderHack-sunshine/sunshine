package application

import (
	"context"
	"strings"
	"time"

	"github.com/TenderHack-sunshine/sunshine/backend/internal/domain"
	"github.com/TenderHack-sunshine/sunshine/backend/internal/port"
)

// TicketService gates every method on actor.IsStaff() (tech specialist or
// admin) and, for a line-scoped tech specialist, on actor.CanHandleLine
// against the ticket's own SupportLevel. A plain "user" actor is rejected
// outright: tickets are the operator/specialist queue, not user-facing.
type TicketService struct {
	store port.Store
	now   func() time.Time
	newID func() (string, error)
}

func NewTicketService(store port.Store) *TicketService {
	return &TicketService{store: store, now: timeNow, newID: newID}
}

func timeNow() time.Time { return time.Now() }

func (s *TicketService) List(ctx context.Context, actor Actor, status *domain.TicketStatus) ([]domain.Ticket, error) {
	if !actor.IsStaff() {
		return nil, ErrForbidden
	}
	var line *domain.SupportLine
	if actor.Role == domain.RoleTechSpecialist && actor.Line != "" {
		line = &actor.Line
	}
	return s.store.ListTickets(ctx, status, line)
}

func (s *TicketService) GetDetail(ctx context.Context, actor Actor, ticketID string) (domain.Ticket, []domain.Message, error) {
	if !actor.IsStaff() {
		return domain.Ticket{}, nil, ErrForbidden
	}
	ticket, err := s.store.GetTicket(ctx, ticketID)
	if err != nil {
		return domain.Ticket{}, nil, err
	}
	if !actor.CanHandleLine(ticket.SupportLevel) {
		return domain.Ticket{}, nil, ErrForbidden
	}
	messages, err := s.store.ListMessages(ctx, ticket.SupportRequestID)
	if err != nil {
		return domain.Ticket{}, nil, err
	}
	return ticket, messages, nil
}

func (s *TicketService) Take(ctx context.Context, actor Actor, ticketID string) (domain.Ticket, error) {
	if !actor.IsStaff() {
		return domain.Ticket{}, ErrForbidden
	}
	if strings.TrimSpace(ticketID) == "" {
		return domain.Ticket{}, ErrInvalidInput
	}
	ticket, err := s.store.GetTicket(ctx, ticketID)
	if err != nil {
		return domain.Ticket{}, err
	}
	if !actor.CanHandleLine(ticket.SupportLevel) {
		return domain.Ticket{}, ErrForbidden
	}
	return s.store.TakeTicket(ctx, ticketID, actor.UserID)
}

func (s *TicketService) Answer(ctx context.Context, actor Actor, ticketID, text string) (domain.Ticket, error) {
	if !actor.IsStaff() {
		return domain.Ticket{}, ErrForbidden
	}
	if validateMessage(text) != nil {
		return domain.Ticket{}, ErrInvalidInput
	}
	ticket, err := s.store.GetTicket(ctx, ticketID)
	if err != nil {
		return domain.Ticket{}, err
	}
	if !actor.CanHandleLine(ticket.SupportLevel) {
		return domain.Ticket{}, ErrForbidden
	}
	messageID, err := s.newID()
	if err != nil {
		return domain.Ticket{}, err
	}
	message := domain.Message{ID: messageID, Sender: domain.SenderOperator, Text: strings.TrimSpace(text), CreatedAt: s.now().UTC()}
	return s.store.AnswerTicket(ctx, ticketID, actor.UserID, message.Text, message)
}

func (s *TicketService) Close(ctx context.Context, actor Actor, ticketID string) (domain.Ticket, error) {
	if !actor.IsStaff() {
		return domain.Ticket{}, ErrForbidden
	}
	if strings.TrimSpace(ticketID) == "" {
		return domain.Ticket{}, ErrInvalidInput
	}
	ticket, err := s.store.GetTicket(ctx, ticketID)
	if err != nil {
		return domain.Ticket{}, err
	}
	if !actor.CanHandleLine(ticket.SupportLevel) {
		return domain.Ticket{}, ErrForbidden
	}
	return s.store.CloseTicket(ctx, ticketID, actor.UserID)
}
