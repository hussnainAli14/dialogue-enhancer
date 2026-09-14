-- Make the keyword search cap and the knowledge-base blend weight runtime-editable
-- via discovery_settings (previously hardcoded).

alter table discovery_settings
  add column if not exists keyword_search_cap integer not null default 30,
  add column if not exists kb_overlap_weight   numeric not null default 0.25;
