package application

import (
	"context"
	"strings"
	"time"

	"github.com/TenderHack-sunshine/sunshine/backend/internal/domain"
	"github.com/TenderHack-sunshine/sunshine/backend/internal/port"
)

type FeedbackService struct {
	store port.Store
	now   func() time.Time
	newID func() (string, error)
}

func NewFeedbackService(store port.Store) *FeedbackService {
	return &FeedbackService{store: store, now: time.Now, newID: newID}
}

func (s *FeedbackService) Create(ctx context.Context, actor Actor, requestID string, rating int, comment string, resolved bool) (domain.Feedback, error) {
	if strings.TrimSpace(actor.UserID) == "" || strings.TrimSpace(requestID) == "" || rating < 1 || rating > 5 || len([]rune(comment)) > maxMessageLength {
		return domain.Feedback{}, ErrInvalidInput
	}
	request, err := s.store.GetSupportRequest(ctx, requestID)
	if err != nil {
		return domain.Feedback{}, err
	}
	if request.UserID != actor.UserID {
		return domain.Feedback{}, ErrForbidden
	}
	if request.Status != domain.RequestStatusAnswered && request.Status != domain.RequestStatusEscalated {
		return domain.Feedback{}, ErrInvalidState
	}
	id, err := s.newID()
	if err != nil {
		return domain.Feedback{}, err
	}
	feedback := domain.Feedback{ID: id, UserID: actor.UserID, SupportRequestID: request.ID, Rating: rating, Comment: strings.TrimSpace(comment), Resolved: resolved, CreatedAt: s.now().UTC()}
	if err := s.store.CreateFeedback(ctx, feedback); err != nil {
		return domain.Feedback{}, err
	}
	return feedback, nil
}
