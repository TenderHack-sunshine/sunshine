package rag

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/TenderHack-sunshine/sunshine/backend/internal/domain"
	"github.com/TenderHack-sunshine/sunshine/backend/internal/port"
)

// Client is the HTTP boundary between the Go application and the Python RAG
// service. It deliberately contains no retrieval or ticket business logic.
type Client struct {
	baseURL string
	http    *http.Client
}

func NewClient(baseURL string, timeout time.Duration) *Client {
	return &Client{baseURL: strings.TrimRight(baseURL, "/"), http: &http.Client{Timeout: timeout}}
}

func (c *Client) Process(ctx context.Context, input port.ProcessRequest) (port.ProcessResponse, error) {
	payload, err := json.Marshal(input)
	if err != nil {
		return port.ProcessResponse{}, fmt.Errorf("encode RAG request: %w", err)
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/process", bytes.NewReader(payload))
	if err != nil {
		return port.ProcessResponse{}, fmt.Errorf("create RAG request: %w", err)
	}
	request.Header.Set("Content-Type", "application/json")
	response, err := c.http.Do(request)
	if err != nil {
		return port.ProcessResponse{}, fmt.Errorf("call RAG service: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		return port.ProcessResponse{}, fmt.Errorf("RAG service returned %s", response.Status)
	}
	var result port.ProcessResponse
	if err := json.NewDecoder(io.LimitReader(response.Body, 1<<20)).Decode(&result); err != nil {
		return port.ProcessResponse{}, fmt.Errorf("decode RAG response: %w", err)
	}
	switch result.Status {
	case domain.AIStatusAnswered, domain.AIStatusNeedClarification, domain.AIStatusBlocked, domain.AIStatusEscalated:
		return result, nil
	default:
		return port.ProcessResponse{}, fmt.Errorf("unknown RAG status %q", result.Status)
	}
}

var _ port.RAGClient = (*Client)(nil)
