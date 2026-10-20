"""Speak the morning brief with Sarvam text-to-speech (bulbul:v3, Hindi)."""

from __future__ import annotations

import base64
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

URL = "https://api.sarvam.ai/text-to-speech"


def speak_hi(text: str, out: Path, speaker: str | None = None, pace: float = 0.95) -> Path:
    key = os.environ.get("SARVAM_API_KEY")
    if not key:
        raise RuntimeError("SARVAM_API_KEY is not set in .env")
    r = httpx.post(URL, timeout=120, headers={"api-subscription-key": key}, json={
        "text": text[:2500], "language_code": "hi-IN", "model": "bulbul:v3",
        "speaker": speaker or os.environ.get("VO_SPEAKER", "shubh"), "pace": pace, "speech_sample_rate": 24000,
    })
    r.raise_for_status()
    out.write_bytes(base64.b64decode(r.json()["audios"][0]))
    return out
