-- Pujiverse Film Database — Supabase / Postgres schema
-- Run once in the Supabase SQL editor on a new project, then run seed_industries.sql.

create extension if not exists pg_trgm with schema extensions;

-- ---------------------------------------------------------------- tables
create table public.industries (
  slug text primary key,
  name text not null,
  language_code text,
  region text,
  description text,
  sort_order int default 0,
  expected_films int
);

create table public.titles (
  title_id text primary key,                 -- "<industry>-<wikidata QID>" or "<industry>-wp-<year>-<slug>"
  title text not null,
  title_telugu text,
  original_title text,
  english_title_wikipedia text,
  industry text not null references public.industries(slug),
  language text,
  type text not null default 'movie'
    check (type in ('movie','short','animated','tv','anime','tv_film','documentary')),
  status text default 'released' check (status in ('released','upcoming','unknown')),
  release_date date,                          -- only set when the exact day is known
  year int,
  genre text,
  runtime_min int,
  director text,
  "cast" text,
  production text,
  overview text,
  poster_url text,
  tmdb_rating numeric(4,2),
  tmdb_votes int,
  rating_display numeric(4,2),                -- TMDB rating, only when tmdb_votes >= 10
  streaming_in text,
  streaming_us text,
  rent_buy_us text,
  imdb_id text,
  tmdb_id int,
  wikidata_id text,
  wikidata_url text,
  wikipedia_url text,
  source text,                                -- wikidata | wikipedia | wikidata+wikipedia
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  title_local text,                           -- title in the original script
  user_rating_avg numeric(3,1),               -- maintained by trigger
  user_story_avg numeric(3,1),
  user_rating_count int not null default 0,
  watch_link_in text,                         -- TMDB/JustWatch where-to-watch page (India)
  watch_link_us text,
  tmdb_checked_at timestamptz                 -- set once the TMDB step has looked at this film
);

create table public.user_ratings (
  id bigint generated always as identity primary key,
  title_id text not null references public.titles(title_id) on delete cascade,
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  story_rating smallint check (story_rating between 1 and 10),
  overall_rating smallint not null check (overall_rating between 1 and 10),
  review text check (char_length(review) <= 2000),
  created_at timestamptz default now(),
  unique (title_id, user_id)
);

create table public.duplicate_reports (
  id bigint generated always as identity primary key,
  title_id text not null references public.titles(title_id) on delete cascade,
  duplicate_of text references public.titles(title_id) on delete cascade,
  note text check (char_length(note) <= 500),
  reported_by uuid default auth.uid() references auth.users(id) on delete set null,
  resolved boolean default false,
  created_at timestamptz default now()
);

-- ---------------------------------------------------------------- indexes
create index titles_industry_year_idx    on public.titles (industry, year);
create index titles_ind_year_date_idx    on public.titles (industry, year, release_date);
create index titles_ind_title_idx        on public.titles (industry, title);
create index titles_year_idx             on public.titles (year);
create index titles_tmdb_idx             on public.titles (tmdb_id);
create index titles_title_trgm_idx       on public.titles using gin (title extensions.gin_trgm_ops);
create index titles_local_trgm_idx       on public.titles using gin (title_local extensions.gin_trgm_ops);
create index titles_orig_trgm_idx        on public.titles using gin (original_title extensions.gin_trgm_ops);
create index titles_te_trgm_idx          on public.titles using gin (title_telugu extensions.gin_trgm_ops);
create index titles_director_trgm_idx    on public.titles using gin (director extensions.gin_trgm_ops);
create index titles_cast_trgm_idx        on public.titles using gin ("cast" extensions.gin_trgm_ops);
create index titles_todo_year_idx on public.titles (year desc nulls last) where tmdb_checked_at is null;
create index user_ratings_title_idx      on public.user_ratings (title_id);

-- ---------------------------------------------------------------- row level security
alter table public.industries        enable row level security;
alter table public.titles            enable row level security;
alter table public.user_ratings      enable row level security;
alter table public.duplicate_reports enable row level security;

create policy "public read industries" on public.industries for select to anon, authenticated using (true);
create policy "public read titles"     on public.titles     for select to anon, authenticated using (true);
create policy "public read ratings"    on public.user_ratings for select to anon, authenticated using (true);
create policy "users add own rating"    on public.user_ratings for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "users edit own rating"   on public.user_ratings for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "users delete own rating" on public.user_ratings for delete to authenticated using ((select auth.uid()) = user_id);
create policy "users report duplicates" on public.duplicate_reports for insert to authenticated with check ((select auth.uid()) = reported_by);

