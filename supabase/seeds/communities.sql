-- ═══════════════════════════════════════
-- Module 4 — starter monitored communities
-- Run after migration 003. Safe to re-run (ON CONFLICT DO NOTHING).
-- ═══════════════════════════════════════

INSERT INTO monitored_communities (platform, community_id, community_name, keywords, priority)
VALUES
    -- Reddit (community_id = subreddit name)
    ('reddit', 'leadership', 'r/leadership',
        ARRAY['leadership','coaching','management','team dynamics','accountability'], 3),
    ('reddit', 'personaldevelopment', 'r/personaldevelopment',
        ARRAY['personal growth','habits','mindset','self improvement'], 2),
    ('reddit', 'psychology', 'r/psychology',
        ARRAY['behaviour','motivation','relationships','community'], 2),
    ('reddit', 'Entrepreneur', 'r/Entrepreneur',
        ARRAY['leadership','culture','team','coaching'], 1),

    -- Bluesky (community_id = keyword/hashtag)
    ('bluesky', 'leadership', 'leadership', ARRAY['leadership'], 2),
    ('bluesky', 'coaching', 'coaching', ARRAY['coaching'], 2),
    ('bluesky', 'personalgrowth', 'personalgrowth', ARRAY['personal growth'], 2),
    ('bluesky', 'community', 'community', ARRAY['community'], 1),

    -- Mastodon (community_id = hashtag)
    ('mastodon', 'leadership', '#leadership', ARRAY['leadership'], 2),
    ('mastodon', 'coaching', '#coaching', ARRAY['coaching'], 2),
    ('mastodon', 'personaldevelopment', '#personaldevelopment', ARRAY['personal development'], 2),

    -- YouTube (keywords only, no specific channel)
    ('youtube', 'leadership coaching', 'Leadership Coaching (search)',
        ARRAY['leadership coaching','personal growth','community building','executive coaching'], 1)

ON CONFLICT (platform, community_id) DO NOTHING;
