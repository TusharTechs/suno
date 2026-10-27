"""The SIMULATED teacher: whom she notices, what she says about them, and how she says it.

Each statement is ground truth: which child she means, what the child actually did, and how
she phrased it (with or without the item, the mistake, a roll number, a label...). Claude then
voices the day's statements as a natural spoken note in her style, sentence by sentence, so we
know exactly which sentence carries which statement.

STYLE ASSUMPTIONS (per teacher persona):
- precise: names the word and the mistake; rarely an opinion or a label.
- brief: names the word, often not the mistake; some opinions.
- impressionistic: often vague or habitual ("hamesha"), opinions, labels such as कमज़ोर.
- hinglish: like brief, mixing English words the way many teachers speak.
"""

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from eval.sim.world import Child, Klass, response  # noqa: E402
from server.pipeline.claude_client import Usage, call_structured  # noqa: E402

STYLES = {
    #               detail mix: item+error, item only, skill only, vague
    "precise":         {"detail": [0.80, 0.12, 0.05, 0.03], "opinions": 0.3, "label": 0.05, "roll": 0.85,
                        "nameless": 0.05, "general": 0.05, "noticed": 6, "adherence": 0.7},
    "brief":           {"detail": [0.40, 0.45, 0.10, 0.05], "opinions": 0.6, "label": 0.10, "roll": 0.6,
                        "nameless": 0.10, "general": 0.10, "noticed": 5, "adherence": 0.5},
    "impressionistic": {"detail": [0.35, 0.20, 0.20, 0.25], "opinions": 1.5, "label": 0.35, "roll": 0.3,
                        "nameless": 0.20, "general": 0.30, "noticed": 5, "adherence": 0.4},
    "hinglish":        {"detail": [0.45, 0.35, 0.12, 0.08], "opinions": 0.6, "label": 0.10, "roll": 0.6,
                        "nameless": 0.10, "general": 0.10, "noticed": 5, "adherence": 0.5},
}
P_ABSENT = 0.12
LABELS = ["कमज़ोर", "ढीला", "weak", "slow"]
OPINIONS_POS = ["बहुत होशियार है", "अच्छा पढ़ता है", "ठीक चल रहा है", "तेज़ है"]
OPINIONS_NEG = ["पढ़ाई में पीछे है", "ध्यान नहीं देता", "पढ़ने में कमज़ोर है", "कुछ नहीं आता"]

_MATRAS = "ािीुूेैोौ"


def _aksharas(word: str) -> list[str]:
    out = []
    for ch in word:
        if out and (ch in _MATRAS + "ंँ़्" or out[-1].endswith("्")):
            out[-1] += ch
        else:
            out.append(ch)
    return out


def misread(item: str, error: str, rng: random.Random) -> str:
    """A plausible version of what the child said, for the teacher to quote."""
    if error == "segments_without_blending":
        return " ".join(_aksharas(item))
    if error == "matra_omitted":
        return "".join(ch for ch in item if ch not in _MATRAS) or item
    if error == "matra_confused":
        return item.translate(str.maketrans("िीुू", "ीिूु"))
    if error == "letter_confusion":
        return item.translate(str.maketrans("घबधभखग", "गवदबकघ"))
    if error == "number_reversal":
        digits = re.findall(r"\d+", item)
        return digits[0][::-1] if digits else item
    if error == "counting_error":
        nums = [int(n) for n in re.findall(r"\d+", item)]
        if len(nums) == 2:
            ans = nums[0] + nums[1] if "+" in item else nums[0] - nums[1]
            return str(ans + rng.choice([-1, 1]))
    return ""


def name_text(c: Child, form: str) -> str:
    return {"first": c.first_name, "first+roll": f"{c.first_name}, रोल {c.roll_no}",
            "nickname_known": c.roster_nickname or c.first_name, "nickname_unknown": c.spoken_nickname or c.first_name,
            "none": "एक बच्चा", "latin": c.latin}[form]


