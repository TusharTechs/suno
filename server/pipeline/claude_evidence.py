"""Claude call 2: turn verified moments into evidence records, then score them in code.

Claude decides skill, outcome and error type. Code checks every record points at
a real, attributed moment, then computes confidence from measured signals and
applies the gate. Below the gate a claim becomes "check tomorrow".
"""

from __future__ import annotations

import json

from .claude_client import Usage, call_structured, load_prompt, load_schema
from .confidence import answer_match, confidence, passes_gate

PROMPT = "evidence.v1.md"
SCHEMA = "evidence.v1.json"


def extract_evidence(moments: list[dict], segments: list[dict], usage: Usage | None = None):
    """Returns (claims, check_tomorrow, problems)."""
    usable = [m for m in moments if m["addressee_child_id"] and m["response_type"] == "individual"
              and m["response_seg_ids"]]
    if not usable:
        return [], [], []
    out = call_structured(
        prompt=load_prompt(PROMPT),
        schema=load_schema(SCHEMA),
        stable_context="(skill ladder is in the instructions)",
        request="MOMENTS\n" + json.dumps(usable, ensure_ascii=False, indent=1),
        usage=usage,
    )
    by_id = {m["moment_id"]: m for m in usable}
    claims, later, problems = [], [], []
    for e in out["evidence"]:
        m = by_id.get(e["moment_id"])
        if m is None or e["child_id"] != m["addressee_child_id"]:
            problems.append((e["moment_id"], "dropped", "evidence for a moment or child that was not verified"))
            continue
        match = answer_match(m["answer_heard"], m["expected_item"])
        c = confidence(m["attribution_basis"], e["outcome"], match, m["teacher_uptake"], m["teacher_said_answer"])
        record = e | {
            "item": m["expected_item"], "heard": m["answer_heard"], "segment_ids": m["response_seg_ids"],
            "signals": {"attribution": m["attribution_basis"], "expected_match": round(match, 2),
                        "teacher_uptake": m["teacher_uptake"], "teacher_said_answer": m["teacher_said_answer"]},
            "confidence": round(c, 3),
        }
        (claims if passes_gate(c) else later).append(record)
    return claims, later, problems
