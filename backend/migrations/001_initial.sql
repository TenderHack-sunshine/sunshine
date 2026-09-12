CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS support_requests (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    original_message TEXT NOT NULL,
    status TEXT NOT NULL,
    topic TEXT NOT NULL DEFAULT '',
    support_level TEXT NOT NULL DEFAULT '',
    ai_status TEXT NOT NULL,
    ai_answer TEXT NOT NULL DEFAULT '',
    confidence DOUBLE PRECISION,
    ai_sources JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    support_request_id TEXT NOT NULL REFERENCES support_requests(id) ON DELETE CASCADE,
    sender_type TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    support_request_id TEXT NOT NULL UNIQUE REFERENCES support_requests(id),
    status TEXT NOT NULL,
    topic TEXT NOT NULL DEFAULT '',
    support_level TEXT NOT NULL DEFAULT '',
    original_query TEXT NOT NULL,
    conversation_context TEXT NOT NULL DEFAULT '',
    ai_answer TEXT NOT NULL DEFAULT '',
    ai_confidence DOUBLE PRECISION,
    ai_sources JSONB NOT NULL DEFAULT '[]'::jsonb,
    operator_id TEXT NOT NULL DEFAULT '',
    operator_answer TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    taken_at TIMESTAMPTZ,
    answered_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS feedback (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    support_request_id TEXT NOT NULL UNIQUE REFERENCES support_requests(id),
    ticket_id TEXT REFERENCES tickets(id),
    rating SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment TEXT NOT NULL DEFAULT '',
    resolved BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_request_created ON messages (support_request_id, created_at);
CREATE INDEX IF NOT EXISTS idx_tickets_status_created ON tickets (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_support_requests_topic ON support_requests (topic);
CREATE INDEX IF NOT EXISTS idx_support_requests_user_created ON support_requests (user_id, created_at DESC);
