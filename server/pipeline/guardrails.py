"""Code that stands between Claude and the teacher.

Claude proposes; this module verifies. Nothing here asks a model anything.
- has_banned_words / mask_banned: labels we never use about a child, in English and Hindi.
- check_mentions: every mention from a teacher's voice note must cite her real
  sentences; the child is resolved by code from the roster (names.py) and must agree
  with Claude; items must be in her words; labels are masked; confidence is computed.
"""

from __future__ import annotations

import re
import unicodedata

from . import names
from .confidence import note_confidence, note_signals, passes_gate

TAP_WINDOW_BEFORE_S = 8.0   # a tap counts for an answer that starts up to 8 s later
TAP_WINDOW_AFTER_S = 1.0

BANNED = ["weak", "slow", "poor", "dull", "stupid", "lazy", "dumb", "duffer", "backward",
          "कमज़ोर", "कमजोर", "ढीला", "बुद्धू", "मंद", "आलसी", "नालायक", "बेवकूफ", "मूर्ख", "निकम्मा"]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s).replace("़", "").lower()
    return re.sub(r"[^\w\s]", " ", s)


def _words(s: str) -> list[str]:
    return _norm(s).split()


def names_of(child: dict) -> list[str]:
    return [child["first_name"], *child.get("aliases", [])]


def _banned_pattern(w: str) -> str:
    # Latin words match whole words only ("slowly" describes reading, "slow" labels a child);
    # Devanagari labels match anywhere, with or without a nukta (कमज़ोर / कमजोर).
    if w.isascii():
        return rf"\b{re.escape(w)}\b"
    base = unicodedata.normalize("NFC", w).replace("\u093c", "")
    return "".join(re.escape(ch) + "\u093c?" for ch in base)


def has_banned_words(text: str) -> list[str]:
    t = unicodedata.normalize("NFC", text)
    return [w for w in BANNED if re.search(_banned_pattern(w), t, flags=re.I)]


def mask_banned(text: str) -> str:
    t = unicodedata.normalize("NFC", text)
    for w in BANNED:
        t = re.sub(_banned_pattern(w), "•••", t, flags=re.I)
    return t


# ---------------------------------------------------------------------------
# v1: checks on what Claude extracted from the teacher's after-class voice note.
# ---------------------------------------------------------------------------

_ROLL_NEAR = re.compile(r"(\S+)\s*(?:नंबर|नम्बर|number|no)\b|(?:रोल|roll)\s*(?:नंबर|नम्बर|number|no)?\s*(\S+)", re.I)


def _flat(s: str) -> str:
    return " ".join(_norm(s).split())


def _in_text(fragment: str, text: str) -> bool:
    f = _flat(fragment)
    return bool(f) and f in _flat(text)


def _roll_hint(text: str) -> str:
    """'प्रिया ने ... बारह नंबर वाली' -> 'बारह': roll numbers said next to नंबर/roll."""
    return " ".join(g for m in _ROLL_NEAR.finditer(text) for g in m.groups() if g)


_ECHO = re.compile(r"([\w\u0900-\u097f]+)\s+को\s+([\w\u0900-\u097f]+)\s+(?:पढ़|पढ|बोल|बता|read)", re.I)
_SAID_RIGHT = re.compile(r"सही|ठीक|शाबाश|correct|right|बढ़िया", re.I)


def erased_misreading(text: str) -> str | None:
    """'किताब को किताब पढ़ा': the same word on both sides of को. Speech-to-text often turns the
    child's misreading the teacher is quoting into the correct word, so this cannot show 'correct'."""
    for m in _ECHO.finditer(unicodedata.normalize("NFC", text)):
        if _flat(m.group(1)) == _flat(m.group(2)):
            return m.group(0)
    return None


def _item_found(item: str, text: str) -> bool:
    if _in_text(item, text):
        return True
    item_nums, text_nums = names.numbers_in(item), names.numbers_in(text)
    return bool(item_nums) and item_nums <= text_nums  # "32" said as "बत्तीस"


def _item_in_lesson(item: str, lesson: dict) -> bool:
    every = [i for items in lesson["items"].values() for i in items]
    return any(_flat(item) == _flat(i) for i in every) or any(
        names.numbers_in(item) and names.numbers_in(item) == names.numbers_in(i) for i in every)


