CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS tickets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id VARCHAR(255),

    status VARCHAR(50) NOT NULL DEFAULT 'open',

    topic VARCHAR(255),
    intent VARCHAR(255),

    is_technical BOOLEAN,

    initial_support_level VARCHAR(10),
    final_support_level VARCHAR(10),

    ai_resolved BOOLEAN NOT NULL DEFAULT FALSE,
    operator_involved BOOLEAN NOT NULL DEFAULT FALSE,

    final_resolution VARCHAR(100),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ,

    CONSTRAINT tickets_initial_support_level_check
        CHECK (
            initial_support_level IS NULL
            OR initial_support_level IN ('L1', 'L2', 'L3')
        ),

    CONSTRAINT tickets_final_support_level_check
        CHECK (
            final_support_level IS NULL
            OR final_support_level IN ('L1', 'L2', 'L3')
        )
);

CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    ticket_id UUID NOT NULL
        REFERENCES tickets(id)
        ON DELETE CASCADE,

    sender VARCHAR(20) NOT NULL,

    text TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT messages_sender_check
        CHECK (
            sender IN ('USER', 'AI', 'OPERATOR', 'SYSTEM')
        )
);

CREATE TABLE IF NOT EXISTS ticket_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    ticket_id UUID NOT NULL
        REFERENCES tickets(id)
        ON DELETE CASCADE,

    event_type VARCHAR(100) NOT NULL,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    ticket_id UUID NOT NULL
        REFERENCES tickets(id)
        ON DELETE CASCADE,

    rating VARCHAR(20) NOT NULL,

    reason VARCHAR(100),

    comment TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT feedback_rating_check
        CHECK (
            rating IN ('POSITIVE', 'NEGATIVE')
        )
);

CREATE INDEX IF NOT EXISTS idx_messages_ticket_id
    ON messages(ticket_id);

CREATE INDEX IF NOT EXISTS idx_ticket_events_ticket_id
    ON ticket_events(ticket_id);

CREATE INDEX IF NOT EXISTS idx_ticket_events_event_type
    ON ticket_events(event_type);

CREATE INDEX IF NOT EXISTS idx_feedback_ticket_id
    ON feedback(ticket_id);

CREATE INDEX IF NOT EXISTS idx_tickets_created_at
    ON tickets(created_at);

CREATE INDEX IF NOT EXISTS idx_tickets_topic
    ON tickets(topic);