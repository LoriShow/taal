"""Taal Studio: write a new song draft from what a parent tells us.

Claude writes the title, the words and the child's tune; the song's shape (intro, listen,
your turn, together, outro) is fixed here so every draft waits for the child. Every tune is
checked with the same rules as the album, and Claude is asked again (up to three tries)
with the problems spelled out if it fails.
"""

from __future__ import annotations

import os

import httpx

from . import plan as plan_mod
from . import tune as tune_mod

API = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("TAAL_WRITER_MODEL", "claude-sonnet-5-5")

MOODS = {
    "calm": ("84-96", "gentle, warm, unhurried"),
    "bouncy": ("100-112", "bright, bouncy, playful"),
    "silly": ("104-116", "silly, cheeky, giggly"),
    "sleepy": ("66-80", "soft, sleepy, like a lullaby"),
    "brave": ("96-108", "bold, marching, proud"),
}

SYSTEM = (
    "You write very short songs that a parent and a child of three to five play together. "
    "The child plays the tune on a few notes, so the tune must be easy, repetitive and "
    "singable. The words are for small children: simple, kind, concrete, nothing scary or "
    "unkind, no brand names, no real artists or song titles, nothing that copies an "
    "existing song. Use the child's name only if one is given."
)

TOOL = {
    "name": "record_song",
    "description": "Record the new song.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Up to 5 words"},
            "bpm": {"type": "integer"},
            "notes": {
                "type": "array",
                "description": "The child's tune: 4 bars of 4 beats (beats 0-15), one note per beat at most.",
                "items": {
                    "type": "object",
                    "properties": {
                        "pitch": {"type": "string", "description": "One of the allowed notes, e.g. C4"},
                        "beat": {"type": "integer", "description": "0 to 15"},
                    },
                    "required": ["pitch", "beat"],
                },
            },
            "listen_lines": {
                "type": "array", "items": {"type": "string"},
                "description": "4 short lines sung in the first part, one per bar, up to 6 words each",
            },
            "together_lines": {
                "type": "array", "items": {"type": "string"},
                "description": "4 short lines for the part everyone plays together",
            },
            "styles": {
                "type": "array", "items": {"type": "string"},
                "description": "3 to 6 plain music descriptions: instruments, feel. No artist or song names.",
            },
        },
        "required": ["title", "bpm", "notes", "listen_lines", "together_lines", "styles"],
    },
}


def _clean_text(s, limit: int) -> str:
    s = " ".join(str(s or "").split())
    return s[:limit]


def brief_from(raw: dict) -> dict:
    """Keep only what we use, with limits, whatever the page sent."""
    mood = raw.get("mood") if raw.get("mood") in MOODS else "bouncy"
    level = 2 if str(raw.get("level")) == "2" else 1
    return {
        "about": _clean_text(raw.get("about"), 200) or "a happy day",
        "child_name": _clean_text(raw.get("child_name"), 30),
        "mood": mood,
        "level": level,
        "variation": int(raw.get("variation") or 0) % 100,
    }


def _prompt(brief: dict, problems: list[str]) -> str:
    level = brief["level"]
    rules = tune_mod.LEVELS[level]
    notes = ", ".join(rules["pitches"])
    bpm_range, feel = MOODS[brief["mood"]]
    lines = [
        f"Write a song about: {brief['about']}.",
        f"Child's name: {brief['child_name']}." if brief["child_name"] else "No child's name: do not invent one.",
        f"Feel: {feel}. Tempo between {bpm_range} beats per minute.",
        f"The tune may use only these notes: {notes}. Never jump more than {rules['max_leap']} "
        "semitones between neighbouring notes; mostly move by step or repeat a note.",
        "Tune shape: 4 bars of 4 beats (beats 0 to 15). Put a note on most beats but leave the "
        "last beat of each bar (beats 3, 7, 11, 15) empty, so the child can breathe. "
        "Make bar 3 the same as bar 1. Use 9 to 12 notes in all. Start on C4; end on C4.",
        "Words: 4 lines for listening and 4 lines for playing together, one line per bar, "
        "each line up to 6 short words. Repeat lines freely; small children love repetition.",
        "Styles: plain descriptions only (e.g. 'gentle piano', 'soft ukulele', 'light shaker').",
    ]
    if brief["variation"]:
        lines.append(f"This is attempt {brief['variation'] + 1}: make the tune clearly different from a plain scale.")
    if problems:
        lines.append("Your last tune broke these rules; fix every one: " + "; ".join(problems))
    return "\n".join(lines)


