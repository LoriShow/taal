-- What the public site needs: sample songs anyone can play, and automatic photo reading.

alter table public.taal_songs
  add column is_sample boolean not null default false,
  add column sample_audio_path text;

-- Anyone can read a song that has been published as a sample.
create policy taal_songs_read_samples on public.taal_songs
  for select to anon, authenticated
  using (is_sample);

-- Public files: sample audio only. Family files stay in the private 'taal' bucket.
insert into storage.buckets (id, name, public)
values ('taal-public', 'taal-public', true)
on conflict (id) do nothing;

-- When a family adds an instrument photo, queue the reading job for the worker.
create function public.taal_queue_read_instrument()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.taal_jobs (type, payload)
  values ('read_instrument', jsonb_build_object('instrument_id', new.id));
  return new;
end;
$$;

revoke execute on function public.taal_queue_read_instrument() from public, anon, authenticated;

create trigger taal_instruments_queue_read
  after insert on public.taal_instruments
  for each row execute function public.taal_queue_read_instrument();
