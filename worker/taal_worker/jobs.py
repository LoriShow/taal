"""What the worker can do so far. Each handler takes (db, job) and returns a result dict."""

from __future__ import annotations

import json
import pathlib

from . import instrument as instrument_mod
from . import music
from . import plan as plan_mod
from . import tune as tune_mod


def _song(db, job: dict) -> dict:
    if not job.get("song_id"):
        raise RuntimeError("this job needs a song_id")
    song = db.get("taal_songs", job["song_id"])
    if song is None:
        raise RuntimeError(f"song {job['song_id']} not found")
    return song


def check_song(db, job: dict) -> dict:
    """Run the tune and plan rules on a draft song."""
    song = _song(db, job)
    if not song.get("tune") or not song.get("plan"):
        raise RuntimeError("the song needs both a tune and a plan before it can be checked")
    notes = None
    if song.get("instrument_id"):
        inst = db.get("taal_instruments", song["instrument_id"])
        if inst is None or inst["status"] != "ready":
            raise RuntimeError("the song's instrument is not ready yet")
        notes = inst.get("notes") or None
    tune_result = tune_mod.check_tune(song["tune"], song["level"], notes)
    plan_result = plan_mod.check_plan(song["plan"])
    if song["tune"].get("bpm") != song["plan"].get("bpm"):
        plan_result["ok"] = False
        plan_result["problems"].append("the tune and the plan have different tempos")
    checks = {
        "ok": tune_result["ok"] and plan_result["ok"],
        "tune": tune_result,
        "plan": plan_result,
        "timeline": plan_mod.timeline(song["plan"]) if plan_result["ok"] else None,
    }
    values = {"checks": checks}
    if checks["ok"]:
        values["status"] = "checked"
    db.update("taal_songs", song["id"], values)
    return checks


def backing_track(db, job: dict) -> dict:
    """Generate the backing track with ElevenLabs and store it."""
    song = _song(db, job)
    if song["status"] != "checked":
        raise RuntimeError("the song must pass check_song before audio is generated")
    audio, eleven_id = music.compose(song["plan"])
    path = db.upload(f"{song['family_id']}/{song['id']}/backing.mp3", audio, "audio/mpeg")
    total_ms = song["checks"]["plan"]["total_ms"]
    db.insert(
        "taal_costs",
        {
            "job_id": job["id"],
            "song_id": song["id"],
            "provider": "elevenlabs_music",
            "units": round(total_ms / 60000, 3),
            "unit": "minute",
            "amount_usd": music.cost_usd(total_ms),
        },
    )
    db.update("taal_songs", song["id"], {"audio_path": path, "status": "audio"})
    return {"audio_path": path, "elevenlabs_song_id": eleven_id, "bytes": len(audio)}


def publish_sample(db, job: dict) -> dict:
    """Make a finished song playable by anyone on the site, as a sample."""
    song = _song(db, job)
    if not song.get("audio_path"):
        raise RuntimeError("the song has no audio yet")
    audio, content_type = db.download(song["audio_path"])
    path = db.upload(f"samples/{song['id']}/backing.mp3", audio, "audio/mpeg", bucket="taal-public")
    db.update("taal_songs", song["id"], {"is_sample": True, "sample_audio_path": path})
    return {"sample_audio_path": path, "bytes": len(audio)}


CONTENT = pathlib.Path(__file__).parent / "content"


def load_album(db, job: dict) -> dict:
    """Create an album's songs from the bundled content file and take each one all the
    way to a published sample: check, backing track, publish. Songs already there are skipped."""
    payload = job.get("payload") or {}
    album, family_id = payload.get("album"), payload.get("family_id")
    if not album or not family_id or "/" in album or "." in album:
        raise RuntimeError("this job needs payload.album and payload.family_id")
    songs = json.loads((CONTENT / f"{album}.json").read_text())
    report = []
    for item in songs:
        entry = {"track": item["track"], "title": item["title"]}
        try:
            if db.find("taal_songs", album=album, track=item["track"]):
                entry["result"] = "already there"
            else:
                song = db.insert(
                    "taal_songs",
                    {
                        "family_id": family_id, "album": album, "track": item["track"],
                        "title": item["title"], "level": item["level"], "language": "en",
                        "tune": item["tune"], "plan": item["plan"], "lyrics": item["lyrics"],
                    },
                )
                step = {"id": job["id"], "song_id": song["id"]}
                checks = check_song(db, step)
                if not checks["ok"]:
                    raise RuntimeError(f"failed its checks: {checks['tune']['problems'] + checks['plan']['problems']}")
                backing_track(db, step)
                publish_sample(db, step)
                entry["result"] = "published"
                entry["song_id"] = song["id"]
        except Exception as exc:  # one bad song must not stop the album
            entry["result"] = f"failed: {exc}"[:300]
        report.append(entry)
    return {"album": album, "songs": report}


PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_PHOTO_BYTES = 5 * 1024 * 1024


def read_instrument(db, job: dict) -> dict:
    """Look at a family's instrument photo and save what it is and how it is laid out."""
    instrument_id = (job.get("payload") or {}).get("instrument_id")
    if not instrument_id:
        raise RuntimeError("this job needs payload.instrument_id")
    inst = db.get("taal_instruments", instrument_id)
    if inst is None:
        raise RuntimeError(f"instrument {instrument_id} not found")
    if not inst["photo_path"].startswith(f"{inst['family_id']}/"):
        raise RuntimeError("the photo is not in this family's folder")
    image, media_type = db.download(inst["photo_path"])
    media_type = media_type.split(";")[0].strip()
    if media_type not in PHOTO_TYPES:
        raise RuntimeError(f"unsupported photo type {media_type}; use JPEG, PNG or WebP")
    if len(image) > MAX_PHOTO_BYTES:
        raise RuntimeError("the photo is larger than 5 MB; send a smaller one")
    result = instrument_mod.clean_profile(instrument_mod.read_photo(image, media_type))
    db.update(
        "taal_instruments",
        instrument_id,
        {
            "kind": result["profile"]["kind"],
            "profile": result["profile"],
            "notes": result["notes"],
            "status": result["status"],
            "status_reason": result["reason"],
        },
    )
    return result


def ping(db, job: dict) -> dict:
    """Proves the queue works end to end."""
    return {"pong": True, "echo": job.get("payload") or {}}


HANDLERS = {
    "load_album": load_album,
    "ping": ping,
    "publish_sample": publish_sample,
    "read_instrument": read_instrument,
    "check_song": check_song,
    "backing_track": backing_track,
}
