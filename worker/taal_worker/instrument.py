"""Read a family's instrument from a photo, so the lesson fits what they own.

A photo shows what the instrument is and how it is laid out. It cannot show how the
instrument is tuned: toy xylophones are often off-pitch. So a pitched instrument that
is not a keyboard stays at "needs_tuning" until each bar or string has been played
into a microphone and measured (not built yet).
"""

from __future__ import annotations

import base64
import os

import httpx

from . import tune as tune_mod

API = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("TAAL_VISION_MODEL", "claude-sonnet-5-5")

KINDS = {
    "keyboard", "piano", "xylophone", "glockenspiel", "ukulele", "guitar", "harmonium",
    "tabla", "dholak", "drum", "shaker", "tambourine", "household", "other", "none",
}
# Fixed-pitch instruments a photo is enough for: the keys follow a standard.
STANDARD_PITCH = {"keyboard", "piano"}
LAYOUTS = {"row", "keys", "strings", "pads", "single"}
MAX_PARTS = 88

PROMPT = (
    "This photo was sent by a parent so a music lesson for a small child can be built "
    "around the instrument they own. Describe only the instrument. "
    "List each playable part from left to right (or low to high): each bar, key, string "
    "or drum. For a piano-style keyboard list the white keys only. "
    "Give note_guess only when you can read it: a note name printed on the part, or the "
    "standard layout of a piano-style keyboard. Otherwise leave it null; do not guess "
    "the tuning of a xylophone or toy from its looks. "
    "Set people_visible to true if any person, or part of one beyond hands, is in the photo. "
    "If the photo shows no instrument, use kind 'none'."
)

TOOL = {
    "name": "record_instrument",
    "description": "Record what the instrument in the photo is and how it is laid out.",
    "input_schema": {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": sorted(KINDS)},
            "name": {"type": "string", "description": "Plain name, e.g. '8-bar rainbow xylophone'"},
            "pitched": {"type": "boolean", "description": "True if it plays different notes"},
            "layout": {"type": "string", "enum": sorted(LAYOUTS)},
            "parts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": ["string", "null"], "description": "Text printed on the part"},
                        "colour": {"type": ["string", "null"], "description": "One plain colour word"},
                        "note_guess": {"type": ["string", "null"], "description": "e.g. C4, or null"},
                    },
                    "required": ["label", "colour", "note_guess"],
                },
            },
            "people_visible": {"type": "boolean"},
            "confidence": {"type": "number", "description": "0 to 1"},
            "note_for_parent": {"type": "string", "description": "One friendly sentence"},
        },
        "required": ["kind", "name", "pitched", "layout", "parts", "people_visible", "confidence"],
    },
}


def read_photo(image: bytes, media_type: str, timeout: float = 120.0) -> dict:
    """Ask Claude what the instrument is. Returns the raw tool input."""
    key = os.environ["ANTHROPIC_API_KEY"]
    body = {
        "model": MODEL,
        "max_tokens": 4000,
        "tools": [TOOL],
        "tool_choice": {"type": "tool", "name": TOOL["name"]},
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64.standard_b64encode(image).decode(),
                        },
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
    }
    r = httpx.post(
        API,
        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
        json=body,
        timeout=timeout,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"Claude {r.status_code}: {r.text[:500]}")
    for block in r.json().get("content", []):
        if block.get("type") == "tool_use":
            return block["input"]
    raise RuntimeError("Claude did not return an instrument description")


def _valid_pitch(pitch) -> str | None:
    if not isinstance(pitch, str):
        return None
    try:
        tune_mod.midi(pitch)
    except ValueError:
        return None
    return pitch[0].upper() + pitch[1:]


def clean_profile(raw: dict) -> dict:
    """Tidy what the model returned and decide what happens next.

    Returns {"profile": {...}, "notes": [...], "status": ...} where status is:
      retake        the photo shows people, or no instrument; ask for another
      needs_tuning  pitched, but the real notes must be measured before a tune is written
      ready         usable now (standard keyboard, or a rhythm instrument)
    """
    kind = raw.get("kind") if raw.get("kind") in KINDS else "other"
    layout = raw.get("layout") if raw.get("layout") in LAYOUTS else "row"
    parts = []
    for i, p in enumerate((raw.get("parts") or [])[:MAX_PARTS]):
        parts.append(
            {
                "index": i,
                "label": (p.get("label") or None),
                "colour": (p.get("colour") or None),
                "note_guess": _valid_pitch(p.get("note_guess")),
            }
        )
    profile = {
        "kind": kind,
        "name": str(raw.get("name") or kind)[:120],
        "pitched": bool(raw.get("pitched")),
        "layout": layout,
        "parts": parts,
        "count": len(parts),
        "confidence": max(0.0, min(1.0, float(raw.get("confidence") or 0))),
        "note_for_parent": str(raw.get("note_for_parent") or "")[:300],
    }

    if raw.get("people_visible"):
        return {"profile": profile, "notes": [], "status": "retake",
                "reason": "Please send a photo of the instrument only, with nobody in it."}
    if kind == "none" or not parts:
        return {"profile": profile, "notes": [], "status": "retake",
                "reason": "We could not find an instrument in this photo."}

    if not profile["pitched"]:
        return {"profile": profile, "notes": [], "status": "ready", "reason": "Rhythm instrument."}

    guesses = [p["note_guess"] for p in parts]
    if kind in STANDARD_PITCH and all(guesses):
        return {"profile": profile, "notes": guesses, "status": "ready",
                "reason": "Standard keyboard; notes taken from the key layout."}
    return {"profile": profile, "notes": [], "status": "needs_tuning",
            "reason": "Play each bar or string once so its real note can be measured."}
