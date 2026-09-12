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

## Authentication

There is no dev header anymore — every request (except `/health` and
`/auth/*`) requires `Authorization: Bearer <access_token>`. Roles:

- `user` — a regular supplier-portal user; self-registers via
  `POST /auth/register`.
- `tech_specialist` — scoped to one support line (`L1`/`L2`/`L3`); can
  self-register via `POST /auth/register-specialist`, but stays in
  `pending` status (cannot log in) until an admin approves them.
- `admin` — approves/rejects pending specialists and can grant or revoke
  `tech_specialist`/`admin` on any existing account directly
  (`POST /admin/users/{id}/role`), independent of the approval queue.

The first admin is created on startup from `ADMIN_EMAIL`/`ADMIN_PASSWORD`
(see `.env.example`); every other admin is created by an existing admin via
`POST /admin/users/{id}/role`.

| Method | Endpoint | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/auth/register` | none | Create a `user` account, returns tokens. |
| POST | `/auth/register-specialist` | none | Request `tech_specialist` for a line; pending until approved. |
| POST | `/auth/login` | none | Verify credentials, returns an access token + sets the refresh cookie. |
| POST | `/auth/refresh` | refresh cookie | Rotate the refresh token, returns a new access token. |
| POST | `/auth/logout` | refresh cookie | Revoke the refresh token. |
| GET | `/auth/me` | any | Current user's profile. |
| GET | `/admin/users` | admin | List all accounts. |
| GET | `/admin/specialists/pending` | admin | List specialists awaiting approval. |
| POST | `/admin/specialists/{id}/approve` | admin | Approve a pending specialist. |
| POST | `/admin/specialists/{id}/reject` | admin | Reject a pending specialist. |
| POST | `/admin/users/{id}/role` | admin | Set `{role, line}` on any user directly. |

The access token is a short-lived (`ACCESS_TOKEN_TTL`, default 15m) JWT
returned in the JSON body; the frontend keeps it in memory and calls
`/auth/refresh` (which relies on the httpOnly, `SameSite=Lax` refresh
cookie — no token ever touches `localStorage`) to get a new one silently.

## API

| Method | Endpoint | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/support/requests` | any | Create and process a user request. |
| GET | `/support/requests` | any | List the current user’s support requests. |
| GET | `/support/requests/{id}` | owner | Read the owner’s request. |
| POST | `/support/requests/{id}/messages` | owner | Submit a clarification response. |
| GET | `/support/requests/{id}/messages` | owner | Read the owner’s conversation. |
| GET | `/operator/tickets` | staff | List tickets; optional `?status=` filter; a line-scoped specialist only sees their line. |
| GET | `/operator/tickets/{id}` | staff (own line) | Read ticket context. |
| POST | `/operator/tickets/{id}/take` | staff (own line) | Move waiting ticket to in progress. |
| POST | `/operator/tickets/{id}/answer` | staff (own line) | Store an operator answer. |
| POST | `/operator/tickets/{id}/close` | staff (own line) | Close an answered ticket. |
| POST | `/feedback` | owner | Save one 1–5 rating for a request. |
| GET | `/analytics/summary` | staff | Request, ticket, and feedback totals. |
| GET | `/analytics/topics` | staff | Request counts by topic and support level. |
| GET | `/analytics/feedback` | staff | Feedback aggregates. |
| GET | `/analytics/conclusions` | staff | Rule-based operational conclusions. |

"staff" = `tech_specialist` or `admin`. "own line" = an admin can act on any
ticket; a tech specialist only on tickets whose `support_level` matches
their assigned line (a specialist with no line set is unscoped, for
accounts created before line assignment existed).

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
curl -s http://localhost:8081/auth/register \
  -H 'Content-Type: application/json' \
  --data '{"email":"demo@example.com","password":"correct-horse","display_name":"Демо Пользователь"}' \
  | tee /tmp/session.json

TOKEN=$(sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p' /tmp/session.json)

curl -i http://localhost:8081/support/requests \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TOKEN" \
  --data '{"message":"Не работает электронная подпись"}'
```
