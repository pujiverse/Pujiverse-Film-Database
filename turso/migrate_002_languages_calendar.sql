-- Run ONCE on databases created before the calendar / languages features (already applied to pujiverse-films):
alter table titles add column languages text;          -- spoken languages from TMDB, comma list
create index if not exists titles_release_idx on titles (release_date);
