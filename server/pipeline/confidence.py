"""Confidence is computed here, from measured signals. Claude never sets it.

v0 uses hand-set weights. Once labelled moments exist (proxy sessions, ASER),
eval/ refits the weights and picks the gate as the lowest value that keeps
precision at or above the target. Until then the gate is 0.75 (CONFIDENCE_GATE).
"""

from __future__ import annotations

import os
import unicodedata
from difflib import SequenceMatcher

GATE = float(os.environ.get("CONFIDENCE_GATE", "0.75"))

# How sure we are about WHO answered, by how it was established (F1/F3 decide these).
ATTRIBUTION = {"tap_confirm": 0.98, "name_call": 0.90, "none": 0.0}

# How strongly the teacher's reaction supports each outcome.
UPTAKE_SUPPORT = {
    "correct": {"praise": 1.0, "repeat": 0.6, "neutral": 0.5, "none": 0.5, "correction": 0.0},
    "incorrect": {"correction": 1.0, "repeat": 0.5, "neutral": 0.4, "none": 0.4, "praise": 0.0},
}
W_MATCH, W_UPTAKE, W_ECHO = 0.45, 0.35, 0.20


def answer_match(heard: str, expected: str | None) -> float:
    """0-1 similarity of what the child said to the expected item (Devanagari or Latin)."""
    def norm(s: str) -> str:
        s = unicodedata.normalize("NFC", s).replace("़", "").lower()
        return "".join(ch for ch in s if unicodedata.category(ch)[0] in "LM")
    if not expected or not heard:
        return 0.0
    a, b = norm(heard), norm(expected)
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def outcome_confidence(outcome: str, match: float, uptake: str, teacher_said_answer: bool) -> float:
    """How well the signals agree with the claimed outcome, 0-1."""
    if outcome not in UPTAKE_SUPPORT:
        return 0.0  # partial and unclear never pass the gate as a named claim in v0
    match_support = match if outcome == "correct" else 1.0 - match
    # If the teacher said the word first, a "correct" answer may only be an echo.
    echo_support = (0.0 if teacher_said_answer else 1.0) if outcome == "correct" else 1.0
    return W_MATCH * match_support + W_UPTAKE * UPTAKE_SUPPORT[outcome][uptake] + W_ECHO * echo_support


def confidence(attribution_basis: str, outcome: str, match: float, uptake: str, teacher_said_answer: bool) -> float:
    return ATTRIBUTION.get(attribution_basis, 0.0) * outcome_confidence(outcome, match, uptake, teacher_said_answer)


def passes_gate(c: float) -> bool:
    return c >= GATE
