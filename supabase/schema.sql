-- Pujiverse Film Database — Supabase schema (accounts and community data only)
-- The film/series catalog lives in Turso (see turso/schema.sql). title_id values match Turso's titles.title_id.

create table public.user_ratings (
  id bigint generated always as identity primary key,
  title_id text not null,                     -- Turso titles.title_id
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  story_rating smallint check (story_rating between 1 and 10),
  overall_rating smallint not null check (overall_rating between 1 and 10),
  review text check (char_length(review) <= 2000),
  created_at timestamptz default now(),
  unique (title_id, user_id)
);
create index user_ratings_title_idx on public.user_ratings (title_id);

create table public.duplicate_reports (
  id bigint generated always as identity primary key,
  title_id text not null,
  duplicate_of text,
  note text check (char_length(note) <= 500),
  reported_by uuid default auth.uid() references auth.users(id) on delete set null,
  resolved boolean default false,
  created_at timestamptz default now()
);

alter table public.user_ratings      enable row level security;
alter table public.duplicate_reports enable row level security;

create policy "public read ratings"     on public.user_ratings for select to anon, authenticated using (true);
create policy "users add own rating"    on public.user_ratings for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "users edit own rating"   on public.user_ratings for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "users delete own rating" on public.user_ratings for delete to authenticated using ((select auth.uid()) = user_id);
create policy "users report duplicates" on public.duplicate_reports for insert to authenticated with check ((select auth.uid()) = reported_by);
