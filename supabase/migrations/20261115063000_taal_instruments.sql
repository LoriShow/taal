-- A family's own instrument, read from a photo, so lessons fit what they own.

create table public.taal_instruments (
  id uuid primary key default gen_random_uuid(),
  family_id uuid not null references public.taal_families (id) on delete cascade,
  photo_path text not null,
  kind text,
  profile jsonb,
  -- The notes the instrument really plays, low to high. Empty until known.
  notes jsonb not null default '[]'::jsonb,
  status text not null default 'uploaded'
    check (status in ('uploaded', 'retake', 'needs_tuning', 'ready')),
  status_reason text,
  created_at timestamptz not null default now()
);
create index taal_instruments_family_idx on public.taal_instruments (family_id);

alter table public.taal_instruments enable row level security;

-- A family can see its instruments and add or remove one; only the worker fills in the reading.
create policy taal_instruments_read_own on public.taal_instruments
  for select to authenticated
  using (family_id in (select id from public.taal_families where owner = (select auth.uid())));

create policy taal_instruments_add_own on public.taal_instruments
  for insert to authenticated
  with check (
    family_id in (select id from public.taal_families where owner = (select auth.uid()))
    and status = 'uploaded' and profile is null and notes = '[]'::jsonb
    and photo_path like family_id::text || '/instruments/%'
  );

create policy taal_instruments_delete_own on public.taal_instruments
  for delete to authenticated
  using (family_id in (select id from public.taal_families where owner = (select auth.uid())));

alter table public.taal_songs
  add column instrument_id uuid references public.taal_instruments (id) on delete set null;
create index taal_songs_instrument_idx on public.taal_songs (instrument_id);

-- A family can upload instrument photos into its own folder, and remove them.
create policy taal_files_add_instrument_photo on storage.objects
  for insert to authenticated
  with check (
    bucket_id = 'taal'
    and (storage.foldername(name))[2] = 'instruments'
    and (storage.foldername(name))[1] in (
      select id::text from public.taal_families where owner = (select auth.uid())
    )
  );

create policy taal_files_delete_instrument_photo on storage.objects
  for delete to authenticated
  using (
    bucket_id = 'taal'
    and (storage.foldername(name))[2] = 'instruments'
    and (storage.foldername(name))[1] in (
      select id::text from public.taal_families where owner = (select auth.uid())
    )
  );
