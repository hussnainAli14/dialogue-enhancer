-- Favour posts that already have an audience: an engagement floor, an
-- engagement ranking weight, and a wider lookback window so posts have time to
-- gain traction. All runtime-editable via discovery_settings.

alter table discovery_settings
  add column if not exists min_engagement_score     numeric not null default 0.0,
  add column if not exists engagement_weight        numeric not null default 0.3,
  add column if not exists discovery_lookback_hours integer not null default 72;
