"""Play-along video for one song: the screen keys light up in time with the music.

Made for YouTube. A short title card, the whole song, then an end card. In "listen" parts the
tune is played; in "your turn" parts the keys light up with no tune, so the child plays it.
Frames are drawn with Pillow and piped straight into ffmpeg; nothing is written per frame.
"""

from __future__ import annotations

import math
import os
import subprocess
import tempfile
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .tune import frequency

FONTS = os.path.join(os.path.dirname(__file__), "fonts")
W, H = 1920, 1080

INK = (17, 20, 39)
MUTED = (88, 94, 120)
BG = (238, 240, 251)
CARD = (255, 255, 255)
BAND = (226, 229, 246)
ACCENT = (59, 68, 196)
TURN = (229, 72, 122)
NOTE = {
    "C": (229, 72, 122), "D": (230, 154, 0), "E": (14, 156, 138), "F": (47, 127, 214),
    "G": (138, 85, 214), "A": (79, 157, 45), "B": (107, 114, 128),
}


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def _mix(c, toward, amount):
    return tuple(int(a + (b - a) * amount) for a, b in zip(c, toward))


def _letter(pitch: str) -> str:
    return pitch[0].upper()


class Song:
    """The same timing the website uses: sections in whole bars; the tune sits in every
    section long enough to hold it."""

    def __init__(self, song: dict):
        tune, plan = song["tune"], song["plan"]
        self.title = song.get("title") or "A Taal song"
        self.beat = 60.0 / tune["bpm"]
        self.per_bar = tune.get("beats_per_bar", 4)
        last = max(n["start"] + n["length"] for n in tune["notes"])
        self.tune_beats = math.ceil(last / self.per_bar) * self.per_bar
        self.cells = [None] * self.tune_beats
        for n in tune["notes"]:
            if n["start"] < self.tune_beats:
                self.cells[int(n["start"])] = n["pitch"]
        self.sections, self.notes = [], []
        bar = 0
        for sec in plan["sections"]:
            start = bar * self.per_bar * self.beat
            bar += sec["bars"]
            o = {
                "name": sec["name"], "bars": sec["bars"], "kind": sec.get("kind", "listen"),
                "lines": sec.get("lines") or [], "start": start, "end": bar * self.per_bar * self.beat,
            }
            o["tune"] = o["kind"] != "free" and sec["bars"] * self.per_bar >= self.tune_beats
            self.sections.append(o)
            if o["tune"]:
                for n in tune["notes"]:
                    self.notes.append({"p": n["pitch"], "t": start + n["start"] * self.beat,
                                       "turn": o["kind"] == "turn"})
        self.total = bar * self.per_bar * self.beat
        pitches = sorted({n["pitch"] for n in tune["notes"]}, key=frequency)
        self.pitches = pitches

    def section_at(self, t: float):
        for s in self.sections:
            if s["start"] <= t < s["end"]:
                return s
        return None


def melody_wav(song: Song, path: str, offset: float, length: float, rate: int = 44100) -> None:
    """The tune as the website plays it (a soft bell), except in the child's turns."""
    out = np.zeros(int((length + 1) * rate), dtype=np.float32)
    dur = 0.75
    tt = np.arange(int(dur * rate)) / rate
    env = np.where(tt < 0.01, tt / 0.01, np.exp(-(tt - 0.01) * 9.0)) * 0.45
    for n in song.notes:
        if n["turn"]:
            continue
        f = frequency(n["p"])
        wavef = (np.sin(2 * np.pi * f * tt) + 0.25 * np.sin(2 * np.pi * 4 * f * tt)) * env
        i = int((offset + n["t"]) * rate)
        out[i:i + len(wavef)] += wavef[: max(0, len(out) - i)]
    pcm = (np.clip(out, -1, 1) * 32767 * 0.8).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


