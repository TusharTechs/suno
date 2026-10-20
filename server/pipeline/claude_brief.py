"""Claude call 3: write the morning brief, then check it in code before anyone hears it.

Code decides the facts (tracker status, call-ons, Silence Ledger); Claude only
words them. The check rejects a brief that names a child as needing support
without tracker backing, changes the call-on or silent lists, uses an unknown
activity or child, runs too long for text-to-speech, or uses a banned word.
One rewrite is attempted with the problems listed; after that it fails closed.
"""

from __future__ import annotations

import json

from .claude_client import ClaudeOutputError, Usage, call_structured, load_prompt, load_schema
from .guardrails import has_banned_words

PROMPT = "brief.v1.md"
SCHEMA = "brief.v1.json"
MAX_CHARS = 2000


def check_brief(b: dict, roster_ids: set[str], needs_support: set[tuple[str, str]],
                call_on: list[str], silent: list[str], activity_ids: set[str]) -> list[str]:
    problems = []
    ids = {c for x in b["needs_support"] for c in [x["child_id"]]}
    ids |= {c for x in b["stuck_where"] + b["today"] for c in x["child_ids"]}
    ids |= set(b["call_on"]) | set(b["silent"]) | {x["child_id"] for x in b["check_tomorrow"]}
    if ids - roster_ids:
        problems.append(f"unknown child ids: {sorted(ids - roster_ids)}")
    claimed = {(x["child_id"], x["skill_code"]) for x in b["needs_support"]}
    if claimed - needs_support:
        problems.append(f"needs-support claims the tracker does not back: {sorted(claimed - needs_support)}")
    stuck = {(c, x["skill_code"]) for x in b["stuck_where"] for c in x["child_ids"]}
    if stuck - needs_support:
        problems.append(f"stuck_where names children the tracker does not back: {sorted(stuck - needs_support)}")
    if b["call_on"] != call_on:
        problems.append("call_on must be exactly the planner's list")
    if sorted(b["silent"]) != sorted(silent):
        problems.append("silent must be exactly the Silence Ledger")
    if {x["activity_id"] for x in b["today"]} - activity_ids:
        problems.append("today uses an activity that is not in the list")
    if len(b["text_hi"]) > MAX_CHARS:
        problems.append(f"text_hi is {len(b['text_hi'])} characters; limit {MAX_CHARS}")
    banned = has_banned_words(json.dumps(b, ensure_ascii=False))
    if banned:
        problems.append(f"banned words: {banned}")
    return problems


def write_brief(roster: list[dict], facts: dict, activities: list[dict], usage: Usage | None = None) -> dict:
    """facts: tracker, evidence_summary, check_tomorrow, call_on, silent (all computed in code)."""
    stable = ("ROSTER\n" + json.dumps(roster, ensure_ascii=False, sort_keys=True)
              + "\n\nACTIVITIES\n" + json.dumps(activities, ensure_ascii=False, sort_keys=True))
    needs = {(t["child_id"], t["skill"]) for t in facts["tracker"] if t["status"] == "needs support"}
    request = "FACTS\n" + json.dumps(facts, ensure_ascii=False, indent=1)
    for attempt in range(2):
        brief = call_structured(prompt=load_prompt(PROMPT), schema=load_schema(SCHEMA),
                                stable_context=stable, request=request, usage=usage)
        problems = check_brief(brief, {c["child_id"] for c in roster}, needs, facts["call_on"],
                               facts["silent"], {a["activity_id"] for a in activities})
        if not problems:
            return brief
        request += "\n\nYOUR PREVIOUS BRIEF WAS REJECTED BY THE CHECKS. Fix exactly these problems:\n- " + "\n- ".join(problems)
    raise ClaudeOutputError(f"brief failed checks twice: {problems}")
