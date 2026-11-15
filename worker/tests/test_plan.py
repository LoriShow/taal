

def test_free_section_is_allowed_and_instrumental():
    from taal_worker import plan as P
    p = {"bpm": 96, "beats_per_bar": 4, "styles": ["piano"], "sections": [
        {"name": "Your turn", "bars": 4, "kind": "turn", "lines": []},
        {"name": "Make it up", "bars": 4, "kind": "free", "lines": []}]}
    assert P.check_plan(p)["ok"]
    chunk = P.to_elevenlabs(p)["chunks"][1]
    assert "instrumental" in chunk["positive_styles"]
    assert any("make up a melody" in s for s in chunk["positive_styles"])
