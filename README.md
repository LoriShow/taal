# Taal

A kids' music platform, sister to Lori. A family's music taste becomes original songs
with animated films that teach the child and parents to play together.

## Layout

- `worker/` — Python job runner (Railway service `taal-worker`, root directory `/worker`).
- `supabase/migrations/` — database schema (Supabase project `taal`).
- `web/` — the site: static HTML, CSS and JS served by nginx (Railway service `taal-web`, root directory `/web`). Home page, song player, and the family area (sign-in, links, instrument photos). `config.js` holds public values only.

## Rules that shape the code

1. **Links are taste signals, not source material.** No YouTube audio is downloaded,
   analysed or remade. Only titles are read, and only abstract traits reach the
   music generator: never an artist, band or song name.
2. **The child's tune is exact.** It is written as notes (`tune`), checked by
   `taal_worker/tune.py`, and rendered with a sampled instrument. ElevenLabs Music
   only makes the backing track.
3. **Audio first.** Sections are whole bars, so the timeline in `taal_worker/plan.py`
   drives the film cuts and the play-along.
4. **Every song waits for the child.** A plan without a `turn` section fails its check.

## Worker

Job types so far:

| Type | Does |
|---|---|
| `import_asset` | Copies an image made on Higgsfield (cover, theme) into the public bucket |
| `load_album` | Creates an album's songs from `taal_worker/content/<album>.json` and takes each to a published sample |
| `ping` | Proves the queue works end to end |
| `read_instrument` | Reads a family's instrument photo with Claude: what it is, its layout, and whether its notes are known |
| `check_song` | Runs the tune and plan rules on a draft song; marks it `checked` |
| `publish_sample` | Copies a song's audio to the public bucket so anyone can play it on the site |
| `backing_track` | Generates the backing track with ElevenLabs Music and stores it |

Queue a job by inserting a row in `taal_jobs` (`type`, `song_id`). `read_instrument` takes
`payload.instrument_id` instead.

A photo cannot show tuning. Keyboards are `ready` from the photo; other pitched
instruments stay `needs_tuning` until their notes are measured (not built yet). A photo
with a person in it is marked `retake`.

Variables on `taal-worker`: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `ELEVENLABS_API_KEY`,
`ANTHROPIC_API_KEY`, `HIGGSFIELD_API_KEY`, `WOLFRAM_APP_ID`. No keys go in this repo.

Tests:

```
cd worker && pip install -r requirements.txt pytest && python -m pytest
```

## Provisional numbers

The tempo band (60-120 bpm) and the playability pass mark (60) in `tune.py` are our
own starting values. They are to be calibrated with real children.
