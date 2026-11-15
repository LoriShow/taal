"""What the worker can do so far. Each handler takes (db, job) and returns a result dict."""

from __future__ import annotations

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
    tune_result = tune_mod.check_tune(song["tune"], song["level"])
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


def ping(db, job: dict) -> dict:
    """Proves the queue works end to end."""
    return {"pong": True, "echo": job.get("payload") or {}}


HANDLERS = {
    "ping": ping,
    "check_song": check_song,
    "backing_track": backing_track,
}
