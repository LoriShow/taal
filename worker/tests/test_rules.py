from taal_worker import instrument as instrument_mod
from taal_worker import plan as plan_mod
from taal_worker import tune as tune_mod


def note(pitch, start, length=1):
    return {"pitch": pitch, "start": start, "length": length}


# Two bars, repeated: C D E E | C D E E
EASY = {
    "bpm": 96,
    "beats_per_bar": 4,
    "notes": [note(p, i) for i, p in enumerate(["C4", "D4", "E4", "E4"] * 2)],
}

PLAN = {
    "bpm": 96,
    "beats_per_bar": 4,
    "key": "C major",
    "styles": ["gentle piano", "children's choir"],
    "avoid": ["harsh drums"],
    "sections": [
        {"name": "Intro", "bars": 4, "kind": "listen", "lines": []},
        {"name": "Listen", "bars": 4, "kind": "listen", "lines": ["la la la"]},
        {"name": "Your turn", "bars": 4, "kind": "turn", "lines": []},
    ],
}


def test_pitch_maths():
    assert tune_mod.midi("C4") == 60
    assert tune_mod.midi("A4") == 69
    assert tune_mod.midi("Bb3") == 58
    assert round(tune_mod.frequency("A4"), 2) == 440.00
    assert round(tune_mod.frequency("C4"), 2) == 261.63
    assert tune_mod.beat_ms(120) == 500


def test_easy_tune_passes_level_1():
    result = tune_mod.check_tune(EASY, level=1)
    assert result["ok"], result["problems"]
    assert result["beat_ms"] == 625.0


def test_note_outside_range_fails():
    bad = {**EASY, "notes": EASY["notes"] + [note("C5", 8)]}
    result = tune_mod.check_tune(bad, level=2)
    assert not result["ok"]
    assert any("outside C4-A4" in p for p in result["problems"])


def test_level_1_rejects_level_2_notes():
    tune = {**EASY, "notes": [note(p, i) for i, p in enumerate(["C4", "D4", "E4", "G4"] * 2)]}
    assert not tune_mod.check_tune(tune, level=1)["ok"]
    assert tune_mod.check_tune(tune, level=2)["ok"]


def test_big_jump_fails():
    tune = {**EASY, "notes": [note(p, i) for i, p in enumerate(["C4", "A4", "C4", "A4"] * 2)]}
    result = tune_mod.check_tune(tune, level=2)
    assert any("jump of 9" in p for p in result["problems"])


def test_tempo_band():
    assert not tune_mod.check_tune({**EASY, "bpm": 170}, level=1)["ok"]


def test_overlapping_notes_fail():
    tune = {**EASY, "notes": [note("C4", 0, 2), note("D4", 1, 1)]}
    assert any("overlap" in p for p in tune_mod.check_tune(tune, level=1)["problems"])


def test_repetition_raises_playability():
    wandering = {
        **EASY,
        "notes": [note(p, i) for i, p in enumerate(["C4", "E4", "D4", "C4", "E4", "C4", "D4", "E4"])],
    }
    assert tune_mod.playability(EASY) > tune_mod.playability(wandering)


def test_plan_timing():
    assert plan_mod.section_ms(4, 96) == 10000
    result = plan_mod.check_plan(PLAN)
    assert result["ok"], result["problems"]
    assert result["total_ms"] == 30000
    line = plan_mod.timeline(PLAN)
    assert [s["start_ms"] for s in line] == [0, 10000, 20000]
    assert line[2]["start_bar"] == 8 and line[2]["kind"] == "turn"


def test_plan_needs_a_turn():
    plan = {**PLAN, "sections": PLAN["sections"][:2]}
    assert any("turn" in p for p in plan_mod.check_plan(plan)["problems"])


def test_plan_rejects_too_short_section():
    plan = {**PLAN, "sections": [{"name": "Blip", "bars": 1, "kind": "turn", "lines": []}]}
    assert not plan_mod.check_plan(plan)["ok"]  # 1 bar at 96 bpm is 2.5 s


