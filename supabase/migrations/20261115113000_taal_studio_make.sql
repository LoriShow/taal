-- Taal Studio step 2: make a draft into a real song, make its play-along video, list a family's songs.
-- Same pattern as step 1: the page calls these with the family's studio code; nothing else is exposed.
-- Progress is kept inside the draft record: draft->'make' and draft->'video'.

create function public.taal_studio_make(code text, draft_id uuid, words jsonb default '{}'::jsonb)
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
  fam uuid;
  d jsonb;
  lines jsonb;
  made_today int;
begin
  fam := public.taal_studio_family(code);
  if fam is null then raise exception 'unknown studio code'; end if;
  select s.draft into d from public.taal_studio_drafts s
   where s.id = draft_id and s.family_id = fam and s.status = 'ready';
  if d is null then raise exception 'that draft is not ready'; end if;
  if coalesce(d->'make'->>'status', '') in ('queued', 'made') then
    return d->'make'->>'status';
  end if;
  select count(*) into made_today from public.taal_studio_drafts s
   where s.family_id = fam
     and s.draft->'make'->>'status' in ('queued', 'made')
     and (s.draft->'make'->>'at')::timestamptz > now() - interval '1 day';
  if made_today >= 10 then raise exception 'that is 10 songs today; make more tomorrow'; end if;

  -- The family's edited words, if any: up to 4 lines of up to 40 characters each.
  lines := (select coalesce(jsonb_agg(left(btrim(x), 40)), '[]'::jsonb)
              from (select x from jsonb_array_elements_text(coalesce(words->'listen', '[]'::jsonb)) x
                     where btrim(x) <> '' limit 4) t);
  if jsonb_array_length(lines) > 0 then d := jsonb_set(d, '{plan,sections,1,lines}', lines); end if;
  lines := (select coalesce(jsonb_agg(left(btrim(x), 40)), '[]'::jsonb)
              from (select x from jsonb_array_elements_text(coalesce(words->'together', '[]'::jsonb)) x
                     where btrim(x) <> '' limit 4) t);
  if jsonb_array_length(lines) > 0 then d := jsonb_set(d, '{plan,sections,3,lines}', lines); end if;

  d := jsonb_set(d, '{make}', jsonb_build_object('status', 'queued', 'at', now()));
  update public.taal_studio_drafts s set draft = d, updated_at = now() where s.id = draft_id;
  insert into public.taal_jobs (type, payload) values ('make_song', jsonb_build_object('draft_id', draft_id));
  return 'queued';
end;
$$;
revoke execute on function public.taal_studio_make(text, uuid, jsonb) from public;
grant execute on function public.taal_studio_make(text, uuid, jsonb) to anon, authenticated;

create function public.taal_studio_video(code text, draft_id uuid)
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
  fam uuid;
  d jsonb;
begin
  fam := public.taal_studio_family(code);
  if fam is null then raise exception 'unknown studio code'; end if;
  select s.draft into d from public.taal_studio_drafts s where s.id = draft_id and s.family_id = fam;
  if d is null or d->'make'->>'status' <> 'made' then raise exception 'make the song first'; end if;
  if coalesce(d->'video'->>'status', '') in ('queued', 'made') then return d->'video'->>'status'; end if;
  update public.taal_studio_drafts s
     set draft = jsonb_set(s.draft, '{video}', jsonb_build_object('status', 'queued', 'at', now())), updated_at = now()
   where s.id = draft_id;
  insert into public.taal_jobs (type, song_id, payload)
  values ('render_video', (d->'make'->>'song_id')::uuid, jsonb_build_object('draft_id', draft_id));
  return 'queued';
end;
$$;
revoke execute on function public.taal_studio_video(text, uuid) from public;
grant execute on function public.taal_studio_video(text, uuid) to anon, authenticated;

create function public.taal_studio_list(code text)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select coalesce(jsonb_agg(x order by x->>'created_at' desc), '[]'::jsonb)
    from (
      select jsonb_build_object('id', d.id, 'created_at', d.created_at, 'title', d.draft->>'title',
                                'make', d.draft->'make', 'video', d.draft->'video') x
        from public.taal_studio_drafts d
       where d.family_id = public.taal_studio_family(code)
         and d.draft->'make'->>'status' = 'made'
       order by d.created_at desc
       limit 30
    ) t
$$;
revoke execute on function public.taal_studio_list(text) from public;
grant execute on function public.taal_studio_list(text) to anon, authenticated;
