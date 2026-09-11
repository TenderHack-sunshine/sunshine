package application

import "errors"

var (
	ErrInvalidInput      = errors.New("invalid input")
	ErrNotFound          = errors.New("not found")
	ErrForbidden         = errors.New("forbidden")
	ErrInvalidState      = errors.New("invalid state transition")
	ErrAIUnavailable     = errors.New("AI service is unavailable")
	ErrInvalidAIResult   = errors.New("AI service returned an invalid result")
	ErrDuplicateFeedback = errors.New("feedback already exists")
)