-- ---------------------------------------------------------------- rating summary trigger
create or replace function public.refresh_title_rating() returns trigger
language plpgsql security definer set search_path = public as $$
declare tid text := coalesce(new.title_id, old.title_id);
begin
  update public.titles t set user_rating_avg = s.a, user_story_avg = s.st, user_rating_count = s.n
  from (select round(avg(overall_rating)::numeric,1) a, round(avg(story_rating)::numeric,1) st, count(*)::int n
        from public.user_ratings where title_id = tid) s
  where t.title_id = tid;
  return null;
end $$;
revoke execute on function public.refresh_title_rating() from public, anon, authenticated;
create trigger user_ratings_refresh after insert or update or delete on public.user_ratings
  for each row execute function public.refresh_title_rating();

-- ---------------------------------------------------------------- views
create view public.titles_with_ratings with (security_invoker = true) as select * from public.titles;

-- year counts are precomputed (fast at 300k+ films); refresh after every upload
create table public.industry_year_stats (
  industry text not null references public.industries(slug) on delete cascade,
  year int not null, films int not null, streaming int not null,
  primary key (industry, year)
);
alter table public.industry_year_stats enable row level security;
create policy "public read year stats" on public.industry_year_stats for select to anon, authenticated using (true);

create or replace function public.refresh_year_stats() returns void
language sql security definer set search_path = public as $$
  delete from public.industry_year_stats where true;
  insert into public.industry_year_stats (industry, year, films, streaming)
  select industry, year, count(*)::int,
         count(*) filter (where streaming_in is not null or streaming_us is not null)::int
  from public.titles where year is not null group by industry, year;
$$;
revoke execute on function public.refresh_year_stats() from public, anon, authenticated;
grant execute on function public.refresh_year_stats() to service_role;

-- web series support: type 'series' plus series columns, and per-kind stats
-- (schema already allows these via the columns/check above when you apply migrations in order)
create or replace function public.refresh_industry_stats(p_industry text) returns void
language sql security definer set search_path = public as $$
  delete from public.industry_year_stats where industry = p_industry;
  insert into public.industry_year_stats (industry, kind, year, films, streaming)
  select industry, case when type = 'series' then 'series' else 'film' end, year, count(*)::int,
         count(*) filter (where streaming_in is not null or streaming_us is not null)::int
  from public.titles where industry = p_industry and year is not null group by 1, 2, 3;
$$;
revoke execute on function public.refresh_industry_stats(text) from public, anon, authenticated;
grant execute on function public.refresh_industry_stats(text) to service_role;

create view public.year_counts with (security_invoker = true) as
  select industry, year, films, streaming from public.industry_year_stats;

create view public.industry_overview with (security_invoker = true) as
select i.slug, i.name, i.region, i.description, i.sort_order, i.expected_films,
       coalesce(s.films_loaded, 0) as films_loaded, s.first_year, s.last_year, s.spark
from public.industries i
left join (
  select industry, sum(films)::int as films_loaded, min(year) as first_year, max(year) as last_year,
         json_agg(json_build_array(year, films) order by year) as spark
  from public.industry_year_stats group by industry
) s on s.industry = i.slug;

-- ---------------------------------------------------------------- ranked search
create or replace function public.search_titles(
  q text, p_industry text default null, y_from int default null, y_to int default null,
  p_sort text default 'relevance', lim int default 50, off int default 0)
returns table (title_id text, title text, title_local text, title_telugu text, industry text, year int,
  release_date date, genre text, director text, poster_url text, rating_display numeric,
  streaming_in text, streaming_us text, user_rating_avg numeric, user_rating_count int,
  match_field text, rank int)
