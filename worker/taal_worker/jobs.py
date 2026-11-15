"""What the worker can do so far. Each handler takes (db, job) and returns a result dict."""

from __future__ import annotations

import json
import pathlib
import time
from urllib.parse import urlparse

import httpx

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
    path = db.upload(
        f"samples/{song['id']}/backing-{int(time.time())}.mp3", audio, "audio/mpeg", bucket="taal-public"
    )
    db.update("taal_songs", song["id"], {"is_sample": True, "sample_audio_path": path})
    return {"sample_audio_path": path, "bytes": len(audio)}


CONTENT = pathlib.Path(__file__).parent / "content"


def load_album(db, job: dict) -> dict:
    """Create an album's songs from the bundled content file and take each one all the
    way to a published sample: check, backing track, publish. Songs already there are
    skipped, unless payload.replace is true: then they are rewritten and regenerated.
    payload.tracks, a list of track numbers, limits the job to those tracks."""
    payload = job.get("payload") or {}
    album, family_id = payload.get("album"), payload.get("family_id")
    if not album or not family_id or "/" in album or "." in album:
        raise RuntimeError("this job needs payload.album and payload.family_id")
    songs = json.loads((CONTENT / f"{album}.json").read_text())
    replace, only = bool(payload.get("replace")), payload.get("tracks")
    report = []
    for item in songs:
        if only and item["track"] not in only:
            continue
        entry = {"track": item["track"], "title": item["title"]}
        try:
            existing = db.find("taal_songs", album=album, track=item["track"])
            if existing and not replace:
                entry["result"] = "already there"
            elif existing:
                song = existing[0]
                db.update(
                    "taal_songs",
                    song["id"],
                    {"title": item["title"], "level": item["level"], "tune": item["tune"],
                     "plan": item["plan"], "lyrics": item["lyrics"], "status": "draft", "checks": None},
                )
                step = {"id": job["id"], "song_id": song["id"]}
                checks = check_song(db, step)
                if not checks["ok"]:
                    raise RuntimeError(f"failed its checks: {checks['tune']['problems'] + checks['plan']['problems']}")
                backing_track(db, step)
                publish_sample(db, step)
                entry["result"] = "regenerated"
                entry["song_id"] = song["id"]
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


ASSET_HOSTS = (".higgsfield.ai", ".cloudfront.net")
ASSET_TYPES = {"image/png", "image/jpeg", "image/webp", "video/mp4"}


def import_asset(db, job: dict) -> dict:
    """Copy a picture or short clip made for Taal (a cover, theme art) into the public bucket."""
    payload = job.get("payload") or {}
    url, path = payload.get("url", ""), payload.get("path", "")
    host = urlparse(url).hostname or ""
    if not url.startswith("https://") or not host.endswith(ASSET_HOSTS):
        raise RuntimeError("assets can only be imported from Higgsfield")
    if not path or ".." in path or not path.startswith(("covers/", "themes/")):
        raise RuntimeError("payload.path must start with covers/ or themes/")
    r = httpx.get(url, timeout=120.0, follow_redirects=True)
    if r.status_code >= 400:
        raise RuntimeError(f"could not fetch the asset: {r.status_code}")
    content_type = r.headers.get("content-type", "").split(";")[0].strip()
    if content_type not in ASSET_TYPES:
        raise RuntimeError(f"unsupported asset type {content_type!r}")
    if len(r.content) > 40 * 1024 * 1024:
        raise RuntimeError("the asset is larger than 40 MB")
    db.upload(path, r.content, content_type, bucket="taal-public")
    return {"path": path, "bytes": len(r.content), "content_type": content_type}


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


def render_video(db, job: dict) -> dict:
    """Make the YouTube play-along video for a sample song and put it in the public bucket."""
    import tempfile

    from . import video

    song = _song(db, job)
    payload = job.get("payload") or {}
    if not song.get("sample_audio_path"):
        raise RuntimeError("the song has no public backing track yet")
    with tempfile.TemporaryDirectory() as tmp:
        backing = f"{tmp}/backing.mp3"
        r = db.http.get(f"{db.url}/storage/v1/object/public/taal-public/{song['sample_audio_path']}")
        if r.status_code >= 400:
            raise RuntimeError(f"could not fetch the backing track: {r.status_code}")
        with open(backing, "wb") as f:
            f.write(r.content)
        out = f"{tmp}/video.mp4"
        started = time.time()
        try:
            info = video.render(song, backing, out)
        except Exception as exc:
            if payload.get("draft_id"):
                _draft_part(db, payload["draft_id"], "video", {"status": "failed", "error": str(exc)[:300], "at": _stamp()})
            raise
        with open(out, "rb") as f:
            data = f.read()
    name = payload.get("path") or (
        f"videos/{song.get('album') or 'songs'}/track{int(song.get('track') or 0):02d}-{int(time.time())}.mp4"
    )
    path = db.upload(name, data, "video/mp4", bucket="taal-public")
    if payload.get("draft_id"):
        _draft_part(db, payload["draft_id"], "video", {"status": "made", "path": path, "at": _stamp()})
    return {"path": path, "bytes": len(data), "seconds": info["seconds"],
            "render_seconds": round(time.time() - started, 1)}


