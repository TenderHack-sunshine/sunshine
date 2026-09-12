package application

import (
	"context"
	"sort"

	"github.com/TenderHack-sunshine/sunshine/backend/internal/domain"
	"github.com/TenderHack-sunshine/sunshine/backend/internal/port"
)

type AnalyticsService struct{ store port.Store }

func NewAnalyticsService(store port.Store) *AnalyticsService { return &AnalyticsService{store: store} }

type Summary struct {
	TotalRequests      int64            `json:"total_requests"`
	AnsweredByAI       int64            `json:"answered_by_ai"`
	Escalated          int64            `json:"escalated"`
	EscalationRate     float64          `json:"escalation_rate"`
	RequestsByTopic    map[string]int64 `json:"requests_by_topic"`
	RequestsByLevel    map[string]int64 `json:"requests_by_support_level"`
	TicketsByStatus    map[string]int64 `json:"tickets_by_status"`
	AverageFeedback    *float64         `json:"average_feedback"`
	UnresolvedFeedback int64            `json:"unresolved_feedback_count"`
}
type OperationalOverview struct {
	Total                    int64   `json:"total"`
	AnsweredByAI             int64   `json:"answered_by_ai"`
	AnsweredByAIPercent      float64 `json:"answered_by_ai_percent"`
	Escalated                int64   `json:"escalated"`
	EscalatedPercent         float64 `json:"escalated_percent"`
	NeedClarification        int64   `json:"need_clarification"`
	NeedClarificationPercent float64 `json:"need_clarification_percent"`
	InProgress               int64   `json:"in_progress"`
}

type Conclusion struct {
	Type    string  `json:"type"`
	Topic   string  `json:"topic"`
	Message string  `json:"message"`
	Value   float64 `json:"value"`
}

func (s *AnalyticsService) Snapshot(ctx context.Context) (port.AnalyticsSnapshot, error) {
	return s.store.Analytics(ctx)
}

func (s *AnalyticsService) Summary(ctx context.Context) (Summary, error) {
	snapshot, err := s.Snapshot(ctx)
	if err != nil {
		return Summary{}, err
	}
	rate := 0.0
	if snapshot.TotalRequests > 0 {
		rate = float64(snapshot.Escalated) / float64(snapshot.TotalRequests)
	}
	return Summary{
		TotalRequests:      snapshot.TotalRequests,
		AnsweredByAI:       snapshot.AnsweredByAI,
		Escalated:          snapshot.Escalated,
		EscalationRate:     rate,
		RequestsByTopic:    snapshot.RequestsByTopic,
		RequestsByLevel:    snapshot.RequestsByLevel,
		TicketsByStatus:    snapshot.TicketsByStatus,
		AverageFeedback:    snapshot.AverageFeedback,
		UnresolvedFeedback: snapshot.UnresolvedFeedback,
	}, nil
}

func (s *AnalyticsService) Requests(ctx context.Context) ([]domain.SupportRequest, error) {
	return s.store.ListSupportRequests(ctx)
}

func (s *AnalyticsService) OperationalOverview(ctx context.Context) (OperationalOverview, error) {
	snapshot, err := s.store.OperationalAnalytics(ctx)
	if err != nil {
		return OperationalOverview{}, err
	}

	result := OperationalOverview{
		Total:             snapshot.Total,
		AnsweredByAI:      snapshot.AnsweredByAI,
		Escalated:         snapshot.Escalated,
		NeedClarification: snapshot.NeedClarification,
		InProgress:        snapshot.InProgress,
	}

	if snapshot.Total > 0 {
		total := float64(snapshot.Total)

		result.AnsweredByAIPercent =
			float64(snapshot.AnsweredByAI) / total * 100

		result.EscalatedPercent =
			float64(snapshot.Escalated) / total * 100

		result.NeedClarificationPercent =
			float64(snapshot.NeedClarification) / total * 100
	}

	return result, nil
}

func (s *AnalyticsService) Conclusions(ctx context.Context) ([]Conclusion, error) {
	snapshot, err := s.Snapshot(ctx)
	if err != nil {
		return nil, err
	}
	conclusions := make([]Conclusion, 0)
	for topic, requests := range snapshot.RequestsByTopic {
		if requests >= 5 {
			conclusions = append(conclusions, Conclusion{Type: "frequent_topic", Topic: topic, Message: "Часто встречающаяся проблема", Value: float64(requests)})
		}
		if escalated := snapshot.EscalationsByTopic[topic]; requests > 0 && float64(escalated)/float64(requests) >= 0.5 {
			conclusions = append(conclusions, Conclusion{Type: "high_escalation_rate", Topic: topic, Message: "Большая доля обращений передаётся оператору", Value: float64(escalated) / float64(requests)})
		}
		if total := snapshot.FeedbackCountByTopic[topic]; total > 0 && float64(snapshot.NegativeByTopic[topic])/float64(total) >= 0.5 {
			conclusions = append(conclusions, Conclusion{Type: "low_satisfaction", Topic: topic, Message: "Низкая удовлетворённость пользователей по теме", Value: float64(snapshot.NegativeByTopic[topic]) / float64(total)})
		}
	}
	sort.Slice(conclusions, func(i, j int) bool { return conclusions[i].Value > conclusions[j].Value })
	return conclusions, nil
}
