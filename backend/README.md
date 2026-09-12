# Supplier Portal support backend

The Go backend owns the support workflow, PostgreSQL, tickets, operator flow,
feedback, and analytics. The separate Python service in `../rag` owns
moderation, retrieval, confidence, and answer generation.

```text
Frontend → Go handler → SupportService → RAGClient → HTTP → Python RAG
                            ↓                              ↓
                  PostgreSQL request / messages / ticket    RAG pipeline
```

## Workflow

1. A user creates a support request.
2. The request and its first message are persisted before the RAG call.
3. `RAGClient` returns exactly one of `answered`, `need_clarification`,
   `blocked`, or `escalated`.
4. The backend stores the result. Escalation creates a ticket atomically with
   the RAG result.
5. An operator moves the ticket through `WAITING_FOR_OPERATOR → IN_PROGRESS →
   ANSWERED → CLOSED`.
6. The user can leave a single 1–5 feedback entry per request. Analytics reads
   the same persisted records.

## Go ↔ Python RAG HTTP contract

Set `RAG_SERVICE_URL` to the RAG service. Backend sends `POST
<RAG_SERVICE_URL>/process`:

```json
{
  "query": "Электронная подпись не работает",
  "conversation_id": "...",
  "context": [{"id":"...", "support_request_id":"...", "sender_type":"USER", "text":"...", "created_at":"..."}]
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
  "sources": [{"document":"...", "section":"...", "page": 4, "chunk_id":"..."}]
}
```

For `need_clarification`, return `clarification_question`; for `blocked`,
return `blocked_reason`; for `escalated`, include the topic, support level,
confidence, sources, and optionally a preliminary `answer`. An unavailable or
invalid RAG service returns a controlled `503` or `502`; it never crashes the
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

Compose starts PostgreSQL, the Python RAG service, applies the SQL migration
once through a separate `migrate` job, then starts the API on host port 8081
by default (set `API_HOST_PORT` to change it). Docker uses
`RAG_SERVICE_URL=http://rag:8000`; local development uses
`http://localhost:8000`.

Before the first Docker run, build the local RAG artifacts in `rag/` (they are
intentionally ignored by Git):

```sh
python scripts/prepare_index.py
python scripts/build_ticket_bm25.py
```

The current RAG factory requires both
`data/processed/index/all_chunks.jsonl` and
`data/indexes/support_tickets_bm25.pkl`.

Then start the complete stack:

```sh
docker compose up --build
```

Both Go and Python expose `GET /health`.

## Local development

Start Python after preparing the artifacts:

```sh
cd rag && DATA_DIR="$PWD/data" python scripts/serve.py --port 8000
```

In another terminal at the repository root, apply migrations and start Go:

```sh
set -a; . backend/.env.example; set +a
go run ./backend/cmd/migrate
go run ./backend/cmd/api
```

The schema is in `backend/migrations`; the API container never creates tables
itself. `go test ./...` runs the backend flow and HTTP-client tests.

To check the full frontend → Go → Python path after `docker compose up`, run:

```sh
curl -i http://localhost:8081/support/requests \
  -H 'Content-Type: application/json' \
  -H 'X-Portal-User-ID: demo-user' \
  --data '{"message":"Не работает электронная подпись"}'
```
