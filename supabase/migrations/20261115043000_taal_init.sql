-- Taal: first schema. Families see only their own rows; the worker uses the service key.

create table public.taal_families (
  id uuid primary key default gen_random_uuid(),
  owner uuid not null unique references auth.users (id) on delete cascade,
  name text not null,
  created_at timestamptz not null default now()
);

create table public.taal_children (
  id uuid primary key default gen_random_uuid(),
  family_id uuid not null references public.taal_families (id) on delete cascade,
  name text not null,
  birth_year int,
  -- A parent or guardian must confirm before a child is added.
  consent boolean not null check (consent),
  consent_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);
create index taal_children_family_idx on public.taal_children (family_id);

create table public.taal_links (
  id uuid primary key default gen_random_uuid(),
  family_id uuid not null references public.taal_families (id) on delete cascade,
  url text not null,
  who text not null check (who in ('kid', 'father', 'mother', 'other')),
  -- Title and channel only. The audio is never fetched.
  title text,
  channel text,
  traits jsonb,
  created_at timestamptz not null default now()
);
create index taal_links_family_idx on public.taal_links (family_id);

create table public.taal_soundcards (
  id uuid primary key default gen_random_uuid(),
  family_id uuid not null references public.taal_families (id) on delete cascade,
  weights jsonb not null default '{}'::jsonb,
  traits jsonb not null default '{}'::jsonb,
  confirmed_at timestamptz,
  created_at timestamptz not null default now()
);
create index taal_soundcards_family_idx on public.taal_soundcards (family_id);

create table public.taal_themes (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  name text not null,
  description text,
  assets jsonb not null default '{}'::jsonb,
  status text not null default 'draft' check (status in ('draft', 'ready', 'retired')),
  created_at timestamptz not null default now()
);

create table public.taal_songs (
  id uuid primary key default gen_random_uuid(),
  family_id uuid not null references public.taal_families (id) on delete cascade,
  soundcard_id uuid references public.taal_soundcards (id) on delete set null,
  theme_id uuid references public.taal_themes (id) on delete set null,
  level int not null default 1 check (level between 1 and 4),
  title text,
  language text,
  tune jsonb,
  plan jsonb,
  lyrics text,
  checks jsonb,
  status text not null default 'draft'
    check (status in ('draft', 'checked', 'audio', 'film', 'ready', 'failed')),
  audio_path text,
  film_path text,
  beat_grid jsonb,
  created_at timestamptz not null default now()
);
create index taal_songs_family_idx on public.taal_songs (family_id);
create index taal_songs_soundcard_idx on public.taal_songs (soundcard_id);
create index taal_songs_theme_idx on public.taal_songs (theme_id);

create table public.taal_jobs (
  id uuid primary key default gen_random_uuid(),
  type text not null,
  song_id uuid references public.taal_songs (id) on delete cascade,
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'queued'
    check (status in ('queued', 'running', 'done', 'failed')),
  attempts int not null default 0,
  result jsonb,
  error text,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz
);
create index taal_jobs_queue_idx on public.taal_jobs (created_at) where status = 'queued';
create index taal_jobs_song_idx on public.taal_jobs (song_id);

create table public.taal_costs (
  id uuid primary key default gen_random_uuid(),
  job_id uuid references public.taal_jobs (id) on delete set null,
  song_id uuid references public.taal_songs (id) on delete set null,
  provider text not null,
  units numeric not null,
  unit text not null,
  amount_usd numeric,
  created_at timestamptz not null default now()
);
create index taal_costs_job_idx on public.taal_costs (job_id);
create index taal_costs_song_idx on public.taal_costs (song_id);

-- Row-level security -------------------------------------------------------

alter table public.taal_families enable row level security;
alter table public.taal_children enable row level security;
alter table public.taal_links enable row level security;
alter table public.taal_soundcards enable row level security;
alter table public.taal_themes enable row level security;
alter table public.taal_songs enable row level security;
alter table public.taal_jobs enable row level security;
alter table public.taal_costs enable row level security;

create policy taal_families_own on public.taal_families
  for all to authenticated
  using (owner = (select auth.uid()))
  with check (owner = (select auth.uid()));

create policy taal_children_own on public.taal_children
  for all to authenticated
  using (family_id in (select id from public.taal_families where owner = (select auth.uid())))
  with check (family_id in (select id from public.taal_families where owner = (select auth.uid())));

create policy taal_links_own on public.taal_links
  for all to authenticated
  using (family_id in (select id from public.taal_families where owner = (select auth.uid())))
  with check (family_id in (select id from public.taal_families where owner = (select auth.uid())));

create policy taal_soundcards_own on public.taal_soundcards
  for all to authenticated
  using (family_id in (select id from public.taal_families where owner = (select auth.uid())))
  with check (family_id in (select id from public.taal_families where owner = (select auth.uid())));

-- Families can read their songs; only the worker writes them.
create policy taal_songs_read_own on public.taal_songs
  for select to authenticated
  using (family_id in (select id from public.taal_families where owner = (select auth.uid())));

create policy taal_themes_read_ready on public.taal_themes
  for select to anon, authenticated
  using (status = 'ready');

-- taal_jobs and taal_costs have no policies: only the service key can touch them.

-- Job queue ----------------------------------------------------------------

create function public.taal_claim_job()
returns setof public.taal_jobs
language plpgsql
set search_path = ''
as $$
begin
  return query
  update public.taal_jobs j
     set status = 'running',
         attempts = j.attempts + 1,
         started_at = now()
   where j.id = (
     select q.id
       from public.taal_jobs q
      where q.status = 'queued'
      order by q.created_at
      limit 1
      for update skip locked
   )
  returning j.*;
end;
$$;

revoke execute on function public.taal_claim_job() from public, anon, authenticated;
grant execute on function public.taal_claim_job() to service_role;

-- Private file storage for audio and films ---------------------------------

insert into storage.buckets (id, name, public)
values ('taal', 'taal', false)
on conflict (id) do nothing;

-- Files live under <family_id>/...; a family can read only its own folder.
create policy taal_files_read_own on storage.objects
  for select to authenticated
  using (
    bucket_id = 'taal'
    and (storage.foldername(name))[1] in (
      select id::text from public.taal_families where owner = (select auth.uid())
    )
  );
