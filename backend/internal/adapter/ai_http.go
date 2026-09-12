package adapter

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

// HTTPAIClient is the only backend boundary to the independently-developed
// AI module. The module must expose POST /v1/process with AIRequest and
// AIResult JSON documents defined in port/ports.go.
type HTTPAIClient struct {
	baseURL string
	client  *http.Client
}

func NewHTTPAIClient(baseURL string, timeout time.Duration) *HTTPAIClient {
	return &HTTPAIClient{baseURL: strings.TrimRight(baseURL, "/"), client: &http.Client{Timeout: timeout}}
}

func (c *HTTPAIClient) Process(ctx context.Context, input port.AIRequest) (port.AIResult, error) {
	payload, err := json.Marshal(input)
	if err != nil {
		return port.AIResult{}, fmt.Errorf("encode AI request: %w", err)
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/v1/process", bytes.NewReader(payload))
	if err != nil {
		return port.AIResult{}, fmt.Errorf("create AI request: %w", err)
	}
	request.Header.Set("Content-Type", "application/json")
	response, err := c.client.Do(request)
	if err != nil {
		return port.AIResult{}, fmt.Errorf("call AI service: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		return port.AIResult{}, fmt.Errorf("AI service returned %s", response.Status)
	}
	var result port.AIResult
	if err := json.NewDecoder(io.LimitReader(response.Body, 1<<20)).Decode(&result); err != nil {
		return port.AIResult{}, fmt.Errorf("decode AI response: %w", err)
	}
	switch result.Status {
	case domain.AIStatusAnswered, domain.AIStatusNeedClarification, domain.AIStatusBlocked, domain.AIStatusEscalated:
		return result, nil
	default:
		return port.AIResult{}, fmt.Errorf("unknown AI status %q", result.Status)
	}
}