def day_statements(k: Klass, listening: list[dict], focus: list[str], rng: random.Random) -> tuple[list[dict], set[str]]:
    """Ground-truth statements for one day, and who was absent."""
    st = STYLES[k.style]
    absent = {c.child_id for c in k.children if rng.random() < P_ABSENT}
    present = [c for c in k.children if c.child_id not in absent]
    by_id = {c.child_id: c for c in k.children}
    dup_names = {c.first_name for c in k.children if sum(x.first_name == c.first_name for x in k.children) > 1}

    # Whom she notices: some of SUNO's list (adherence), the rest by visibility.
    noticed: list[Child] = []
    for p in listening:
        c = by_id.get(p["child_id"])
        if c and c.child_id not in absent and rng.random() < st["adherence"]:
            noticed.append(c)
    n_total = max(len(noticed), rng.choice([st["noticed"] - 1, st["noticed"], st["noticed"] + 1]))
    pool = [c for c in present if c not in noticed]
    while len(noticed) < n_total and pool:
        w = [c.visibility ** 1.5 for c in pool]
        c = rng.choices(pool, w)[0]
        pool.remove(c)
        noticed.append(c)
    planned_item = {p["child_id"]: (p["skill_code"], p["item"]) for p in listening}

    out, sid = [], 0
    for c in noticed:
        if c.child_id in planned_item and planned_item[c.child_id][0] in k.lesson["items"]:
            skill, item = planned_item[c.child_id]
        else:
            skill = rng.choice(focus)
            item = rng.choice(k.lesson["items"][skill])
        outcome, err = response(c, skill, rng)
        detail = rng.choices(["item_error", "item", "skill", "vague"], st["detail"])[0]
        if outcome == "correct" and detail == "item_error":
            detail = "item"
        when = "general" if rng.random() < st["general"] else "today"
        if c.first_name in dup_names:
            form = "first+roll" if rng.random() < st["roll"] else "first"
        elif c.spoken_nickname:
            form = "nickname_unknown" if rng.random() < 0.7 else "first"
        elif c.roster_nickname and rng.random() < 0.5:
            form = "nickname_known"
        elif rng.random() < st["nameless"]:
            form = "none"
        else:
            form = "latin" if k.style == "hinglish" and rng.random() < 0.3 else "first"
        sid += 1
        out.append({
            "sid": f"t{sid}", "child_id": c.child_id, "name_form": form, "name_text": name_text(c, form),
            "kind": "observation", "skill": skill, "item": item if detail in ("item_error", "item") else "",
            "lesson_item": item, "outcome": outcome, "error_type": err if outcome != "correct" else "none",
            "said_as": misread(item, err, rng) if detail == "item_error" and outcome != "correct" else "",
            "detail": detail, "when": when,
            "label": outcome != "correct" and rng.random() < st["label"],
            "home_language": "helped" if skill == "hi.comprehension" and c.home_language_gap and outcome != "correct" else "none",
        })
    # Opinions about children she did not observe today.
    n_op = int(st["opinions"]) + (rng.random() < st["opinions"] % 1)
    for c in rng.sample([c for c in present if c not in noticed], min(n_op, len(present) - len(noticed))):
        sid += 1
        neg = c.reading <= 2
        text = rng.choice(OPINIONS_NEG if neg else OPINIONS_POS)
        form = "first+roll" if c.first_name in dup_names else "first"
        out.append({"sid": f"t{sid}", "child_id": c.child_id, "name_form": form, "name_text": name_text(c, form),
                    "kind": "opinion", "opinion": text, "skill": None, "item": "", "outcome": "unclear",
                    "error_type": "not_stated", "detail": "vague", "when": "general",
                    "label": any(lbl in text for lbl in LABELS), "home_language": "none"})
    # She mentions some absent children.
    for cid in rng.sample(sorted(absent), min(len(absent), rng.choice([0, 1, 2]))):
        c = by_id[cid]
        sid += 1
        form = "first+roll" if c.first_name in dup_names else "first"
        out.append({"sid": f"t{sid}", "child_id": cid, "name_form": form, "name_text": name_text(c, form),
                    "kind": "absent", "skill": None, "item": "", "outcome": "unclear", "error_type": "not_stated",
                    "detail": "vague", "when": "today", "label": False, "home_language": "none"})
    rng.shuffle(out)
    for s in out:
        s["expect"] = expectation(s, dup_names, by_id)
    return out, absent


