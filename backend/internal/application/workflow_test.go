package application

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/TenderHack-sunshine/sunshine/backend/internal/domain"
	"github.com/TenderHack-sunshine/sunshine/backend/internal/port"
)

func TestSupportFlowAnswerClarificationAndEscalation(t *testing.T) {
	store := newFakeStore()
	confidence := 0.9
	rag := &fakeRAG{results: []port.ProcessResponse{
		{Status: domain.AIStatusAnswered, Answer: "Инструкция найдена", Topic: "signature", SupportLevel: "L3", Confidence: &confidence},
		{Status: domain.AIStatusNeedClarification, ClarificationQuestion: "Укажите номер закупки", Topic: "payments"},
		{Status: domain.AIStatusEscalated, Topic: "payments", SupportLevel: "L2", Confidence: &confidence},
	}}
	service := NewSupportService(store, rag)

	answered, ticket, err := service.Create(context.Background(), Actor{UserID: "user-1"}, "Не работает подпись")
	if err != nil || ticket != nil {
		t.Fatalf("expected direct answer, ticket=%v err=%v", ticket, err)
	}
	if answered.Status != domain.RequestStatusAnswered || answered.AIAnswer != "Инструкция найдена" {
		t.Fatalf("unexpected answer: %+v", answered)
	}

	clarified, ticket, err := service.Create(context.Background(), Actor{UserID: "user-1"}, "Не приходит платёж")
	if err != nil || ticket != nil || clarified.Status != domain.RequestStatusNeedClarification {
		t.Fatalf("expected clarification, request=%+v ticket=%v err=%v", clarified, ticket, err)
	}
	if clarified.AIAnswer != "Укажите номер закупки" {
		t.Fatalf("clarification was not saved: %+v", clarified)
	}

	escalated, ticket, err := service.AddUserMessage(context.Background(), Actor{UserID: "user-1"}, clarified.ID, "Номер 42")
	if err != nil || ticket == nil {
		t.Fatalf("expected ticket, ticket=%v err=%v", ticket, err)
	}
	if escalated.Status != domain.RequestStatusEscalated || ticket.Status != domain.TicketStatusWaitingForOperator {
		t.Fatalf("unexpected escalation: request=%+v ticket=%+v", escalated, ticket)
	}
	if len(store.messages[clarified.ID]) != 4 {
		t.Fatalf("expected user, AI clarification, user, AI escalation messages; got %d", len(store.messages[clarified.ID]))
	}
}

func TestTicketLifecycleFeedbackAnalyticsAndAIUnavailable(t *testing.T) {
	store := newFakeStore()
	confidence := 0.4
	support := NewSupportService(store, &fakeRAG{results: []port.ProcessResponse{{Status: domain.AIStatusEscalated, Topic: "electronic_signature", SupportLevel: "L3", Confidence: &confidence}}})
	request, ticket, err := support.Create(context.Background(), Actor{UserID: "user-1"}, "Подпись не работает")
	if err != nil || ticket == nil {
		t.Fatalf("create escalated request: ticket=%v err=%v", ticket, err)
	}

	tickets := NewTicketService(store)
	if _, err := tickets.Answer(context.Background(), "operator-1", ticket.ID, "Ответ"); !errors.Is(err, ErrInvalidState) {
		t.Fatalf("answer before take = %v, want invalid state", err)
	}
	taken, err := tickets.Take(context.Background(), "operator-1", ticket.ID)
	if err != nil || taken.Status != domain.TicketStatusInProgress {
		t.Fatalf("take: ticket=%+v err=%v", taken, err)
	}
	answered, err := tickets.Answer(context.Background(), "operator-1", ticket.ID, "Переустановите сертификат")
	if err != nil || answered.Status != domain.TicketStatusAnswered {
		t.Fatalf("answer: ticket=%+v err=%v", answered, err)
	}
	closed, err := tickets.Close(context.Background(), "operator-1", ticket.ID)
	if err != nil || closed.Status != domain.TicketStatusClosed {
		t.Fatalf("close: ticket=%+v err=%v", closed, err)
	}
	if _, err := tickets.Answer(context.Background(), "operator-1", ticket.ID, "Повторный ответ"); !errors.Is(err, ErrInvalidState) {
		t.Fatalf("answer after close = %v, want invalid state", err)
	}

	feedback, err := NewFeedbackService(store).Create(context.Background(), Actor{UserID: "user-1"}, request.ID, 2, "Проблема осталась", false)
	if err != nil || feedback.Rating != 2 {
		t.Fatalf("feedback=%+v err=%v", feedback, err)
	}
	if _, err := NewFeedbackService(store).Create(context.Background(), Actor{UserID: "user-1"}, request.ID, 5, "", true); !errors.Is(err, ErrDuplicateFeedback) {
		t.Fatalf("duplicate feedback error=%v", err)
	}

	analytics := NewAnalyticsService(store)
	summary, err := analytics.Summary(context.Background())
	if err != nil || summary.TotalRequests != 1 || summary.Escalated != 1 || summary.UnresolvedFeedback != 1 {
		t.Fatalf("summary=%+v err=%v", summary, err)
	}
	conclusions, err := analytics.Conclusions(context.Background())
	if err != nil || len(conclusions) == 0 {
		t.Fatalf("conclusions=%+v err=%v", conclusions, err)
	}

	failingStore := newFakeStore()
	failing := NewSupportService(failingStore, &fakeRAG{err: errors.New("offline")})
	if _, _, err := failing.Create(context.Background(), Actor{UserID: "user-2"}, "Помогите"); !errors.Is(err, ErrRAGUnavailable) {
		t.Fatalf("AI error=%v", err)
	}
	for _, saved := range failingStore.requests {
		if saved.Status != domain.RequestStatusAIFailed {
			t.Fatalf("request must be marked failed: %+v", saved)
		}
	}
}

