-- Run ONCE on the existing pujiverse-films database (it was imported before these existed):
--   turso db shell pujiverse-films < turso/migrate_001_sync_triggers.sql

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
