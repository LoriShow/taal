"""Backing tracks from ElevenLabs Music."""

from __future__ import annotations

import os

import httpx

from . import plan as plan_mod

API = "https://api.elevenlabs.io/v1/music"
MODEL = os.environ.get("ELEVENLABS_MUSIC_MODEL", "music_v2")
# ElevenLabs lists the Music API at $0.15 per generated minute (read 15 Nov 2026).
USD_PER_MINUTE = float(os.environ.get("ELEVENLABS_MUSIC_USD_PER_MIN", "0.15"))


def compose(plan: dict, timeout: float = 600.0) -> tuple[bytes, str | None]:
    """Generate the backing track for a plan. Returns (mp3 bytes, ElevenLabs song id)."""
    key = os.environ["ELEVENLABS_API_KEY"]
    body = {"model_id": MODEL, "composition_plan": plan_mod.to_elevenlabs(plan)}
    r = httpx.post(API, headers={"xi-api-key": key}, json=body, timeout=timeout)
    if r.status_code >= 400:
        raise RuntimeError(f"ElevenLabs Music {r.status_code}: {r.text[:500]}")
    return r.content, r.headers.get("song-id")


def cost_usd(total_ms: int) -> float:
    return round(total_ms / 60000 * USD_PER_MINUTE, 4)