type fakeRAG struct {
	results []port.ProcessResponse
	err     error
}

func (a *fakeRAG) Process(_ context.Context, _ port.ProcessRequest) (port.ProcessResponse, error) {
	if a.err != nil {
		return port.ProcessResponse{}, a.err
	}
	result := a.results[0]
	a.results = a.results[1:]
	return result, nil
}

type fakeStore struct {
	requests map[string]domain.SupportRequest
	messages map[string][]domain.Message
	tickets  map[string]domain.Ticket
	feedback map[string]domain.Feedback
}

func newFakeStore() *fakeStore {
	return &fakeStore{requests: map[string]domain.SupportRequest{}, messages: map[string][]domain.Message{}, tickets: map[string]domain.Ticket{}, feedback: map[string]domain.Feedback{}}
}
func (s *fakeStore) CreateSupportRequest(_ context.Context, r domain.SupportRequest, m domain.Message) error {
	s.requests[r.ID] = r
	s.messages[r.ID] = []domain.Message{m}
	return nil
}
func (s *fakeStore) GetSupportRequest(_ context.Context, id string) (domain.SupportRequest, error) {
	r, ok := s.requests[id]
	if !ok {
		return domain.SupportRequest{}, ErrNotFound
	}
	return r, nil
}
func (s *fakeStore) AddMessage(_ context.Context, m domain.Message) error {
	s.messages[m.RequestID] = append(s.messages[m.RequestID], m)
	return nil
}
func (s *fakeStore) ListMessages(_ context.Context, id string) ([]domain.Message, error) {
	return append([]domain.Message(nil), s.messages[id]...), nil
}
func (s *fakeStore) ApplyRAGResult(_ context.Context, id string, result port.ProcessResponse, message *domain.Message, ticket *domain.Ticket) error {
	request, ok := s.requests[id]
	if !ok {
		return ErrNotFound
	}
	request.AIStatus = result.Status
	request.Topic = result.Topic
	request.SupportLevel = result.SupportLevel
	request.Confidence = result.Confidence
	request.Sources = result.Sources
	switch result.Status {
	case domain.AIStatusAnswered:
		request.Status = domain.RequestStatusAnswered
		request.AIAnswer = result.Answer
	case domain.AIStatusNeedClarification:
		request.Status = domain.RequestStatusNeedClarification
		request.AIAnswer = result.ClarificationQuestion
	case domain.AIStatusBlocked:
		request.Status = domain.RequestStatusBlocked
		request.AIAnswer = result.BlockedReason
	case domain.AIStatusEscalated:
		request.Status = domain.RequestStatusEscalated
		request.AIAnswer = result.Answer
	}
	s.requests[id] = request
	if message != nil {
		s.messages[id] = append(s.messages[id], *message)
	}
	if ticket != nil {
		s.tickets[ticket.ID] = *ticket
	}
	return nil
}
func (s *fakeStore) MarkRAGFailed(_ context.Context, id string) error {
	request := s.requests[id]
	request.Status = domain.RequestStatusAIFailed
	request.AIStatus = domain.AIStatusFailed
	s.requests[id] = request
	return nil
}
func (s *fakeStore) ListTickets(_ context.Context, status *domain.TicketStatus) ([]domain.Ticket, error) {
	items := []domain.Ticket{}
	for _, ticket := range s.tickets {
		if status == nil || ticket.Status == *status {
			items = append(items, ticket)
		}
	}
	return items, nil
}
func (s *fakeStore) GetTicket(_ context.Context, id string) (domain.Ticket, error) {
	ticket, ok := s.tickets[id]
	if !ok {
		return domain.Ticket{}, ErrNotFound
	}
	return ticket, nil
}
func (s *fakeStore) TakeTicket(_ context.Context, id, operator string) (domain.Ticket, error) {
	ticket, err := s.GetTicket(context.Background(), id)
	if err != nil {
		return ticket, err
	}
	if ticket.Status != domain.TicketStatusWaitingForOperator {
		return ticket, ErrInvalidState
	}
	ticket.Status = domain.TicketStatusInProgress
	ticket.OperatorID = operator
	s.tickets[id] = ticket
	return ticket, nil
}
func (s *fakeStore) AnswerTicket(_ context.Context, id, operator, answer string, message domain.Message) (domain.Ticket, error) {
	ticket, err := s.GetTicket(context.Background(), id)
	if err != nil {
		return ticket, err
	}
	if ticket.Status != domain.TicketStatusInProgress || ticket.OperatorID != operator {
		return ticket, ErrInvalidState
	}
	ticket.Status = domain.TicketStatusAnswered
	ticket.OperatorAnswer = answer
	s.tickets[id] = ticket
	message.RequestID = ticket.SupportRequestID
	s.messages[message.RequestID] = append(s.messages[message.RequestID], message)
	return ticket, nil
}
func (s *fakeStore) CloseTicket(_ context.Context, id, operator string) (domain.Ticket, error) {
	ticket, err := s.GetTicket(context.Background(), id)
	if err != nil {
		return ticket, err
	}
	if ticket.Status != domain.TicketStatusAnswered || ticket.OperatorID != operator {
		return ticket, ErrInvalidState
	}
	ticket.Status = domain.TicketStatusClosed
	s.tickets[id] = ticket
	return ticket, nil
}
func (s *fakeStore) CreateFeedback(_ context.Context, feedback domain.Feedback) error {
	if _, ok := s.feedback[feedback.SupportRequestID]; ok {
		return ErrDuplicateFeedback
	}
	s.feedback[feedback.SupportRequestID] = feedback
	return nil
}
func (s *fakeStore) Analytics(_ context.Context) (port.AnalyticsSnapshot, error) {
	result := port.AnalyticsSnapshot{RequestsByTopic: map[string]int64{}, RequestsByLevel: map[string]int64{}, TicketsByStatus: map[string]int64{}, EscalationsByTopic: map[string]int64{}, NegativeByTopic: map[string]int64{}, FeedbackCountByTopic: map[string]int64{}}
	var total int
	for _, request := range s.requests {
		result.TotalRequests++
		result.RequestsByTopic[request.Topic]++
		result.RequestsByLevel[request.SupportLevel]++
		if request.Status == domain.RequestStatusAnswered {
			result.AnsweredByAI++
		}
		if request.Status == domain.RequestStatusEscalated {
			result.Escalated++
			result.EscalationsByTopic[request.Topic]++
		}
		total++
	}
	for _, ticket := range s.tickets {
		result.TicketsByStatus[string(ticket.Status)]++
	}
	var ratings int
	for _, feedback := range s.feedback {
		ratings += feedback.Rating
		if !feedback.Resolved {
			result.UnresolvedFeedback++
		}
		request := s.requests[feedback.SupportRequestID]
		result.FeedbackCountByTopic[request.Topic]++
		if feedback.Rating <= 2 {
			result.NegativeByTopic[request.Topic]++
		}
	}
	if len(s.feedback) > 0 {
		average := float64(ratings) / float64(len(s.feedback))
		result.AverageFeedback = &average
	}
	_ = total
	return result, nil
}

var _ port.Store = (*fakeStore)(nil)
var _ = time.Now
