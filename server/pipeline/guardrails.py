"""Code that stands between Claude and the teacher.

Claude proposes; this module verifies. Nothing here asks a model anything.
- check_moments: every moment must cite real segments, and every attribution
  must be backed by a tap or a unique name actually present in the transcript.
  An attribution that fails is removed (the moment stays, unattributed).
- has_banned_words: labels we never use about a child, in English and Hindi.
"""

from __future__ import annotations

import re
import unicodedata

TAP_WINDOW_BEFORE_S = 8.0   # a tap counts for an answer that starts up to 8 s later
TAP_WINDOW_AFTER_S = 1.0

BANNED = ["weak", "slow", "poor", "dull", "stupid", "कमज़ोर", "कमजोर", "ढीला", "कमजोर बच्चा", "बुद्धू", "मंद"]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s).replace("़", "").lower()
    return re.sub(r"[^\w\s]", " ", s)


def _words(s: str) -> list[str]:
    return _norm(s).split()


def names_of(child: dict) -> list[str]:
    return [child["first_name"], *child.get("aliases", [])]


def roster_matches(word_seq: list[str], roster: list[dict]) -> set[str]:
    """child_ids whose first name or alias appears as a whole word in word_seq."""
    found = set()
    for c in roster:
        for n in names_of(c):
            nw = _words(n)
            if any(word_seq[i:i + len(nw)] == nw for i in range(len(word_seq) - len(nw) + 1)):
                found.add(c["child_id"])
    return found


def check_moments(moments: list[dict], segments: list[dict], taps: list[dict], roster: list[dict]):
    """Returns (kept, problems). Kept moments have verified attributions or none."""
    seg = {s["seg_id"]: s for s in segments}
    by_id = {c["child_id"]: c for c in roster}
    kept, problems = [], []
    for m in moments:
        mid = m["moment_id"]
        ids = m["prompt_seg_ids"] + m["response_seg_ids"] + m["uptake_seg_ids"]
        missing = [i for i in ids if i not in seg]
        if missing:
            problems.append((mid, "dropped", f"cites segments that do not exist: {missing}"))
            continue
        if any(seg[i]["speaker"] != "teacher" for i in m["prompt_seg_ids"] + m["uptake_seg_ids"]):
            problems.append((mid, "dropped", "prompt or uptake segment is not the teacher"))
            continue
        responses = [seg[i] for i in m["response_seg_ids"]]
        heard = " ".join(r["text"] for r in responses)
        if m["answer_heard"] and _norm(m["answer_heard"]).strip() not in _norm(heard):
            problems.append((mid, "dropped", "answer_heard is not in the response segments"))
            continue
        m = dict(m)
        reason = _attribution_problem(m, responses, seg, taps, roster, by_id)
        if reason:
            problems.append((mid, "unattributed", reason))
            m["addressee_child_id"], m["attribution_basis"] = None, "none"
        kept.append(m)
    return kept, problems


def _attribution_problem(m, responses, seg, taps, roster, by_id) -> str | None:
    child = m["addressee_child_id"]
    basis = m["attribution_basis"]
    if child is None:
        return None if basis == "none" else "basis given without a child"
    if child not in by_id:
        return f"{child} is not on the roster"
    if not responses:
        return None  # called but no answer: no evidence either way
    if m["response_type"] != "individual" or any(r["speaker"] != "child" for r in responses):
        return "answer is not a single child's voice"
    t_answer = min(r["t0"] for r in responses)
    near = [t for t in taps if t_answer - TAP_WINDOW_BEFORE_S <= t["t"] <= t_answer + TAP_WINDOW_AFTER_S]
    last_tap = max(near, key=lambda t: t["t"]) if near else None  # the tap that marks this answer
    if last_tap and last_tap["child_id"] != child:
        return "the tap for this answer points to a different child"
    if basis == "tap_confirm":
        return None if last_tap else "no matching tap near the answer"
    if basis == "name_call":
        teacher_text = " ".join(seg[i]["text"] for i in m["prompt_seg_ids"] + m["uptake_seg_ids"])
        quote = m["name_quote"]
        if not quote or _norm(quote).strip() not in _norm(teacher_text):
            return "name_quote is not in the teacher's words"
        qw = _words(quote)
        named = roster_matches(qw, roster)
        if child not in named:
            return "name_quote does not name this child"
        same_name = {c["child_id"] for c in roster
                     if {_norm(n).strip() for n in names_of(c)} & {_norm(n).strip() for n in names_of(by_id[child])}}
        if named - same_name:
            return "the quote names more than one child"
        if len(same_name) > 1 and str(by_id[child]["roll_no"]) not in qw:
            return "shared first name with no roll number"
        return None
    return "unknown attribution basis"


def has_banned_words(text: str) -> list[str]:
    t = unicodedata.normalize("NFC", text).lower()
    return [w for w in BANNED if w.lower() in t]
