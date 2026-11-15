-- Songs can belong to an album, in track order.
alter table public.taal_songs
  add column album text,
  add column track int;
create unique index taal_songs_album_track_idx on public.taal_songs (album, track) where album is not null;