def expectation(s: dict, dup_names: set[str], by_id: dict) -> str:
    """What a careful human reviewer would do with this statement (not SUNO's own formula)."""
    if s["kind"] == "absent":
        return "absent"
    if s["kind"] == "opinion":
        return "not_evidence"
    unclear_who = s["name_form"] in ("none", "nickname_unknown") or (
        s["name_form"] == "first" and by_id[s["child_id"]].first_name in dup_names)
    if s["detail"] == "vague":
        return "not_evidence"
    if s["detail"] == "skill":
        # A skill with no word or sum ("did the addition fine", "got the vowel signs wrong") can't be
        # checked: SUNO holds it back as "check tomorrow" (decision 32). Not scored either way.
        base = "either"
    else:
        base = "evidence"
    return f"ask_then_{base}" if unclear_who else base


VOICE_PROMPT = """You play a Grade 2 teacher in a Hindi-medium government school in Uttar Pradesh, recording a short voice note on her phone after the reading period. You receive the things she noticed today, each with an id. Write what she says, sentence by sentence, in natural spoken Hindi in Devanagari (the way it would sound, not formal written Hindi).

Rules:
- One or two short sentences per statement, tagged with that statement's id. Cover every statement.
- Refer to the child exactly as `name_text` (if it is "एक बच्चा", do not name the child at all).
- If `item` is given, say it exactly. If `said_as` is given, say that the child read the item as `said_as` (for example "कमल को क म ल पढ़ा"). If `item` is empty, do not mention any word or number: speak only generally about the skill (detail "skill") or very vaguely (detail "vague").
- For detail "item": say whether it was right or wrong, but not how it went wrong.
- outcome partial: the child got part of it, or only with help.
- when "general": speak of it as a habit ("हमेशा", "अक्सर"), not today.
- If `label` is true, use one of these words about the child naturally: कमज़ोर, ढीला, weak, slow.
- If `home_language` is "helped": the child did not understand in Hindi but answered when you asked in Bhojpuri.
- kind "opinion": say the opinion given, nothing specific. kind "absent": the child did not come today.
- You may add at most one sentence about the whole class (id null).
- Style: {style}
"""
STYLE_TEXT = {
    "precise": "clear and specific, calm.",
    "brief": "quick and to the point, as if in a hurry.",
    "impressionistic": "chatty and general, a bit tired, mixes impressions with what happened.",
    "hinglish": "mixes English words the way many teachers do (correct, wrong, blending, matra, absent, number, sentence), written in Devanagari or Latin as spoken.",
}
VOICE_SCHEMA = {
    "type": "object",
    "properties": {"sentences": {"type": "array", "items": {
        "type": "object",
        "properties": {"sid": {"anyOf": [{"type": "string"}, {"type": "null"}]}, "text": {"type": "string"}},
        "required": ["sid", "text"], "additionalProperties": False}}},
    "required": ["sentences"], "additionalProperties": False,
}


def voice_note(statements: list[dict], style: str, usage: Usage | None = None) -> list[dict]:
    keep = ["sid", "name_text", "kind", "item", "said_as", "outcome", "detail", "when", "label", "home_language",
            "opinion", "skill"]
    payload = [{k: s.get(k) for k in keep if s.get(k) not in (None, "")} for s in statements]
    out = call_structured(prompt=VOICE_PROMPT.replace("{style}", STYLE_TEXT[style]), schema=VOICE_SCHEMA,
                          stable_context="(simulation)", request=json.dumps(payload, ensure_ascii=False),
                          effort="low", max_tokens=8000, usage=usage)
    return out["sentences"]
