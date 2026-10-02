-- Pujiverse Film Database — Turso (SQLite/libSQL) catalog schema
-- New database: run this file, then seed_industries.sql, then load data with pipeline/load_to_turso.py

CREATE TABLE industries (slug text primary key, name text not null, language_code text, region text, description text, sort_order int);

CREATE TABLE industry_year_stats (industry text not null, kind text not null, year int not null, films int not null, streaming int not null,
  primary key (industry, kind, year));

CREATE TABLE titles (title_id text primary key, title, title_local, title_telugu, original_title, industry, language, type, status, release_date, year, genre, runtime_min, director, "cast_names", production, overview, poster_url, tmdb_rating, tmdb_votes, rating_display, streaming_in, streaming_us, rent_buy_us, watch_link_in, watch_link_us, imdb_id, tmdb_id, wikidata_id, wikipedia_url, source, seasons, episodes, network, last_air_date, series_status, creators, tmdb_checked_at);

CREATE VIRTUAL TABLE titles_fts using fts5(title, title_local, title_telugu, original_title, director, cast_names,
  content='titles', content_rowid='rowid', tokenize='unicode61 remove_diacritics 2');

CREATE INDEX titles_browse_idx on titles (industry, type, year, release_date);

CREATE INDEX titles_tmdb_idx on titles (tmdb_id);

CREATE INDEX titles_year_idx on titles (industry, year);

-- keep full-text search in sync automatically (external-content FTS5)
create trigger titles_ai after insert on titles begin
  insert into titles_fts(rowid, title, title_local, title_telugu, original_title, director, cast_names)
  values (new.rowid, new.title, new.title_local, new.title_telugu, new.original_title, new.director, new.cast_names);
end;
create trigger titles_ad after delete on titles begin
  insert into titles_fts(titles_fts, rowid, title, title_local, title_telugu, original_title, director, cast_names)
  values ('delete', old.rowid, old.title, old.title_local, old.title_telugu, old.original_title, old.director, old.cast_names);
end;
create trigger titles_au after update of title, title_local, title_telugu, original_title, director, cast_names on titles begin
  insert into titles_fts(titles_fts, rowid, title, title_local, title_telugu, original_title, director, cast_names)
  values ('delete', old.rowid, old.title, old.title_local, old.title_telugu, old.original_title, old.director, old.cast_names);
  insert into titles_fts(rowid, title, title_local, title_telugu, original_title, director, cast_names)
  values (new.rowid, new.title, new.title_local, new.title_telugu, new.original_title, new.director, new.cast_names);
end;

-- lets the TMDB step find unprocessed titles quickly (newest first)
create index if not exists titles_tmdb_todo_idx on titles (year desc) where tmdb_checked_at is null;
