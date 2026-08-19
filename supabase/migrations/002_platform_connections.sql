-- ═══════════════════════════════════════
-- Module 2 — Platform connections
-- Run in the Supabase SQL editor after the base schema.
-- ═══════════════════════════════════════

-- ─────────────────────────────────────
-- platform_connections
-- One row per platform. access_token / refresh_token are stored
-- Fernet-encrypted; they are never written or read as plain text.
-- ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS platform_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform TEXT NOT NULL UNIQUE
        CHECK (platform IN ('reddit','bluesky','mastodon','discord','telegram','threads','youtube')),
    status TEXT DEFAULT 'disconnected'
        CHECK (status IN ('disconnected','connected','error','expired')),
    account_name TEXT,
    account_id TEXT,
    access_token TEXT,
    refresh_token TEXT,
    token_expires_at TIMESTAMPTZ,
    scope TEXT,
    metadata JSONB,
    last_used_at TIMESTAMPTZ,
    last_error TEXT,
    connected_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────
-- platform_connection_logs
-- Append-only audit trail of connection lifecycle + fetch events.
-- ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS platform_connection_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform TEXT NOT NULL,
    event TEXT NOT NULL
        CHECK (event IN (
            'connect_initiated','connect_success','connect_failed',
            'token_refreshed','token_expired','disconnected',
            'fetch_success','fetch_failed'
        )),
    message TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS platform_connection_logs_platform_idx
    ON platform_connection_logs (platform, created_at DESC);
