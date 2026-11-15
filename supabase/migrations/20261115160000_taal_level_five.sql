-- Level 5: all eight notes, C4 to C5 (album five, The Whole Ladder).
alter table public.taal_songs drop constraint taal_songs_level_check;
alter table public.taal_songs add constraint taal_songs_level_check check (level between 1 and 5);
alter table public.taal_plays drop constraint taal_plays_song_level_check;
alter table public.taal_plays add constraint taal_plays_song_level_check check (song_level between 1 and 5);
