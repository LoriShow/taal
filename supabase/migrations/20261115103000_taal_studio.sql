-- Taal Studio (early test): parents describe a song; the worker writes a draft.
-- Access is by a studio code per family until sign-in is switched on. Codes are stored
-- only as SHA-256 hashes. Drafts and codes are never readable directly by the browser:
-- the page goes through two functions that check the code first.

create extension if not exists pgcrypto with schema extensions;

create table public.taal_studio_keys (
  code_hash  text primary key,
  family_id  uuid not null references public.taal_families (id) on delete cascade,
  label      text,
  active     boolean not null default true,
  created_at timestamptz not null default now()
);
alter table public.taal_studio_keys enable row level security;

create table public.taal_studio_drafts (
  id         uuid primary key default gen_random_uuid(),
  family_id  uuid not null references public.taal_families (id) on delete cascade,
  brief      jsonb not null,
  status     text not null default 'queued' check (status in ('queued', 'writing', 'ready', 'failed')),
  draft      jsonb,
  error      text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index taal_studio_drafts_family_idx on public.taal_studio_drafts (family_id, created_at desc);
alter table public.taal_studio_drafts enable row level security;

create function public.taal_studio_family(code text)
returns uuid
language sql
stable
security definer
set search_path = ''
as $$
  select k.family_id
    from public.taal_studio_keys k
   where k.active
     and k.code_hash = encode(extensions.digest(code, 'sha256'), 'hex')
$$;
revoke execute on function public.taal_studio_family(text) from public, anon, authenticated;

create function public.taal_studio_request(code text, brief jsonb)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  fam uuid;
  did uuid;
begin
  fam := public.taal_studio_family(code);
  if fam is null then
    raise exception 'unknown studio code';
  end if;
  if pg_column_size(brief) > 4000 then
    raise exception 'that description is too long';
  end if;
  if (select count(*) from public.taal_studio_drafts d
       where d.family_id = fam and d.created_at > now() - interval '1 hour') >= 30 then
    raise exception 'that is a lot of songs for one hour; try again a bit later';
  end if;
  insert into public.taal_studio_drafts (family_id, brief) values (fam, brief) returning id into did;
  insert into public.taal_jobs (type, payload) values ('write_song', jsonb_build_object('draft_id', did));
  return did;
end;
$$;
revoke execute on function public.taal_studio_request(text, jsonb) from public;
grant execute on function public.taal_studio_request(text, jsonb) to anon, authenticated;

create function public.taal_studio_get(code text, draft_id uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object('id', d.id, 'status', d.status, 'draft', d.draft, 'error', d.error, 'brief', d.brief)
    from public.taal_studio_drafts d
   where d.id = draft_id
     and d.family_id = public.taal_studio_family(code)
$$;
revoke execute on function public.taal_studio_get(text, uuid) from public;
grant execute on function public.taal_studio_get(text, uuid) to anon, authenticated;
