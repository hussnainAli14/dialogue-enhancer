-- ═══════════════════════════════════════
-- Module 3 — Community Discovery and Management
-- Run in the Supabase SQL editor after migration 003.
-- monitored_communities already exists (from 003) — not recreated here.
-- ═══════════════════════════════════════

-- ─────────────────────────────────────
-- discovery_topics — author's topics/keywords for keyword discovery
-- ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS discovery_topics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic TEXT NOT NULL,
    keywords TEXT[] NOT NULL DEFAULT '{}',
    description TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────
-- monitored_people — people whose communities/activity we track
-- ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS monitored_people (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    platform_handles JSONB NOT NULL DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    last_checked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────
-- community_suggestions — discovery approval queue
-- ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS community_suggestions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform TEXT NOT NULL,
    community_id TEXT NOT NULL,
    community_name TEXT NOT NULL,
    community_url TEXT,
    description TEXT,
    member_count INTEGER,
    activity_level TEXT CHECK (activity_level IN ('high','medium','low','unknown')),
    discovery_method TEXT NOT NULL CHECK (discovery_method IN ('keyword','people_based','both')),
    discovered_via_keywords TEXT[] DEFAULT '{}',
    discovered_via_people TEXT[] DEFAULT '{}',
    relevance_score FLOAT,
    relevance_reasoning TEXT,
    suggested_keywords TEXT[] DEFAULT '{}',
    status TEXT DEFAULT 'pending'
        CHECK (status IN ('pending','approved','rejected','already_monitoring')),
    rejection_reason TEXT,
    approved_at TIMESTAMPTZ,
    rejected_at TIMESTAMPTZ,
    discovery_run_id UUID,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (platform, community_id)
);

CREATE INDEX IF NOT EXISTS community_suggestions_status_idx
    ON community_suggestions (status, relevance_score DESC);

-- ─────────────────────────────────────
-- community_discovery_runs — audit log
-- ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS community_discovery_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trigger_type TEXT CHECK (trigger_type IN ('scheduled','manual','api')),
    discovery_modes TEXT[],
    platforms_searched TEXT[],
    topics_used TEXT[],
    people_checked INTEGER DEFAULT 0,
    communities_found INTEGER DEFAULT 0,
    communities_new INTEGER DEFAULT 0,
    communities_already_known INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running' CHECK (status IN ('running','completed','failed','partial')),
    error_message TEXT,
    started_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    duration_seconds FLOAT
);

CREATE INDEX IF NOT EXISTS community_discovery_runs_started_idx
    ON community_discovery_runs (started_at DESC);

-- ─────────────────────────────────────
-- Extend discovery_settings with community-discovery settings
-- ─────────────────────────────────────
ALTER TABLE discovery_settings ADD COLUMN IF NOT EXISTS
    community_discovery_enabled BOOLEAN DEFAULT true;
ALTER TABLE discovery_settings ADD COLUMN IF NOT EXISTS
    community_schedule_hours INTEGER DEFAULT 24;
ALTER TABLE discovery_settings ADD COLUMN IF NOT EXISTS
    max_communities_per_platform INTEGER DEFAULT 20;
ALTER TABLE discovery_settings ADD COLUMN IF NOT EXISTS
    min_community_relevance_score FLOAT DEFAULT 0.60;
ALTER TABLE discovery_settings ADD COLUMN IF NOT EXISTS
    max_community_suggestions INTEGER DEFAULT 50;

-- ─────────────────────────────────────
-- Seed starter topics (only if none exist)
-- ─────────────────────────────────────
INSERT INTO discovery_topics (topic, keywords)
SELECT * FROM (VALUES
    ('Coaching and Leadership',
     ARRAY['coaching','leadership','executive coach','team leadership','management']),
    ('Personal Growth',
     ARRAY['personal development','personal growth','self improvement','habits','mindset']),
    ('Spirituality and Meaning',
     ARRAY['spirituality','meaning','purpose','contemplative','inner work']),
    ('Community Building',
     ARRAY['community','belonging','facilitation','dialogue','connection']),
    ('Psychological Safety',
     ARRAY['psychological safety','vulnerability','trust','accountability','conflict'])
) AS t(topic, keywords)
WHERE NOT EXISTS (SELECT 1 FROM discovery_topics);
