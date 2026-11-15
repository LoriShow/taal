-- Progress and rewards: one row each time a child plays a song through to the end.
-- A family sees and adds only its own rows; nobody edits history.

create table public.taal_plays (
  id          uuid primary key default gen_random_uuid(),
  family_id   uuid not null references public.taal_families (id) on delete cascade,
  child_id    uuid not null references public.taal_children (id) on delete cascade,
  song_id     uuid references public.taal_songs (id) on delete set null,
  song_level  integer check (song_level between 1 and 4),
  instrument  text not null default 'keys' check (instrument in ('keys', 'lyre', 'piano', 'xylo', 'uke')),
  turn_notes  integer not null check (turn_notes between 0 and 500),
  hits        integer not null check (hits between 0 and 500),
  stars       smallint not null check (stars between 1 and 3),
  seconds     integer not null check (seconds between 0 and 3600),
  created_at  timestamptz not null default now(),
  check (hits <= turn_notes)
);
create index taal_plays_child_idx on public.taal_plays (child_id, created_at desc);
create index taal_plays_family_idx on public.taal_plays (family_id, created_at desc);
create index taal_plays_song_idx on public.taal_plays (song_id);

alter table public.taal_plays enable row level security;

create policy taal_plays_read_own on public.taal_plays
  for select to authenticated
  using (family_id in (select id from public.taal_families where owner = (select auth.uid())));

create policy taal_plays_add_own on public.taal_plays
  for insert to authenticated
  with check (
    family_id in (select id from public.taal_families where owner = (select auth.uid()))
    and child_id in (select c.id from public.taal_children c where c.family_id = taal_plays.family_id)
  );
