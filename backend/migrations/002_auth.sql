-- Authentication and role management.
--
-- Adds real accounts (email + password) on top of the existing anonymous
-- `users` rows, plus a role/support-line model for staff:
--   role = 'user'            regular supplier portal user (self-registers)
--   role = 'tech_specialist' support specialist, scoped to one line (L1/L2/L3)
--   role = 'admin'           can approve/reject specialists and grant roles
--
-- specialist_status tracks the approval workflow for self-registered
-- tech specialists: '' (n/a for role=user/admin) -> 'pending' -> 'approved'
-- or 'rejected'. Statements are idempotent because cmd/migrate re-applies
-- every file on each run (see backend/cmd/migrate).

ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user';
ALTER TABLE users ADD COLUMN IF NOT EXISTS line TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS specialist_status TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- Only real accounts (non-empty email) need to be unique; the pre-existing
-- anonymous rows created on demand by CreateSupportRequest keep email = ''.
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users (email) WHERE email <> '';

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_refresh_tokens_hash ON refresh_tokens (token_hash);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens (user_id);
CREATE INDEX IF NOT EXISTS idx_tickets_support_level ON tickets (support_level);