def _ask(brief: dict, problems: list[str], timeout: float = 90.0) -> dict:
    key = os.environ["ANTHROPIC_API_KEY"]
    body = {
        "model": MODEL,
        "max_tokens": 2000,
        "system": SYSTEM,
        "tools": [TOOL],
        "tool_choice": {"type": "tool", "name": TOOL["name"]},
        "messages": [{"role": "user", "content": _prompt(brief, problems)}],
    }
    r = httpx.post(API, headers={"x-api-key": key, "anthropic-version": "2023-06-01"}, json=body, timeout=timeout)
    if r.status_code >= 400:
        raise RuntimeError(f"Claude {r.status_code}: {r.text[:500]}")
    for block in r.json().get("content", []):
        if block.get("type") == "tool_use":
            return block["input"]
    raise RuntimeError("Claude did not return a song")


def assemble(raw: dict, brief: dict) -> dict:
    """Turn Claude's answer into a Taal song (tune + plan) and check it."""
    bpm = int(raw.get("bpm") or 96)
    seen, notes = set(), []
    for n in raw.get("notes") or []:
        try:
            beat = int(n.get("beat"))
            pitch = str(n.get("pitch"))
            tune_mod.midi(pitch)
        except (TypeError, ValueError):
            continue
        if 0 <= beat <= 15 and beat not in seen:
            seen.add(beat)
            notes.append({"pitch": pitch[0].upper() + pitch[1:], "start": beat, "length": 1})
    notes.sort(key=lambda n: n["start"])
    tune = {"bpm": bpm, "beats_per_bar": 4, "notes": notes}

    def four(lines):
        out = [_clean_text(x, 40) for x in (lines or []) if _clean_text(x, 40)][:4]
        return out or ["La la la"]

    styles = [_clean_text(s, 40) for s in (raw.get("styles") or []) if _clean_text(s, 40)][:6]
    if len(styles) < 2:
        styles = ["gentle piano", "light shaker", "warm and simple"]
    styles += ["simple major harmony", "steady clear beat"]
    plan = {
        "bpm": bpm, "beats_per_bar": 4, "key": "C major", "styles": styles,
        "avoid": ["heavy drums", "distortion", "dark mood", "fast runs"],
        "sections": [
            {"name": "Intro", "bars": 2, "kind": "listen", "lines": []},
            {"name": "Listen", "bars": 4, "kind": "listen", "lines": four(raw.get("listen_lines"))},
            {"name": "Your turn", "bars": 4, "kind": "turn", "lines": []},
            {"name": "Together", "bars": 4, "kind": "listen", "lines": four(raw.get("together_lines")),
             "styles": ["fuller, brighter, builds"]},
            {"name": "Outro", "bars": 2, "kind": "listen", "lines": []},
        ],
    }
    tune_check = tune_mod.check_tune(tune, level=brief["level"])
    plan_check = plan_mod.check_plan(plan)
    problems = list(tune_check["problems"]) + list(plan_check["problems"])
    if len(notes) < 6:
        problems.append(f"the tune has only {len(notes)} notes; use 9 to 12")
    return {
        "title": _clean_text(raw.get("title"), 50) or "Our song",
        "level": brief["level"],
        "tune": tune,
        "plan": plan,
        "checks": {"tune": tune_check, "plan": plan_check},
        "problems": problems,
    }


def write(raw_brief: dict, tries: int = 3) -> dict:
    brief = brief_from(raw_brief)
    problems: list[str] = []
    song = None
    for attempt in range(1, tries + 1):
        song = assemble(_ask(brief, problems), brief)
        song["attempts"] = attempt
        if not song["problems"]:
            return song
        problems = song["problems"]
    raise RuntimeError("could not write a tune that passes the rules: " + "; ".join(problems or []))
