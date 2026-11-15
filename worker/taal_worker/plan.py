"""The section plan: how a song is laid out, and its exact timing.

A plan is a dict:

    {
      "bpm": 96,
      "beats_per_bar": 4,
      "key": "C major",
      "styles": ["gentle piano", "children's choir", "soft arpeggio pulse"],
      "avoid": ["distorted guitar", "harsh drums"],
      "sections": [
        {"name": "Intro", "bars": 4, "kind": "listen", "lines": []},
        {"name": "Your turn", "bars": 4, "kind": "turn", "lines": []},
        ...
      ]
    }

Section lengths are whole bars, so every section starts on a bar line. That is what
lets the film cut on the beat and the player know when it is the child's turn.

Styles are abstract traits only. Never an artist, band or song name.
"""

from __future__ import annotations

# ElevenLabs Music limits for one chunk (docs read 15 Nov 2026).
CHUNK_MIN_MS = 3000
CHUNK_MAX_MS = 120000
MAX_LINES = 30
MAX_LINE_CHARS = 200

KINDS = {"listen", "turn"}


def section_ms(bars: int, bpm: float, beats_per_bar: int = 4) -> int:
    return round(bars * beats_per_bar * 60000 / bpm)


def timeline(plan: dict) -> list[dict]:
    """Each section with its start and end, in ms and in bars."""
    bpm, per_bar = plan["bpm"], plan.get("beats_per_bar", 4)
    out, bar, t = [], 0, 0
    for s in plan["sections"]:
        ms = section_ms(s["bars"], bpm, per_bar)
        out.append(
            {
                "name": s["name"],
                "kind": s.get("kind", "listen"),
                "start_bar": bar,
                "bars": s["bars"],
                "start_ms": t,
                "end_ms": t + ms,
            }
        )
        bar += s["bars"]
        t += ms
    return out


def check_plan(plan: dict) -> dict:
    problems: list[str] = []
    sections = plan.get("sections") or []
    if not sections:
        problems.append("the plan has no sections")
    if not plan.get("styles"):
        problems.append("the plan has no styles")

    bpm, per_bar = plan.get("bpm"), plan.get("beats_per_bar", 4)
    if not bpm:
        problems.append("the plan has no tempo")
        return {"ok": False, "problems": problems}

    for s in sections:
        ms = section_ms(s.get("bars", 0), bpm, per_bar)
        if not CHUNK_MIN_MS <= ms <= CHUNK_MAX_MS:
            problems.append(
                f"section {s.get('name')!r} lasts {ms} ms; "
                f"must be {CHUNK_MIN_MS}-{CHUNK_MAX_MS} ms"
            )
        if s.get("kind", "listen") not in KINDS:
            problems.append(f"section {s.get('name')!r} has unknown kind {s.get('kind')!r}")
        lines = s.get("lines") or []
        if len(lines) > MAX_LINES:
            problems.append(f"section {s.get('name')!r} has more than {MAX_LINES} lines")
        if any(len(line) > MAX_LINE_CHARS for line in lines):
            problems.append(f"section {s.get('name')!r} has a line over {MAX_LINE_CHARS} characters")

    if sections and not any(s.get("kind") == "turn" for s in sections):
        problems.append("the plan has no 'turn' section; every song must wait for the child")

    total = sum(section_ms(s.get("bars", 0), bpm, per_bar) for s in sections)
    return {"ok": not problems, "problems": problems, "total_ms": total}


def to_elevenlabs(plan: dict) -> dict:
    """Build the composition_plan for ElevenLabs Music v2: one chunk per section."""
    bpm = plan["bpm"]
    base = list(plan["styles"]) + [f"{bpm:g} BPM", f"key of {plan.get('key', 'C major')}"]
    avoid = list(plan.get("avoid") or [])
    chunks = []
    for s in plan["sections"]:
        lines = s.get("lines") or []
        text = f"[{s['name']}]"
        if lines:
            text += "\n" + "\n".join(lines)
        styles = base + list(s.get("styles") or [])
        negative = list(avoid)
        if not lines:
            styles.append("instrumental")
            negative.append("vocals")
        if s.get("kind") == "turn":
            # Leave room: the child fills the tune in these bars.
            styles.append("sparse accompaniment with space for a lead melody")
        chunk = {
            "text": text,
            "duration_ms": section_ms(s["bars"], bpm, plan.get("beats_per_bar", 4)),
            "positive_styles": styles,
        }
        if negative:
            chunk["negative_styles"] = negative
        chunks.append(chunk)
    return {"chunks": chunks}