def check_mentions(mentions: list[dict], sentences: list[dict], roster: list[dict], lesson: dict):
    """Verify every mention Claude extracted from a voice note, and score it in code.

    Returns (records, questions, problems):
    - records: one per kept mention, with the code-resolved child, signals, confidence and a status:
      evidence (passes the gate), check_tomorrow (below it), opinion, absent, unattributed.
    - questions: name mix-ups the teacher can settle with one tap (which Priya? who is this?).
    - problems: (mention_id, action, reason) for the reviewer trace.
    """
    sent = {s["sent_id"]: s["text"] for s in sentences}
    by_id = {c["child_id"]: c for c in roster}
    records, questions, problems = [], [], []
    for m in mentions:
        mid = m["mention_id"]
        missing = [i for i in m["sent_ids"] if i not in sent]
        if missing or not m["sent_ids"]:
            problems.append((mid, "dropped", f"cites sentences that do not exist: {missing or 'none'}"))
            continue
        cited = " ".join(sent[i] for i in m["sent_ids"])
        if m["name_said"] and not _in_text(m["name_said"], cited):
            problems.append((mid, "dropped", "name_said is not in the cited sentences"))
            continue
        r = dict(m)
        if m["teacher_quote"] and not _in_text(m["teacher_quote"], cited):
            problems.append((mid, "quote removed", "teacher_quote is not in the cited sentences"))
            r["teacher_quote"] = ""
        if has_banned_words(r["teacher_quote"]):
            problems.append((mid, "label masked", "the quote contained a label about the child"))
            r["teacher_quote"] = mask_banned(r["teacher_quote"])
        if has_banned_words(r["rationale"]):
            problems.append((mid, "rationale removed", "the rationale used a label"))
            r["rationale"] = ""
        if r["item"] and not _item_found(r["item"], cited):
            problems.append((mid, "item removed", f"item {r['item']!r} is not in her words"))
            r["item"] = ""
        echo = erased_misreading(cited)
        if echo and r["outcome"] == "correct" and not _SAID_RIGHT.search(cited):
            problems.append((mid, "outcome set to unclear",
                             f"{echo!r} repeats the word: speech-to-text may have erased the child's misreading"))
            r["outcome"], r["error_type"] = "unclear", "not_stated"

        # Who did she mean? Code resolves the name itself and must agree with Claude.
        res = names.resolve(m["name_said"], roster)
        if res["status"] == "ambiguous":
            res = names.resolve(m["name_said"] + " " + _roll_hint(cited), roster)
        child = res["child_id"]
        if child and m["child_id"] != child:
            problems.append((mid, "unattributed", f"Claude said {m['child_id']}, the roster says {child}"))
            child, status = None, "disagree"
        else:
            status = res["status"]
        if m["child_id"] and m["child_id"] not in by_id:
            problems.append((mid, "unattributed", f"{m['child_id']} is not on the roster"))
        r["child_id"] = child
        r["attribution"] = status if child else "none"
        r["candidates"] = res["candidates"]
        in_text = bool(r["item"])
        r["signals"] = None if m["kind"] == "absent" else note_signals(
            r, in_text, in_text and _item_in_lesson(r["item"], lesson))

        if child is None:
            r.update(confidence=0.0, status="unattributed")
            if status in ("ambiguous", "unknown", "disagree", "no_name") and m["kind"] in ("observation", "absent"):
                which = bool(res["candidates"])
                questions.append({"mention_id": mid, "name_said": m["name_said"],
                                  "type": "which_child" if which else "who_is_this",
                                  # who_is_this: the nearest-sounding names, offered as suggestions only
                                  "candidates": res["candidates"] if which else names.nearest(m["name_said"], roster)})
            records.append(r)
            continue
        if m["kind"] == "absent":
            r.update(confidence=None, status="absent")
            records.append(r)
            continue
        r["confidence"] = round(note_confidence(r["attribution"], r["signals"]), 3)
        r["status"] = record_status(r)
        records.append(r)
    return records, questions, problems


def record_status(r: dict) -> str:
    """Where a scored mention goes. An opinion never becomes evidence, whatever its score:
    like any claim below the gate it becomes something to listen for tomorrow."""
    if r["kind"] == "absent":
        return "absent"
    if not r["child_id"]:
        return "unattributed"
    if r["kind"] == "opinion":
        return "check_tomorrow"
    return "evidence" if passes_gate(r["confidence"]) else "check_tomorrow"


def settle_attribution(r: dict, child_id: str) -> dict:
    """The teacher tapped which child she meant: re-score the mention in code with her answer."""
    r = dict(r, child_id=child_id, attribution="teacher_confirmed")
    if r["kind"] != "absent":
        r["confidence"] = round(note_confidence("teacher_confirmed", r["signals"]), 3)
    r["status"] = record_status(r)
    return r


def check_class_observations(obs: list[dict], sentences: list[dict]):
    """Remarks about the whole class ("most children struggled with matras"): same grounding as for
    a child (cited sentences exist, quote and item in her words, labels masked). Returns (records, problems)."""
    sent = {s["sent_id"]: s["text"] for s in sentences}
    records, problems = [], []
    for i, o in enumerate(obs, 1):
        mid = f"k{i}"
        if not o["sent_ids"] or any(x not in sent for x in o["sent_ids"]) or not o["skill_code"]:
            problems.append((mid, "dropped", "class remark without real sentences or a skill"))
            continue
        cited = " ".join(sent[x] for x in o["sent_ids"])
        quote = o["teacher_quote"] if o["teacher_quote"] and _in_text(o["teacher_quote"], cited) else ""
        item = o["item"] if o["item"] and _item_found(o["item"], cited) else ""
        records.append({
            "mention_id": mid, "name_said": "", "child_id": None, "kind": "class", "skill_code": o["skill_code"],
            "item": item, "outcome": "incorrect" if o["outcome"] == "struggled" else "correct",
            "error_type": "not_stated", "when": "today", "home_language": "none",
            "teacher_quote": mask_banned(quote), "rationale": "" if has_banned_words(o["rationale"]) else o["rationale"],
            "attribution": "class", "candidates": [], "signals": None, "confidence": None, "status": "class",
            "share": o["share"],
        })
    return records, problems
