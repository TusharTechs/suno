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


# ---------------------------------------------------------------------------
# v1: confidence for what the teacher reports in her after-class voice note.
#
# The teacher's ear is the sensor; this scores how checkable her statement is.
# A specific observation ("Pinki read कमल as क-म-ल") can pass the gate. A general
# opinion ("Ravi achha padhta hai", "Sonu is weak") can never pass: it becomes a
# question for tomorrow. Hand-set weights (v0); refit on labelled notes in eval/.
# ---------------------------------------------------------------------------

# How sure we are WHICH child she meant, by how code resolved the name (names.resolve).
NOTE_ATTRIBUTION = {"teacher_confirmed": 0.99, "roll_number": 0.98, "unique": 0.95,
                    "ambiguous": 0.0, "unknown": 0.0, "no_name": 0.0}
RECENCY = {"today": 1.0, "earlier": 0.7, "general": 0.3}
W_SPECIFIC, W_CONCRETE, W_RECENT = 0.5, 0.3, 0.2


def note_signals(m: dict, item_in_transcript: bool, item_in_lesson: bool) -> dict:
    """The measurable parts of one verified mention. Every value is computed here, not by Claude."""
    if m["kind"] != "observation" or m["outcome"] == "unclear":
        specificity = 0.2
    elif item_in_transcript:
        specificity = 1.0 if item_in_lesson else 0.85
    elif m["skill_code"]:
        # A skill named without a word or sum ("did the addition work fine") can't be checked:
        # it stays just below the gate and becomes "listen again tomorrow" (real-speech test, 27 Oct).
        specificity = 0.5
    else:
        specificity = 0.2
    if m["outcome"] == "correct":
        concreteness = 1.0
    elif m["outcome"] in ("incorrect", "partial"):
        concreteness = {"not_stated": 0.4, "other": 0.7}.get(m["error_type"], 1.0)
    else:
        concreteness = 0.0
    if m["kind"] == "opinion":
        concreteness = min(concreteness, 0.4)
    return {"specificity": specificity, "concreteness": concreteness, "recency": RECENCY[m["when"]]}


def note_confidence(attribution: str, signals: dict) -> float:
    a = NOTE_ATTRIBUTION.get(attribution, 0.0)
    return a * (W_SPECIFIC * signals["specificity"] + W_CONCRETE * signals["concreteness"]
                + W_RECENT * signals["recency"])
