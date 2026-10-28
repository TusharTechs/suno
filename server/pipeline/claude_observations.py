"""Claude call 1 (v1): turn the teacher's after-class voice note into per-child observations.

Input: the roster, skill ladder and this week's lesson (a cached, stable prefix), then
today's listening list and the note as numbered sentences.
Output: mentions (schemas/observations.v1.json), then verified and scored in code by
guardrails.check_mentions. Claude never decides the child on its own, and never sets confidence.
"""

from __future__ import annotations

import json
import os

from .claude_client import Usage, call_structured, load_prompt, load_schema
from .config import SKILLS
from .guardrails import check_class_observations, check_mentions, has_banned_words

PROMPT = "observations.v3.md"
SCHEMA = "observations.v2.json"
EFFORT = os.environ.get("SUNO_NOTE_EFFORT", "high")


def _stable_context(roster: list[dict], lesson: dict) -> str:
    # Sorted keys keep the cached prefix byte-identical across notes from the same class.
    ladder = [{"code": s["code"], "skill": s["label_en"], "example": s["example"]} for s in SKILLS["skills"]]
    errors = [{"code": e["code"], "meaning": e["label_en"]} for e in SKILLS["error_types"]]
    return ("ROSTER\n" + json.dumps(roster, ensure_ascii=False, sort_keys=True)
            + "\n\nSKILL LADDER\n" + json.dumps(ladder, ensure_ascii=False)
            + "\n\nMISTAKE TYPES\n" + json.dumps(errors, ensure_ascii=False)
            + "\n\nTHIS WEEK'S LESSON\n" + json.dumps(lesson, ensure_ascii=False, sort_keys=True))


def _request(sentences: list[dict], listening: list[dict], roster: list[dict]) -> str:
    kid = {c["child_id"]: c for c in roster}
    plan = "\n".join(f'- {p["child_id"]} ({kid[p["child_id"]]["first_name"]}, roll {kid[p["child_id"]]["roll_no"]}): '
                     f'{p["item"]}' for p in listening if p["child_id"] in kid)
    note = "\n".join(f'{s["sent_id"]}: {s["text"]}' for s in sentences)
    return "TODAY'S LISTENING LIST\n" + (plan or "(none)") + "\n\nTHE NOTE\n" + note


def extract(sentences: list[dict], roster: list[dict], lesson: dict, listening: list[dict],
            usage: Usage | None = None) -> dict:
    """Returns {"raw": Claude's output, "records", "questions", "follow_ups", "problems"}."""
    if not sentences:
        return {"raw": {"mentions": [], "class_observations": [], "follow_ups": []}, "records": [], "questions": [],
                "follow_ups": [], "problems": []}
    raw = call_structured(prompt=load_prompt(PROMPT), schema=load_schema(SCHEMA),
                          stable_context=_stable_context(roster, lesson),
                          request=_request(sentences, listening, roster), effort=EFFORT, usage=usage)
    records, questions, problems = check_mentions(raw["mentions"], sentences, roster, lesson)
    class_records, class_problems = check_class_observations(raw.get("class_observations", []), sentences)
    records += class_records
    problems += class_problems
    follow_ups = []
    for f in raw["follow_ups"][:2]:
        if has_banned_words(f["question_hi"]):
            problems.append(("follow_up", "dropped", "follow-up question used a label"))
        else:
            follow_ups.append(f)
    return {"raw": raw, "records": records, "questions": questions, "follow_ups": follow_ups,
            "problems": [list(p) for p in problems]}
