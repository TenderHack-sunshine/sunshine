package application

import "errors"

var (
	ErrInvalidInput      = errors.New("invalid input")
	ErrNotFound          = errors.New("not found")
	ErrForbidden         = errors.New("forbidden")
	ErrInvalidState      = errors.New("invalid state transition")
	ErrRAGUnavailable    = errors.New("RAG service is unavailable")
	ErrInvalidRAGResult  = errors.New("RAG service returned an invalid result")
	ErrDuplicateFeedback = errors.New("feedback already exists")
)
