# Supplier Portal support backend

The backend owns the support workflow around the external AI module in
`../rag`. It does not implement retrieval, models, moderation, or any other AI
decision logic.

```text
Frontend → HTTP API → SupportService → AIClient → AI result
                                              ↓
                    PostgreSQL ← request / messages / ticket / feedback
```

## Workflow

1. A user creates a support request.
2. The request and its first message are persisted before the AI call.
3. `AIClient` returns exactly one of `answered`, `need_clarification`,
   `blocked`, or `escalated`.
4. The backend stores the result. Escalation creates a ticket atomically with
   the AI result.
5. An operator moves the ticket through `WAITING_FOR_OPERATOR → IN_PROGRESS →
   ANSWERED → CLOSED`.
6. The user can leave a single 1–5 feedback entry per request. Analytics reads
   the same persisted records.

## AI HTTP contract

Set `AI_SERVICE_URL` to the RAG service. Backend sends `POST
<AI_SERVICE_URL>/v1/process`:

```json
{
  "request_id": "...",
  "user_id": "...",
  "message": "Электронная подпись не работает",
  "conversation": [{"id":"...", "support_request_id":"...", "sender_type":"USER", "text":"...", "created_at":"..."}]
}
```

The RAG adapter must return this shape:

```json
{
  "status": "answered",
  "answer": "...",
  "topic": "electronic_signature",
  "support_level": "L3",
  "confidence": 0.84,
  "sources": [{"document_id":"...", "title":"...", "url":"...", "page": 4}]
}
```

For `need_clarification`, return `clarification_question`; for `blocked`,
return `blocked_reason`; for `escalated`, include the topic, support level,
confidence, sources, and optionally a preliminary `answer`. An unavailable or
invalid AI service returns a controlled `503` or `502`; it never crashes the
backend.

## API

The development identity header is `X-Portal-User-ID`. In production, an
authentication gateway must validate the user token and supply this identity.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST | `/support/requests` | Create and process a user request. |
| GET | `/support/requests/{id}` | Read the owner’s request. |
| POST | `/support/requests/{id}/messages` | Submit a clarification response. |
| GET | `/support/requests/{id}/messages` | Read the owner’s conversation. |
| GET | `/operator/tickets` | List tickets; optional `?status=` filter. |
| GET | `/operator/tickets/{id}` | Read ticket context. |
| POST | `/operator/tickets/{id}/take` | Move waiting ticket to in progress. |
| POST | `/operator/tickets/{id}/answer` | Store an operator answer. |
| POST | `/operator/tickets/{id}/close` | Close an answered ticket. |
| POST | `/feedback` | Save one 1–5 rating for a request. |
| GET | `/analytics/summary` | Request, ticket, and feedback totals. |
| GET | `/analytics/topics` | Request counts by topic and support level. |
| GET | `/analytics/feedback` | Feedback aggregates. |
| GET | `/analytics/conclusions` | Rule-based operational conclusions. |

Errors use one format:

```json
{"error":{"code":"INVALID_STATE","message":"Operation is not allowed in the current state"}}
```

## Run with Docker

```sh
docker compose up --build
```

Compose starts PostgreSQL, applies the SQL migration once through a separate
`migrate` job, then starts the API on host port 8081 by default (set
`API_HOST_PORT` to change it). The RAG service is external:
set `AI_SERVICE_URL` in the environment to an address reachable **from the
container**. For a RAG Compose service, use `http://rag:8000`; for a RAG
service outside Docker, use its network-reachable address. A request while it
is offline returns `AI_UNAVAILABLE` and remains stored with `ai_failed`
status.

## Local development

Apply migrations and run the API after setting the variables from
`.env.example`:

```sh
set -a; . backend/.env.example; set +a
go run ./backend/cmd/migrate
go run ./backend/cmd/api
```

The schema is in `backend/migrations`; the API container never creates tables
itself. `go test ./...` runs the backend flow tests.
