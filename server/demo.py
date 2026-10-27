"""The judges' demo: every login gets its own copy of a SYNTHETIC Grade 2 class.

The copy carries eight school days of synthetic teacher notes that were run through the
real pipeline once (eval/seed_demo.py writes samples/synthetic/demo_history.json), plus
the brief for "today". Dates are stored as "school days before today" and rebased at copy
time, so the demo always looks like it is the morning after the last note.
"""

from __future__ import annotations

import json

from . import jobs, store
from .pipeline import planner

FIXTURE = store.ROOT / "samples" / "synthetic" / "demo_history.json"
CLASS = store.ROOT / "samples" / "synthetic" / "demo_class.json"


def fixture() -> dict | None:
    return json.loads(FIXTURE.read_text()) if FIXTURE.exists() else None


def clone_demo() -> str:
    base = json.loads(CLASS.read_text())
    fx = fixture()
    cls = base["class"]
    cid = store.create_class(cls["name"], cls["grade"], cls["school"], base["roster"], base["lesson"], synthetic=True)
    if not fx:
        return cid
    c = store.get_class(cid)
    today = jobs.class_today(c)
    back = planner.school_days_before(today, max(n["back"] for n in fx["notes"]))
    day_of = {k: back[-k].isoformat() for k in range(1, len(back) + 1)}
    for n in fx["notes"]:
        day = day_of[n["back"]]
        nid = store.create_note(cid, day, "sample-text", n["listening"], synthetic=True)
        store.update_note(nid, status="done", transcript=n["transcript"], sentences_json=n["sentences"],
                          claude_json=n["claude"], problems_json=n["problems"], follow_ups_json=n["follow_ups"],
                          usage_json=n["usage"], timings_json=n["timings"])
        store.add_records(nid, cid, day, n["records"])
        for qq, q_id in zip(n["questions"], store.add_questions(nid, cid, n["questions"])):
            if qq.get("answer"):
                _apply_answer(cid, q_id, qq["answer"])
    b = fx.get("brief")
    if b:
        # This morning's brief and its picture are used together, exactly as seeded, so the brief's
        # words always match the lists on screen. From "next morning" on, the live planner takes over.
        src = store.ROOT / b["audio_file"] if b.get("audio_file") else None
        has_audio = bool(src and src.exists())
        store.put_brief(cid, today.isoformat(), status="done", picture_json=b["picture"], brief_json=b["brief"],
                        problems_json=b.get("problems", []), usage_json=b.get("usage"),
                        audio_file=f"{cid}_{today.isoformat()}.mp3" if has_audio else None,
                        audio=src.read_bytes() if has_audio else None)
    return cid


def _apply_answer(class_id: str, q_id: int, answer: str) -> None:
    from .api import settle_question  # late import: api imports demo
    settle_question(class_id, q_id, answer)