class Painter:
    def __init__(self, song: Song, site: str):
        self.s = song
        self.site = site
        self.f_brand = _font("Baloo2-ExtraBold.ttf", 64)
        self.f_huge = _font("Baloo2-ExtraBold.ttf", 120)
        self.f_big = _font("Baloo2-ExtraBold.ttf", 96)
        self.f_key = _font("Baloo2-ExtraBold.ttf", 150)
        self.f_mid = _font("Baloo2-Bold.ttf", 54)
        self.f_lyric = _font("Baloo2-ExtraBold.ttf", 76)
        self.f_cell = _font("Baloo2-ExtraBold.ttf", 40)
        self.f_small = _font("NunitoSans-Bold.ttf", 34)
        self.f_tiny = _font("NunitoSans-Bold.ttf", 28)
        self.f_body = _font("NunitoSans-Regular.ttf", 40)

    # ---------- shared bits ----------
    def _base(self) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        im = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(im)
        d.text((80, 40), "Taal", font=self.f_brand, fill=ACCENT)
        d.text((W - 80, 52), self.s.title, font=self.f_mid, fill=INK, anchor="ra")
        return im, d

    def _keys(self, d, due: set, y=700, h=300, raise_px=18, show_turn=False):
        n = len(self.s.pitches)
        gap = 36
        width = (W - 160 - gap * (n - 1)) / n
        for i, p in enumerate(self.s.pitches):
            x = 80 + i * (width + gap)
            col = NOTE[_letter(p)]
            on = p in due
            top = y - (raise_px if on else 0)
            fill = col if on else _mix(col, BG, 0.55)
            if on:
                d.rounded_rectangle((x - 14, top - 14, x + width + 14, top + h + 14), radius=44, fill=(255, 255, 255))
                d.rounded_rectangle((x - 6, top - 6, x + width + 6, top + h + 6), radius=38, fill=INK)
            d.rounded_rectangle((x, top, x + width, top + h), radius=32, fill=fill)
            d.text((x + width / 2, top + h * 0.52), _letter(p), font=self.f_key, fill=CARD, anchor="mm")
            label = "now!" if on else f"key {i + 1}"
            d.text((x + width / 2, top + h - 34), label, font=self.f_small, fill=CARD, anchor="mm")

    # ---------- cards ----------
    def title_card(self, t: float) -> Image.Image:
        im, d = self._base()
        d.text((W / 2, 300), self.s.title, font=self.f_huge, fill=INK, anchor="mm")
        d.text((W / 2, 410), "Play along! You need " + str(len(self.s.pitches)) + " notes:",
               font=self.f_mid, fill=MUTED, anchor="mm")
        lit = int(t / 0.6) % (len(self.s.pitches) + 1)
        self._keys(d, {self.s.pitches[lit - 1]} if lit else set(), y=520, h=260, raise_px=12)
        d.text((W / 2, 900), "Xylophone, keyboard, piano, or tap along on the screen at " + self.site,
               font=self.f_small, fill=MUTED, anchor="mm")
        d.text((W / 2, 960), "Listen first. When it says “Your turn!”, you play.",
               font=self.f_small, fill=ACCENT, anchor="mm")
        return im

    def end_card(self, t: float) -> Image.Image:
        im, d = self._base()
        d.text((W / 2, 380), "You played a whole song!", font=self.f_huge, fill=INK, anchor="mm")
        d.text((W / 2, 520), "Play it again, or try the next one.", font=self.f_mid, fill=MUTED, anchor="mm")
        d.rounded_rectangle((W / 2 - 520, 640, W / 2 + 520, 780), radius=70, fill=ACCENT)
        d.text((W / 2, 708), self.site, font=self.f_big, fill=CARD, anchor="mm")
        d.text((W / 2, 880), "Your own songs, on the instrument you have at home.",
               font=self.f_small, fill=MUTED, anchor="mm")
        return im

    # ---------- the song ----------
    def song_frame(self, t: float) -> Image.Image:
        s = self.s
        im, d = self._base()
        cur = s.section_at(t)
        beat_pos = t / s.beat
        on_beat = (beat_pos - math.floor(beat_pos)) < 0.25

        # What to do now, with a countdown into the child's turn.
        nxt = None
        if cur:
            i = s.sections.index(cur)
            nxt = s.sections[i + 1] if i + 1 < len(s.sections) else None
        say, colour = "Listen", ACCENT
        if cur and cur["kind"] == "turn":
            say, colour = "Your turn!", TURN
        elif cur and cur["kind"] == "free":
            say, colour = "Make it up!", TURN
        elif cur and "together" in cur["name"].lower():
            say = "Play together"
        elif cur is s.sections[0] and not cur["tune"]:
            say = "Get ready"
        elif cur is s.sections[-1] and not cur["tune"]:
            say = "Well done!"
        if nxt and nxt["kind"] == "turn":
            left = math.ceil((nxt["start"] - t) / s.beat)
            if 1 <= left <= 3:
                say, colour = f"Your turn in {left}…", TURN
        d.ellipse((80, 170, 128, 218), fill=colour if on_beat else _mix(colour, BG, 0.7))
        d.text((156, 194), say, font=self.f_big, fill=colour, anchor="lm")

        # Timeline of the song's parts.
        x0, x1, ty = 80, W - 80, 268
        bars = sum(x["bars"] for x in s.sections)
        x = x0
        for sec in s.sections:
            wsec = (x1 - x0) * sec["bars"] / bars
            active = sec is cur
            turn = sec["kind"] in ("turn", "free")
            fill = (TURN if turn else ACCENT) if active else BAND
            d.rounded_rectangle((x + 3, ty, x + wsec - 3, ty + 64), radius=14, fill=fill,
                                outline=TURN if turn and not active else None, width=4)
            d.text((x + 18, ty + 32), sec["name"], font=self.f_tiny,
                   fill=CARD if active else (TURN if turn else INK), anchor="lm")
            x += wsec
        head = x0 + (x1 - x0) * min(t, s.total) / s.total
        d.rectangle((head - 3, ty - 8, head + 3, ty + 72), fill=INK)

        # Words, one line per bar.
        if cur and cur["kind"] not in ("turn", "free") and cur["lines"]:
            bar_in = int((t - cur["start"]) / (s.beat * s.per_bar))
            line = cur["lines"][min(bar_in, len(cur["lines"]) - 1)]
            d.text((W / 2, 420), line, font=self.f_lyric, fill=INK, anchor="mm")
        elif cur and cur["kind"] == "turn":
            d.text((W / 2, 420), "Play the key that lights up", font=self.f_lyric, fill=TURN, anchor="mm")
        elif cur and cur["kind"] == "free":
            d.text((W / 2, 420), "Play any notes you like. No wrong notes!", font=self.f_lyric, fill=TURN, anchor="mm")

        # The tune strip.
        cy, ch = 520, 84
        cw = (W - 160 - 6 * (s.tune_beats - 1) - 14 * (s.tune_beats // s.per_bar - 1)) / s.tune_beats
        in_tune = int((t - cur["start"]) / s.beat) if cur and cur["tune"] else -1
        cx = 80
        for b, p in enumerate(s.cells):
            if b and b % s.per_bar == 0:
                cx += 14
            fill = NOTE[_letter(p)] if p else BAND
            box = (cx, cy, cx + cw, cy + ch)
            if b == in_tune:
                d.rounded_rectangle((cx - 6, cy - 6, cx + cw + 6, cy + ch + 6), radius=18, fill=INK)
            d.rounded_rectangle(box, radius=14, fill=fill)
            if p:
                d.text((cx + cw / 2, cy + ch / 2 + 2), _letter(p), font=self.f_cell, fill=CARD, anchor="mm")
            cx += cw + 6

        due = set()
        for n in s.notes:
            if n["t"] - 0.05 <= t < n["t"] + s.beat * 0.8:
                due.add(n["p"])
        self._keys(d, due)
        return im


def render(song: dict, backing: str | None, out_path: str, site: str = "playtaal.net",
           fps: int = 30, intro: float = 5.0, outro: float = 5.0, limit: float | None = None) -> dict:
    s = Song(song)
    p = Painter(s, site)
    total = intro + s.total + outro
    if limit:
        total = min(total, limit)
    with tempfile.TemporaryDirectory() as tmp:
        mel = os.path.join(tmp, "melody.wav")
        melody_wav(s, mel, intro, total)
        cmd = ["ffmpeg", "-y", "-loglevel", "error",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
               "-i", mel]
        if backing:
            cmd += ["-i", backing]
            ms = int(intro * 1000)
            filt = (f"[2:a]adelay={ms}|{ms},volume=1.0[b];"
                    f"[1:a][b]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.95[a]")
        else:
            filt = "[1:a]anull[a]"
        cmd += ["-filter_complex", filt, "-map", "0:v", "-map", "[a]",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-t", f"{total:.3f}",
                "-movflags", "+faststart", out_path]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        frames = int(total * fps)
        for i in range(frames):
            t = i / fps
            if t < intro:
                im = p.title_card(t)
            elif t < intro + s.total:
                im = p.song_frame(t - intro)
            else:
                im = p.end_card(t - intro - s.total)
            proc.stdin.write(im.tobytes())
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError("ffmpeg failed")
    return {"seconds": round(total, 2), "frames": frames}


def still(song: dict, t: float, out_png: str, site: str = "playtaal.net", intro: float = 5.0) -> None:
    """One frame, for checking the look. t is seconds from the start of the video."""
    s = Song(song)
    p = Painter(s, site)
    if t < intro:
        im = p.title_card(t)
    elif t < intro + s.total:
        im = p.song_frame(t - intro)
    else:
        im = p.end_card(t - intro - s.total)
    im.save(out_png)
