-- ═══════════════════════════════════════
-- Module 4 — Post Discovery and Scoring
-- Run in the Supabase SQL editor after migration 002.
-- ═══════════════════════════════════════

-- ─────────────────────────────────────
-- monitored_communities
-- The watch-list Module 4 monitors. Populated manually for now;
-- managed by Module 3 (community discovery) once that is built.
-- ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS monitored_communities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform TEXT NOT NULL,
    community_id TEXT NOT NULL,
    community_name TEXT NOT NULL,
    keywords TEXT[] NOT NULL DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    priority INTEGER DEFAULT 1,
    last_fetched_at TIMESTAMPTZ,
    fetch_count INTEGER DEFAULT 0,
    post_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (platform, community_id)
);

-- ─────────────────────────────────────
-- discovered_posts
-- Every fetched post before/after scoring. Also the dedup layer.
-- ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS discovered_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform TEXT NOT NULL,
    post_id TEXT NOT NULL,
    post_url TEXT,
    author_name TEXT,
    author_id TEXT,
    title TEXT,
    content TEXT NOT NULL,
    thread_content TEXT,
    community_name TEXT,
    community_id TEXT,
    posted_at TIMESTAMPTZ,
    fetched_at TIMESTAMPTZ DEFAULT now(),
    engagement_score FLOAT,
    relevance_score FLOAT,
    relevance_reasoning TEXT,
    status TEXT DEFAULT 'fetched'
        CHECK (status IN ('fetched','scoring','scored','submitted','filtered_out','duplicate','error')),
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    worker_run_id UUID,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (platform, post_id)
);

CREATE INDEX IF NOT EXISTS discovered_posts_status_idx ON discovered_posts (status);
CREATE INDEX IF NOT EXISTS discovered_posts_relevance_idx ON discovered_posts (relevance_score DESC);
CREATE INDEX IF NOT EXISTS discovered_posts_fetched_idx ON discovered_posts (fetched_at DESC);

-- ─────────────────────────────────────
-- discovery_runs
-- One row per worker execution.
-- ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS discovery_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trigger_type TEXT NOT NULL CHECK (trigger_type IN ('scheduled','manual','api')),
    status TEXT DEFAULT 'running' CHECK (status IN ('running','completed','failed','partial')),
    platforms_checked TEXT[],
    posts_fetched INTEGER DEFAULT 0,
    posts_scored INTEGER DEFAULT 0,
    posts_submitted INTEGER DEFAULT 0,
    posts_filtered INTEGER DEFAULT 0,
    posts_duplicated INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    duration_seconds FLOAT
);

CREATE INDEX IF NOT EXISTS discovery_runs_started_idx ON discovery_runs (started_at DESC);

-- ─────────────────────────────────────
-- discovery_settings — single-row config
-- ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS discovery_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    is_enabled BOOLEAN DEFAULT true,
    schedule_interval_minutes INTEGER DEFAULT 30,
    max_posts_per_run INTEGER DEFAULT 50,
    max_conversations_per_day INTEGER DEFAULT 5,
    min_relevance_score FLOAT DEFAULT 0.65,
    scoring_batch_size INTEGER DEFAULT 10,
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Seed the single default settings row only if none exists.
INSERT INTO discovery_settings
    (is_enabled, schedule_interval_minutes, max_posts_per_run,
     max_conversations_per_day, min_relevance_score, scoring_batch_size)
SELECT true, 30, 50, 5, 0.65, 10
WHERE NOT EXISTS (SELECT 1 FROM discovery_settings);
