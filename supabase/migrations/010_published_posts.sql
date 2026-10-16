-- Posted-history support.
-- 1) Record standalone posts published from Compose (previously not stored at
--    all — create_post published and forgot them).
-- 2) Keep the live URL of a posted reply so the history can link to it.

create table if not exists published_posts (
  id uuid primary key default gen_random_uuid(),
  platform text not null,
  content text,
  post_url text,
  created_at timestamptz not null default now()
);

create index if not exists published_posts_created_at_idx
  on published_posts (created_at desc);

alter table response_drafts
  add column if not exists posted_url text;