def _stamp() -> str:
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).isoformat()


def write_song(db, job: dict) -> dict:
    """Taal Studio: write a song draft from a parent's brief (words and tune, no music yet)."""
    from . import writer

    draft_id = (job.get("payload") or {}).get("draft_id")
    if not draft_id:
        raise RuntimeError("this job needs payload.draft_id")
    draft = db.get("taal_studio_drafts", draft_id)
    if draft is None:
        raise RuntimeError(f"draft {draft_id} not found")
    db.update("taal_studio_drafts", draft_id, {"status": "writing", "updated_at": _stamp()})
    try:
        song = writer.write(draft["brief"])
    except Exception as exc:
        db.update("taal_studio_drafts", draft_id,
                  {"status": "failed", "error": str(exc)[:500], "updated_at": _stamp()})
        raise
    db.update("taal_studio_drafts", draft_id, {"status": "ready", "draft": song, "error": None, "updated_at": _stamp()})
    return {"draft_id": draft_id, "title": song["title"], "attempts": song["attempts"],
            "playability": song["checks"]["tune"]["playability"]}


def _draft_part(db, draft_id: str, key: str, value: dict) -> None:
    """Set one part (make / video) of a Studio draft's record, keeping the rest."""
    row = db.get("taal_studio_drafts", draft_id)
    if row is None:
        return
    d = dict(row.get("draft") or {})
    d[key] = value
    db.update("taal_studio_drafts", draft_id, {"draft": d, "updated_at": _stamp()})


def make_song(db, job: dict) -> dict:
    """Taal Studio: turn a family's draft into a real song with an ElevenLabs backing track."""
    import secrets

    draft_id = (job.get("payload") or {}).get("draft_id")
    row = db.get("taal_studio_drafts", draft_id) if draft_id else None
    if row is None or not row.get("draft"):
        raise RuntimeError("draft not found or not written yet")
    d = row["draft"]
    try:
        plan_check = plan_mod.check_plan(d["plan"])
        tune_check = tune_mod.check_tune(d["tune"], level=d.get("level", 1))
        problems = plan_check["problems"] + tune_check["problems"]
        if problems:
            raise RuntimeError("the draft no longer passes the rules: " + "; ".join(problems))
        song = db.insert("taal_songs", {
            "family_id": row["family_id"], "level": d.get("level", 1), "title": d.get("title"),
            "tune": d["tune"], "plan": d["plan"], "status": "checked",
            "checks": {"tune": tune_check, "plan": plan_check},
            "lyrics": "\n".join(sum((s.get("lines") or [] for s in d["plan"]["sections"]), [])),
        })
        audio, eleven_id = music.compose(d["plan"])
        # Unguessable public address, so the player can stream it before sign-in exists.
        path = db.upload(f"studio/{draft_id}/{secrets.token_hex(12)}.mp3", audio, "audio/mpeg", bucket="taal-public")
        db.insert("taal_costs", {
            "job_id": job["id"], "song_id": song["id"], "provider": "elevenlabs_music",
            "units": round(plan_check["total_ms"] / 60000, 3), "unit": "minute",
            "amount_usd": music.cost_usd(plan_check["total_ms"]),
        })
        db.update("taal_songs", song["id"], {"audio_path": path, "sample_audio_path": path, "status": "audio"})
    except Exception as exc:
        _draft_part(db, draft_id, "make", {"status": "failed", "error": str(exc)[:300], "at": _stamp()})
        raise
    _draft_part(db, draft_id, "make", {"status": "made", "song_id": song["id"], "audio_path": path, "at": _stamp()})
    return {"song_id": song["id"], "audio_path": path, "bytes": len(audio), "elevenlabs_song_id": eleven_id,
            "usd": music.cost_usd(plan_check["total_ms"])}


def ping(db, job: dict) -> dict:
    """Proves the queue works end to end."""
    return {"pong": True, "echo": job.get("payload") or {}}


HANDLERS = {
    "import_asset": import_asset,
    "load_album": load_album,
    "ping": ping,
    "render_video": render_video,
    "make_song": make_song,
    "write_song": write_song,
    "publish_sample": publish_sample,
    "read_instrument": read_instrument,
    "check_song": check_song,
    "backing_track": backing_track,
}
