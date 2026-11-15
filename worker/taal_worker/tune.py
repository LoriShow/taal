"""The child's tune: exact notes, and the rules a tune must pass before it ships.

A tune is a dict:

    {
      "bpm": 96,
      "beats_per_bar": 4,
      "notes": [{"pitch": "C4", "start": 0, "length": 1}, ...]   # start/length in beats
    }

The pitch rules come from the research in docs/concept: ages 3-5 sing comfortably
from about C4 to A4. The tempo band and the playability score are our own design
rules and are provisional until they are calibrated with real children.
"""

from __future__ import annotations

import os
from collections import Counter

_SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# What a child may be asked to sing or play at each level.
LEVELS = {
    1: {"pitches": ["C4", "D4", "E4"], "max_leap": 4},
    2: {"pitches": ["C4", "D4", "E4", "G4", "A4"], "max_leap": 7},
    3: {"pitches": ["C4", "D4", "E4", "G4", "A4"], "max_leap": 7},
    4: {"pitches": ["C4", "D4", "E4", "F4", "G4", "A4"], "max_leap": 9},
}

RANGE_LOW = "C4"
RANGE_HIGH = "A4"

# Provisional: to be calibrated by clapping tests with the founding family.
BPM_MIN = float(os.environ.get("TAAL_BPM_MIN", "60"))
BPM_MAX = float(os.environ.get("TAAL_BPM_MAX", "120"))
PLAYABILITY_PASS = float(os.environ.get("TAAL_PLAYABILITY_PASS", "60"))


def midi(pitch: str) -> int:
    """'C4' -> 60, 'F#4' -> 66, 'Bb3' -> 58."""
    name, rest = pitch[0].upper(), pitch[1:]
    if name not in _SEMITONES:
        raise ValueError(f"unknown pitch: {pitch!r}")
    offset = 0
    while rest and rest[0] in "#b":
        offset += 1 if rest[0] == "#" else -1
        rest = rest[1:]
    try:
        octave = int(rest)
    except ValueError as exc:
        raise ValueError(f"unknown pitch: {pitch!r}") from exc
    return 12 * (octave + 1) + _SEMITONES[name] + offset


def frequency(pitch: str) -> float:
    """Equal-tempered frequency in Hz, A4 = 440."""
    return 440.0 * 2 ** ((midi(pitch) - 69) / 12)


def beat_ms(bpm: float) -> float:
    return 60000.0 / bpm


def _bars(tune: dict) -> list[tuple]:
    """Each bar as a tuple of (pitch, start-in-bar, length), for repetition checks."""
    per_bar = tune.get("beats_per_bar", 4)
    bars: dict[int, list] = {}
    for n in tune["notes"]:
        index = int(n["start"] // per_bar)
        bars.setdefault(index, []).append(
            (midi(n["pitch"]), round(n["start"] - index * per_bar, 3), n["length"])
        )
    return [tuple(sorted(bars[i])) for i in sorted(bars)]


def playability(tune: dict) -> float:
    """0-100, higher is easier. Our own rule, not published science.

    Rewards few different notes, small steps between notes, and repeated bars.
    """
    notes = sorted(tune["notes"], key=lambda n: n["start"])
    if not notes:
        return 0.0
    pitches = [midi(n["pitch"]) for n in notes]

    distinct = len(set(pitches))
    few_notes = max(0.0, 1 - (distinct - 1) / 6)  # 1 note -> 1.0, 7+ notes -> 0

    leaps = [abs(b - a) for a, b in zip(pitches, pitches[1:])]
    mean_leap = sum(leaps) / len(leaps) if leaps else 0.0
    small_steps = max(0.0, 1 - mean_leap / 7)  # stepwise -> high, fifths -> 0

    bars = _bars(tune)
    counts = Counter(bars)
    repeated = sum(c for c in counts.values() if c > 1) / len(bars) if bars else 0.0

    return round(100 * (0.35 * few_notes + 0.35 * small_steps + 0.30 * repeated), 1)


def check_tune(tune: dict, level: int = 1) -> dict:
    """Return {"ok": bool, "problems": [...], "playability": float, ...}."""
    problems: list[str] = []
    rules = LEVELS.get(level)
    if rules is None:
        return {"ok": False, "problems": [f"unknown level {level}"]}

    notes = sorted(tune.get("notes", []), key=lambda n: n["start"])
    if not notes:
        return {"ok": False, "problems": ["the tune has no notes"]}

    low, high = midi(RANGE_LOW), midi(RANGE_HIGH)
    allowed = {midi(p) for p in rules["pitches"]}

    for n in notes:
        m = midi(n["pitch"])
        if not low <= m <= high:
            problems.append(f"{n['pitch']} at beat {n['start']} is outside {RANGE_LOW}-{RANGE_HIGH}")
        elif m not in allowed:
            problems.append(f"{n['pitch']} at beat {n['start']} is not a level {level} note")
        if n["length"] <= 0:
            problems.append(f"note at beat {n['start']} has no length")

    for a, b in zip(notes, notes[1:]):
        leap = abs(midi(b["pitch"]) - midi(a["pitch"]))
        if leap > rules["max_leap"]:
            problems.append(
                f"jump of {leap} semitones at beat {b['start']} "
                f"(level {level} allows {rules['max_leap']})"
            )
        if b["start"] < a["start"] + a["length"] - 1e-9:
            problems.append(f"notes overlap at beat {b['start']}; the child plays one note at a time")

    bpm = tune.get("bpm")
    if not bpm or not BPM_MIN <= bpm <= BPM_MAX:
        problems.append(f"tempo {bpm} bpm is outside {BPM_MIN:g}-{BPM_MAX:g} bpm")

    score = playability(tune)
    if score < PLAYABILITY_PASS:
        problems.append(f"playability {score} is below {PLAYABILITY_PASS:g}")

    return {
        "ok": not problems,
        "problems": problems,
        "playability": score,
        "level": level,
        "beat_ms": round(beat_ms(bpm), 2) if bpm else None,
        "range_hz": [round(frequency(RANGE_LOW), 2), round(frequency(RANGE_HIGH), 2)],
    }