language sql stable security invoker set search_path = public, extensions as $$
  with term as (select lower(trim(q)) as t),
  hits as (
    select x.*,
      case
        when lower(x.title) = (select t from term) or lower(coalesce(x.title_local,'')) = (select t from term)
             or lower(coalesce(x.title_telugu,'')) = (select t from term) or lower(coalesce(x.original_title,'')) = (select t from term) then 1
        when lower(x.title) like (select t from term) || '%' or lower(coalesce(x.title_local,'')) like (select t from term) || '%' then 2
        when x.title ilike '%' || (select t from term) || '%' or coalesce(x.title_local,'') ilike '%' || (select t from term) || '%'
             or coalesce(x.title_telugu,'') ilike '%' || (select t from term) || '%' or coalesce(x.original_title,'') ilike '%' || (select t from term) || '%' then 3
        when x.director ilike '%' || (select t from term) || '%' then 4
        else 5 end as rank,
      coalesce(x.tmdb_votes,0) * 10 + coalesce(x.user_rating_count,0) * 20
        + length(coalesce(x."cast",'')) / 15 + (case when x.director is not null then 5 else 0 end)
        + (case when x.poster_url is not null then 20 else 0 end) as pop
    from public.titles x
    where length(trim(q)) >= 2
      and (x.title ilike '%' || trim(q) || '%' or x.title_local ilike '%' || trim(q) || '%'
           or x.title_telugu ilike '%' || trim(q) || '%' or x.original_title ilike '%' || trim(q) || '%'
           or x.director ilike '%' || trim(q) || '%' or x."cast" ilike '%' || trim(q) || '%')
      and (p_industry is null or x.industry = p_industry)
      and (y_from is null or x.year >= y_from)
      and (y_to is null or x.year <= y_to)
  )
  select h.title_id, h.title, h.title_local, h.title_telugu, h.industry, h.year, h.release_date, h.genre, h.director,
         h.poster_url, h.rating_display, h.streaming_in, h.streaming_us, h.user_rating_avg, h.user_rating_count,
         case h.rank when 4 then 'director' when 5 then 'cast' else 'title' end, h.rank
  from hits h
  order by
    case when p_sort = 'relevance' then h.rank end,
    case when p_sort = 'relevance' then h.pop end desc,
    case when p_sort = 'rating' then coalesce(h.user_rating_avg, h.rating_display) end desc nulls last,
    case when p_sort = 'newest' then h.year end desc nulls last,
    case when p_sort = 'oldest' then h.year end asc nulls last,
    case when p_sort = 'title' then lower(h.title) end,
    h.pop desc, h.year desc nulls last, h.title
  limit least(lim, 200) offset off;
$$;
grant execute on function public.search_titles(text,text,int,int,text,int,int) to anon, authenticated;

-- ---------------------------------------------------------------- TMDB enrichment (pipeline only, service role)
create or replace function public.apply_tmdb_enrichment(rows jsonb)
returns int language plpgsql security definer set search_path = public as $$
declare n int;
begin
  update public.titles t set
    tmdb_id = coalesce(r.tmdb_id, t.tmdb_id), overview = coalesce(r.overview, t.overview),
    poster_url = coalesce(r.poster_url, t.poster_url), tmdb_rating = coalesce(r.tmdb_rating, t.tmdb_rating),
    tmdb_votes = coalesce(r.tmdb_votes, t.tmdb_votes),
    rating_display = case when coalesce(r.tmdb_votes, t.tmdb_votes, 0) >= 10 then coalesce(r.tmdb_rating, t.tmdb_rating) else t.rating_display end,
    streaming_in = coalesce(r.streaming_in, t.streaming_in), streaming_us = coalesce(r.streaming_us, t.streaming_us),
    rent_buy_us = coalesce(r.rent_buy_us, t.rent_buy_us),
    watch_link_in = coalesce(r.watch_link_in, t.watch_link_in), watch_link_us = coalesce(r.watch_link_us, t.watch_link_us),
    runtime_min = coalesce(t.runtime_min, r.runtime_min), release_date = coalesce(t.release_date, r.release_date),
    imdb_id = coalesce(t.imdb_id, r.imdb_id), tmdb_checked_at = now(), updated_at = now()
  from jsonb_to_recordset(rows) as r(title_id text, tmdb_id int, overview text, poster_url text, tmdb_rating numeric,
       tmdb_votes int, streaming_in text, streaming_us text, rent_buy_us text, watch_link_in text, watch_link_us text,
       runtime_min int, release_date date, imdb_id text)
  where t.title_id = r.title_id;
  get diagnostics n = row_count;
  return n;
end $$;
revoke execute on function public.apply_tmdb_enrichment(jsonb) from public, anon, authenticated;
grant execute on function public.apply_tmdb_enrichment(jsonb) to service_role;