def test_elevenlabs_plan_shape():
    chunks = plan_mod.to_elevenlabs(PLAN)["chunks"]
    assert len(chunks) == 3
    assert chunks[0]["text"] == "[Intro]"
    assert chunks[0]["duration_ms"] == 10000
    assert "instrumental" in chunks[0]["positive_styles"]
    assert "vocals" in chunks[0]["negative_styles"]
    assert chunks[1]["text"] == "[Listen]\nla la la"
    assert "96 BPM" in chunks[1]["positive_styles"]
    assert "vocals" not in chunks[1]["negative_styles"]
    assert any("space for a lead melody" in s for s in chunks[2]["positive_styles"])


# A family's own instrument ---------------------------------------------------

XYLO = ["C5", "D5", "E5", "F5", "G5", "A5", "B5", "C6"]


def test_tune_on_own_instrument_ignores_voice_range():
    tune = {**EASY, "notes": [note(p, i) for i, p in enumerate(["C5", "D5", "E5", "E5"] * 2)]}
    assert not tune_mod.check_tune(tune, level=1)["ok"]  # too high to sing
    result = tune_mod.check_tune(tune, level=1, instrument_notes=XYLO)
    assert result["ok"], result["problems"]
    assert result["for"] == "instrument"


def test_note_missing_from_instrument_fails():
    tune = {**EASY, "notes": [note(p, i) for i, p in enumerate(["C5", "D5", "F#5", "D5"] * 2)]}
    result = tune_mod.check_tune(tune, level=2, instrument_notes=XYLO)
    assert any("not on this instrument" in p for p in result["problems"])


def test_level_limits_how_many_notes_on_instrument():
    tune = {**EASY, "notes": [note(p, i) for i, p in enumerate(["C5", "D5", "E5", "F5"] * 2)]}
    result = tune_mod.check_tune(tune, level=1, instrument_notes=XYLO)
    assert any("4 different notes" in p for p in result["problems"])


def part(label=None, colour=None, guess=None):
    return {"label": label, "colour": colour, "note_guess": guess}


def test_keyboard_photo_is_ready_with_notes():
    raw = {"kind": "keyboard", "name": "mini keyboard", "pitched": True, "layout": "keys",
           "parts": [part(guess=g) for g in ["C4", "D4", "E4", "F4", "G4"]],
           "people_visible": False, "confidence": 0.9}
    out = instrument_mod.clean_profile(raw)
    assert out["status"] == "ready"
    assert out["notes"] == ["C4", "D4", "E4", "F4", "G4"]
    assert out["profile"]["count"] == 5


def test_xylophone_photo_needs_tuning_even_with_guesses():
    raw = {"kind": "xylophone", "name": "rainbow xylophone", "pitched": True, "layout": "row",
           "parts": [part(colour=c, guess=g) for c, g in [("red", "C5"), ("orange", "D5"), ("yellow", None)]],
           "people_visible": False, "confidence": 0.8}
    out = instrument_mod.clean_profile(raw)
    assert out["status"] == "needs_tuning"
    assert out["notes"] == []
    assert [p["colour"] for p in out["profile"]["parts"]] == ["red", "orange", "yellow"]


def test_photo_with_a_person_must_be_retaken():
    raw = {"kind": "ukulele", "name": "ukulele", "pitched": True, "layout": "strings",
           "parts": [part() for _ in range(4)], "people_visible": True, "confidence": 0.9}
    assert instrument_mod.clean_profile(raw)["status"] == "retake"


def test_no_instrument_must_be_retaken():
    raw = {"kind": "none", "name": "", "pitched": False, "layout": "single", "parts": [],
           "people_visible": False, "confidence": 0.9}
    assert instrument_mod.clean_profile(raw)["status"] == "retake"


def test_rhythm_instrument_is_ready_without_notes():
    raw = {"kind": "household", "name": "two steel pots and a spoon", "pitched": False,
           "layout": "pads", "parts": [part(colour="silver"), part(colour="silver")],
           "people_visible": False, "confidence": 0.7}
    out = instrument_mod.clean_profile(raw)
    assert out["status"] == "ready" and out["notes"] == []


def test_bad_model_output_is_tidied():
    raw = {"kind": "spaceship", "name": None, "pitched": 1, "layout": "spiral",
           "parts": [part(guess="H9"), part(guess="c4")], "people_visible": False, "confidence": 7}
    out = instrument_mod.clean_profile(raw)
    assert out["profile"]["kind"] == "other" and out["profile"]["layout"] == "row"
    assert out["profile"]["confidence"] == 1.0
    assert [p["note_guess"] for p in out["profile"]["parts"]] == [None, "C4"]
