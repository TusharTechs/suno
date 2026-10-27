"""Claude call 2 (v1): word the morning brief, then check it in code before the teacher hears it.

Code decides every fact (planner.picture): who needs support with what, whom to listen to
today and with which item, who has not been described. Claude only puts them into simple
spoken Hindi and plain English. The check rejects a brief that names a child as needing
support without tracker backing, changes the listening list or the Silence Ledger, puts a
child in a group for a skill they don't need, uses an unknown activity or child, runs too
long for text-to-speech, or uses a banned word. One rewrite is attempted with the problems
listed; after that it fails closed and the app shows the code-built facts without prose.
"""

from __future__ import annotations

import json
import os

from .claude_client import ClaudeOutputError, Usage, call_structured, load_prompt, load_schema
from .config import ACTIVITIES, SKILL_BY_CODE, SKILLS
from .guardrails import has_banned_words

PROMPT = "brief.v3.md"
SCHEMA = "brief.v2.json"
MAX_CHARS_HI = 1800
MAX_CHARS_EN = 900
EFFORT = os.environ.get("SUNO_BRIEF_EFFORT", "medium")


def facts_for_brief(roster: list[dict], pic: dict, recent_evidence: list[dict]) -> dict:
    name = {c["child_id"]: c["first_name"] for c in roster}
    shared = {n for n in name.values() if list(name.values()).count(n) > 1}
    roll = {c["child_id"]: c["roll_no"] for c in roster}

    def who(cid: str) -> dict:
        d = {"child_id": cid, "first_name": name[cid]}
        if name[cid] in shared:
            d["roll_no"] = roll[cid]
        return d

    on_track: dict[str, int] = {}
    for x in pic["on_track"]:
        on_track[x["skill_code"]] = on_track.get(x["skill_code"], 0) + 1
    ev_by = {}
    for r in recent_evidence:
        ev_by.setdefault((r["child_id"], r["skill_code"]), []).append(r["rationale"] or r["item"])
    return {
        "class_size": len(roster),
        "heard_this_week": len(pic["heard_this_week"]),
        "needs_support": [who(x["child_id"]) | {"skill_code": x["skill_code"],
                                                "skill": SKILL_BY_CODE[x["skill_code"]]["label_hi"],
                                                "evidence": ev_by.get((x["child_id"], x["skill_code"]), [])[-3:]}
                          for x in pic["needs_support"]],
        "on_track_by_skill": {SKILL_BY_CODE[s]["label_hi"]: n for s, n in on_track.items()},
        "levels": _levels(pic, who),
        "listen_today": [who(x["child_id"]) | {"item": x["item"], "reason": x["reason"],
                                               "skill": SKILL_BY_CODE[x["skill_code"]]["label_hi"]}
                         | ({"also": x["also"]["item"]} if x.get("also") else {})
                         for x in pic["listen_today"]],
        "silent": [who(c) for c in pic["silent"]],
        "language_flags": [who(x["child_id"]) | {"signal": x["signal"]} for x in pic["language_flags"]],
        "recent_evidence": [who(r["child_id"]) | {"skill_code": r["skill_code"], "item": r["item"],
                                                  "outcome": r["outcome"], "what": r["rationale"], "day": r["day"]}
                            for r in recent_evidence[-40:]],
    }


def _levels(pic: dict, who) -> dict:
    """{area: {level label: [children]}} for children whose level SUNO is sure of."""
    labels = {a["area"]: a for a in SKILLS["areas"]}
    out: dict = {}
    for cid, areas in pic.get("levels", {}).items():
        for area, v in areas.items():
            if v["level"] is not None:
                lab = labels[area]["levels"][v["level"]]["label_hi"]
                out.setdefault(labels[area]["label_hi"], {}).setdefault(lab, []).append(who(cid)["first_name"])
    return out


def check_brief(b: dict, roster_ids: set[str], pic: dict) -> list[str]:
    problems = []
    needs = {(x["child_id"], x["skill_code"]) for x in pic["needs_support"]}
    acts = {a["activity_id"]: a for a in ACTIVITIES}
    ids = {x["child_id"] for x in b["needs_support"] + b["listen_today"]}
    ids |= {c for x in b["stuck_where"] + b["today"] for c in x["child_ids"]} | set(b["silent"])
    if ids - roster_ids:
        problems.append(f"unknown child ids: {sorted(ids - roster_ids)}")
    claimed = {(x["child_id"], x["skill_code"]) for x in b["needs_support"]}
    if claimed - needs:
        problems.append(f"needs_support claims the tracker does not back: {sorted(claimed - needs)}")
    stuck = {(c, x["skill_code"]) for x in b["stuck_where"] for c in x["child_ids"]}
    if stuck - needs:
        problems.append(f"stuck_where names children the tracker does not back: {sorted(stuck - needs)}")
    for g in b["today"]:
        a = acts.get(g["activity_id"])
        if a is None:
            problems.append(f"today uses an activity that is not in the list: {g['activity_id']}")
            continue
        off = [c for c in g["child_ids"] if not any((c, s) in needs for s in a["skills"])]
        if off:
            problems.append(f"group {g['group']!r}: {off} do not need support with what {g['activity_id']} practises")
    want = [(x["child_id"], x["item"]) for x in pic["listen_today"]]
    if [(x["child_id"], x["item"]) for x in b["listen_today"]] != want:
        problems.append("listen_today must be exactly the planner's list, same order and items")
    if sorted(b["silent"]) != sorted(pic["silent"]):
        problems.append("silent must be exactly the Silence Ledger")
    if len(b["text_hi"]) > MAX_CHARS_HI:
        problems.append(f"text_hi is {len(b['text_hi'])} characters; keep it under 1,500")
    if len(b["summary_en"]) > MAX_CHARS_EN:
        problems.append(f"summary_en is {len(b['summary_en'])} characters; keep it under 700")
    banned = has_banned_words(json.dumps(b, ensure_ascii=False))
    if banned:
        problems.append(f"banned words: {banned}")
    return problems


def write_brief(roster: list[dict], pic: dict, recent_evidence: list[dict],
                usage: Usage | None = None) -> tuple[dict, list[str]]:
    """Returns (brief, problems_fixed_on_rewrite). Raises ClaudeOutputError if it fails twice."""
    stable = ("ROSTER\n" + json.dumps(roster, ensure_ascii=False, sort_keys=True)
              + "\n\nACTIVITIES\n" + json.dumps(ACTIVITIES, ensure_ascii=False, sort_keys=True))
    request = "FACTS\n" + json.dumps(facts_for_brief(roster, pic, recent_evidence), ensure_ascii=False, indent=1)
    first_problems: list[str] = []
    for attempt in range(2):
        b = call_structured(prompt=load_prompt(PROMPT), schema=load_schema(SCHEMA), stable_context=stable,
                            request=request, effort=EFFORT, max_tokens=16000, usage=usage)
        problems = check_brief(b, {c["child_id"] for c in roster}, pic)
        if not problems:
            return b, first_problems
        first_problems = problems
        request += ("\n\nYOUR PREVIOUS BRIEF WAS REJECTED BY THE CHECKS. Write it again and fix exactly these:\n- "
                    + "\n- ".join(problems))
    raise ClaudeOutputError(f"brief failed checks twice: {problems}")
