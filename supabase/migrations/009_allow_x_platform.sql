-- Allow the 'x' (Twitter) platform in platform_connections. The original CHECK
-- constraint (migration 002) predates the X connector, so connecting X failed
-- with a check-constraint violation until 'x' was added.

alter table platform_connections
  drop constraint if exists platform_connections_platform_check;

alter table platform_connections
  add constraint platform_connections_platform_check
  check (platform in ('reddit','bluesky','mastodon','discord','telegram','threads','youtube','x'));
