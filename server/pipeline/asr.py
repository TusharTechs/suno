"""Speech-to-text for the teacher's voice note (Sarvam saaras:v4), then numbered sentences.

The note is the teacher's own adult voice, close to her phone: the easy case for
speech recognition. Sarvam's REST endpoint takes clips of about 30 s, so longer notes
are cut at pauses into clips of at most 25 s.

`keyterms` (roster names, lesson words) are OFF by default: in our tests they pushed the
recogniser to "correct" the misreading a teacher quotes ("पानी को पनी" came back as
"पानी को पानी"), and code already matches name spellings phonetically (names.py).
Set SUNO_ASR_KEYTERMS=names to send roster names only.
"""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import tempfile
import unicodedata
from pathlib import Path

import httpx
import numpy as np
import soundfile as sf
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

URL = "https://api.sarvam.ai/speech-to-text"
MODEL = "saaras:v4"
RATE = 16000
MAX_CLIP_S = 25.0
MAX_NOTE_S = 180.0
MAX_KEYTERMS = 50


class ASRError(RuntimeError):
    pass


def to_wav16k(data: bytes) -> np.ndarray:
    """Any audio the browser or phone produces (webm/opus, m4a, wav, ogg) -> 16 kHz mono float32."""
    with tempfile.TemporaryDirectory() as d:
        src, dst = Path(d) / "in", Path(d) / "out.wav"
        src.write_bytes(data)
        r = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(src),
                            "-ac", "1", "-ar", str(RATE), "-sample_fmt", "s16", str(dst)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise ASRError(f"could not read the audio: {r.stderr.strip()[:200]}")
        audio, _ = sf.read(dst, dtype="float32")
    return audio


def split_at_pauses(audio: np.ndarray, max_s: float = MAX_CLIP_S) -> list[np.ndarray]:
    """Cut into clips of at most max_s, each cut placed in the quietest 50 ms near the limit."""
    win = int(0.05 * RATE)
    clips, start, n = [], 0, len(audio)
    while n - start > max_s * RATE:
        lo, hi = start + int(0.6 * max_s * RATE), start + int(max_s * RATE)
        frames = audio[lo:hi][: (hi - lo) // win * win].reshape(-1, win)
        cut = lo + int(np.argmin((frames ** 2).mean(axis=1))) * win + win // 2
        clips.append(audio[start:cut])
        start = cut
    clips.append(audio[start:])
    return [c for c in clips if len(c) > 0.3 * RATE]


def keyterms(roster: list[dict], lesson: dict | None) -> list[str]:
    terms: list[str] = []
    for c in roster:
        for n in [c["first_name"], *[a for a in c.get("aliases", []) if not a.isascii()]]:
            if n not in terms:
                terms.append(n)
    for items in (lesson or {}).get("items", {}).values():
        for i in items:
            if len(terms) >= MAX_KEYTERMS:
                break
            if " " not in i and not any(ch.isdigit() for ch in i) and i not in terms:
                terms.append(i)
    return [t[:64] for t in terms[:MAX_KEYTERMS]]


def _transcribe_clip(clip: np.ndarray, terms: list[str]) -> str:
    key = os.environ.get("SARVAM_API_KEY")
    if not key:
        raise ASRError("SARVAM_API_KEY is not set")
    buf = io.BytesIO()
    sf.write(buf, clip, RATE, format="WAV", subtype="PCM_16")
    for attempt in range(3):
        try:
            r = httpx.post(URL, timeout=60, headers={"api-subscription-key": key},
                           files={"file": ("note.wav", buf.getvalue(), "audio/wav")},
                           data={"model": MODEL, "language_code": "hi-IN",
                                 **({"keyterms": json.dumps(terms, ensure_ascii=False)} if terms else {})})
        except httpx.HTTPError as e:
            if attempt == 2:
                raise ASRError(f"speech-to-text unreachable: {e}") from e
            continue
        if r.status_code in (429, 500, 503) and attempt < 2:
            continue
        if r.status_code != 200:
            raise ASRError(f"speech-to-text failed ({r.status_code}): {r.text[:200]}")
        return r.json().get("transcript", "").strip()
    raise ASRError("speech-to-text failed after retries")


def transcribe(data: bytes, roster: list[dict], lesson: dict | None = None) -> dict:
    """Returns {"transcript", "seconds", "clips"}."""
    audio = to_wav16k(data)
    seconds = len(audio) / RATE
    if seconds < 1.0:
        raise ASRError("the recording is shorter than a second")
    if seconds > MAX_NOTE_S:
        raise ASRError(f"the recording is {seconds:.0f} s; please keep a note under {MAX_NOTE_S:.0f} s")
    mode = os.environ.get("SUNO_ASR_KEYTERMS", "off")
    terms = keyterms(roster, lesson if mode == "all" else None) if mode in ("names", "all") else []
    clips = split_at_pauses(audio)
    text = " ".join(t for t in (_transcribe_clip(c, terms) for c in clips) if t)
    return {"transcript": text, "seconds": round(seconds, 1), "clips": len(clips)}


_SENT_END = re.compile(r"(?<=[।?!.|])\s+|\n+")


def sentences(transcript: str) -> list[dict]:
    """Split into numbered sentences s1, s2, ... that every claim must cite."""
    t = unicodedata.normalize("NFC", transcript).strip()
    parts = [p.strip() for p in _SENT_END.split(t) if p and p.strip()]
    out: list[str] = []
    for p in parts:  # very long unpunctuated runs: split on commas so citations stay precise
        out.extend([q.strip() for q in p.split(",") if q.strip()] if len(p) > 220 else [p])
    return [{"sent_id": f"s{i}", "text": s} for i, s in enumerate(out, 1)]
