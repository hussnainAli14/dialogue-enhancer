-- ─────────────────────────────────────
-- Module: reply tracking
-- Surfaces replies/comments made to the author's own posts (and their own
-- posted replies) back in the dashboard feed, flagged and starred. The author
-- can then draft a response on demand through the existing pipeline.
-- ─────────────────────────────────────

-- Flags on conversations so a reply-to-me lands in the feed, visually distinct.
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'manual';
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS is_reply_to_me BOOLEAN DEFAULT false;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS parent_post_url TEXT;

-- Posts the author has published through the app (standalone posts and posted
-- replies). Polled periodically to detect new replies to them.
CREATE TABLE IF NOT EXISTS authored_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform TEXT NOT NULL,
    post_id TEXT NOT NULL,          -- at-uri (Bluesky) or status id (Mastodon)
    post_url TEXT,
    content TEXT,
    is_reply BOOLEAN DEFAULT false, -- true when this authored post is itself a reply
    created_at TIMESTAMPTZ DEFAULT now(),
    last_checked_at TIMESTAMPTZ,
    UNIQUE (platform, post_id)
);
CREATE INDEX IF NOT EXISTS authored_posts_platform_idx ON authored_posts (platform);
CREATE INDEX IF NOT EXISTS authored_posts_checked_idx ON authored_posts (last_checked_at);

-- Every reply we have already ingested, so polling never double-creates.
CREATE TABLE IF NOT EXISTS seen_replies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform TEXT NOT NULL,
    reply_id TEXT NOT NULL,
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (platform, reply_id)
);

CREATE INDEX IF NOT EXISTS conversations_reply_to_me_idx ON conversations (is_reply_to_me);
