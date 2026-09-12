package rag

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/TenderHack-sunshine/sunshine/backend/internal/domain"
	"github.com/TenderHack-sunshine/sunshine/backend/internal/port"
)

func TestClientProcessAnsweredSendsContract(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/process" {
			t.Fatalf("request = %s %s, want POST /process", r.Method, r.URL.Path)
		}
		var input port.ProcessRequest
		if err := json.NewDecoder(r.Body).Decode(&input); err != nil {
			t.Fatalf("decode request: %v", err)
		}
		if input.Query != "Не работает подпись" || input.ConversationID != "request-1" || len(input.Context) != 1 {
			t.Fatalf("unexpected request: %+v", input)
		}
		writeResponse(t, w, http.StatusOK, `{"status":"answered","answer":"Проверьте сертификат","topic":"electronic_signature","support_level":"L3","confidence":0.91,"sources":[{"document":"guide.pdf","section":"Подпись","page":12,"chunk_id":"guide:12"}]}`)
	}))
	defer server.Close()

	result, err := NewClient(server.URL, time.Second).Process(context.Background(), port.ProcessRequest{
		Query: "Не работает подпись", ConversationID: "request-1",
		Context: []domain.Message{{ID: "message-1", Text: "Не работает подпись", Sender: domain.SenderUser}},
	})
	if err != nil {
		t.Fatalf("Process: %v", err)
	}
	if result.Status != domain.AIStatusAnswered || result.Answer != "Проверьте сертификат" || result.Confidence == nil || *result.Confidence != 0.91 {
		t.Fatalf("unexpected response: %+v", result)
	}
	if len(result.Sources) != 1 || result.Sources[0].ChunkID != "guide:12" || result.Sources[0].Page == nil || *result.Sources[0].Page != 12 {
		t.Fatalf("unexpected sources: %+v", result.Sources)
	}
}

func TestClientProcessAcceptsClarificationAndEscalation(t *testing.T) {
	tests := []struct {
		name   string
		body   string
		status domain.AIStatus
	}{
		{"clarification", `{"status":"need_clarification","clarification_question":"Укажите номер закупки"}`, domain.AIStatusNeedClarification},
		{"escalation", `{"status":"escalated","topic":"payments","support_level":"L2","confidence":0.31,"sources":[]}`, domain.AIStatusEscalated},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				writeResponse(t, w, http.StatusOK, test.body)
			}))
			defer server.Close()

			result, err := NewClient(server.URL, time.Second).Process(context.Background(), port.ProcessRequest{Query: "Помогите"})
			if err != nil || result.Status != test.status {
				t.Fatalf("result=%+v err=%v", result, err)
			}
		})
	}
}

func TestClientProcessReturnsErrorForRAGFailures(t *testing.T) {
	t.Run("server 500", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			writeResponse(t, w, http.StatusInternalServerError, `{"error":"failed"}`)
		}))
		defer server.Close()
		assertProcessError(t, NewClient(server.URL, time.Second))
	})

	t.Run("invalid JSON", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			writeResponse(t, w, http.StatusOK, `{invalid`)
		}))
		defer server.Close()
		assertProcessError(t, NewClient(server.URL, time.Second))
	})

	t.Run("timeout", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			time.Sleep(100 * time.Millisecond)
			writeResponse(t, w, http.StatusOK, `{"status":"answered","answer":"late"}`)
		}))
		defer server.Close()
		assertProcessError(t, NewClient(server.URL, 5*time.Millisecond))
	})

	t.Run("connection failure", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}))
		url := server.URL
		server.Close()
		assertProcessError(t, NewClient(url, time.Second))
	})
}

func assertProcessError(t *testing.T, client *Client) {
	t.Helper()
	if _, err := client.Process(context.Background(), port.ProcessRequest{Query: "Помогите"}); err == nil {
		t.Fatal("Process error = nil, want an error")
	}
}

func writeResponse(t *testing.T, w http.ResponseWriter, status int, body string) {
	t.Helper()
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if _, err := w.Write([]byte(body)); err != nil {
		t.Fatalf("write response: %v", err)
	}
}
