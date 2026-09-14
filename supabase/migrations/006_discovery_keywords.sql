-- Module: knowledge-base-driven discovery keywords
-- Keywords extracted from the knowledge base (source='kb') plus any the user
-- adds by hand (source='manual'). Discovery searches every connected platform
-- using the ACTIVE keywords, capped in code. Users can activate/deactivate and
-- delete keywords; deactivated/deleted keywords are respected on re-scan.

create table if not exists discovery_keywords (
  id           uuid primary key default gen_random_uuid(),
  keyword      text not null,
  normalized   text not null unique,
  source       text not null default 'kb' check (source in ('kb', 'manual')),
  is_active    boolean not null default true,
  document_id  uuid references documents(id) on delete set null,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create index if not exists idx_discovery_keywords_active
  on discovery_keywords (is_active);
