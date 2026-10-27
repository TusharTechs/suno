"""Build the judges' demo history: eight school days of SYNTHETIC teacher notes, run through the
real pipeline (Claude + code checks), then the morning brief for "today".

Writes samples/synthetic/demo_history.json and samples/synthetic/audio/demo_brief.mp3.
Costs roughly 9 Claude calls. Run:  uv run python eval/seed_demo.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["SUNO_VAR"] = tempfile.mkdtemp(prefix="suno-seed-")

from server import jobs, store  # noqa: E402
from server.pipeline import planner  # noqa: E402

LABEL = ("SYNTHETIC. Eight days of after-class voice notes written by Team Sunvai for a fictional Grade 2 "
         "class, run once through SUNO's real pipeline (Claude + code checks) by eval/seed_demo.py. "
         "Not real children, not a real teacher.")

# Notes as speech-to-text would return them (Devanagari, light punctuation). back = school days before today.
NOTES = [
    (8, "आज आरव ने कमल सही पढ़ा। सिमरन ने घर और नमक दोनों जोड़कर पढ़ लिए। पिंकी ने कमल को क म ल पढ़ा, जोड़ नहीं पाई। "
        "अंजलि ने का कि की पढ़ा पर कु पर अटक गई। रवि तो बहुत होशियार है।"),
    (7, "अमन ने पानी सही पढ़ा, जल्दी से। सोनू ने पानी को पनी पढ़ा, मात्रा छोड़ दी। सुरेश आज नहीं आया। "
        "अर्जुन ने मटर सही पढ़ा। रीना ने बतख को ब त ख पढ़ा, फिर मेरे साथ जोड़ा। गोलू ने बत्तीस को तेईस पढ़ा।"),
    (6, "फ़ातिमा ने वाक्य पढ़ लिया पर कमल कहाँ खिलता है पूछा तो नहीं बता पाई, फिर भोजपुरी में पूछा तो तुरंत बता दिया। "
        "प्रिया ने किताब सही पढ़ी। करण ने तेईस और पाँच जोड़कर अट्ठाईस बताया, सही। मोहन ने मछली सही पढ़ी। "
        "पिंकी ने नमक को न म क पढ़ा, जोड़ नहीं पाई।"),
    (5, "नेहा ने कमल का फूल सुंदर है पूरा वाक्य पढ़ा। विकास ने ग और घ में गड़बड़ की, घर को गर पढ़ा। "
        "पूजा ने फूल और नाव सही पढ़े। दीपक ने पंद्रह में से छह घटाकर नौ बताया। सोनू ने किताब को कताब पढ़ा। "
        "सुरेश आज भी नहीं आया।"),
    (4, "राहुल ने संतालीस को चौहत्तर पढ़ा। सलमा थोड़ी कमज़ोर है पढ़ने में। आशा ने मछली पानी में रहती है पढ़ा, अच्छे से। "
        "मनीष ने कि और की में फर्क नहीं किया। इमरान ने बत्तीस में तीन दहाई दो इकाई सही बताया। "
        "अमन ने किताब सही पढ़ी। पिंकी ने घर को घ र पढ़ा, फिर से कोशिश की तो थोड़ा जोड़ा।"),
    (3, "रानी ने बतख सही पढ़ा। गोलू ने संतालीस को चौहत्तर पढ़ा। सीमा ने का कि की कु कू सब सही पढ़े। "
        "अजय ने बीस में से चार घटाकर सोलह बताया। फ़ातिमा को मछली कहाँ रहती है समझ नहीं आया, भोजपुरी में समझाया तो बता दिया। "
        "पीछे वाला लड़का नाव नहीं पढ़ पाया।"),
    (2, "पिंकी ने मटर को म ट र पढ़ा, जोड़ नहीं पाई। सोनू ने मछली को मछल पढ़ा। काजल अक्सर मात्रा में गलती करती है। "
        "सुरेश आया था, उसने कमल सही पढ़ा। करण ने चौदह और तीन जोड़कर सत्रह बताया।"),
    (1, "अमन ने मछली सही पढ़ी, बिना रुके। गोलू ने नब्बे सही पढ़ा पर बत्तीस को फिर तेईस पढ़ा। "
        "मोहन ने आज कुछ शब्द गलत पढ़े। प्रिया ने फूल को फल पढ़ा। गीता ने कमल का फूल सुंदर है अटक अटक कर पढ़ा।"),
]
# Name mix-ups the "teacher" settles with one tap during seeding (the last day's stays open for the judges).
ANSWERS = {6: {"प्रिया": "c12"}}


def main() -> None:
    base = json.loads((ROOT / "samples/synthetic/demo_class.json").read_text())
    cid = store.create_class(base["class"]["name"], 2, base["class"]["school"], base["roster"], base["lesson"],
                             synthetic=True)
    c = store.get_class(cid)
    today = jobs.class_today(c)
    back = planner.school_days_before(today, len(NOTES))
    from server.api import settle_question
    out_notes = []
    for k, text in NOTES:
        day = back[-k]
        pic = jobs.morning_picture(c, day)
        print(f"\n== {day} (back {k}) listening: {[x['child_id'] + ':' + x['item'] for x in pic['listen_today']]}")
        nid = store.create_note(cid, day.isoformat(), "sample-text", pic["listen_today"], synthetic=True)
        jobs.process_note(nid, None, text)
        n = store.get_note(nid)
        if n["status"] != "done":
            raise SystemExit(f"note failed: {n['error']}")
        recs = store.records(cid, nid)
        for r in recs:
            print(f"  {r['name_said']:14} -> {r['child_id']} {r['kind']:11} {r['skill_code']} {r['item']!r} "
                  f"{r['outcome']} conf={r['confidence']} {r['status']}")
        qs = store.questions(cid, nid)
        answers = []
        for qq in qs:
            a = ANSWERS.get(k, {}).get(qq["name_said"])
            if a:
                settle_question(cid, qq["q_id"], a)
            answers.append(a)
        recs = store.records(cid, nid)  # before any answer was applied: the clone replays answers itself
        out_notes.append({
            "back": k, "transcript": n["transcript"], "sentences": n["sentences"], "listening": n["listening"],
            "claude": n["claude"], "problems": n["problems"], "follow_ups": n["follow_ups"],
            "usage": n["usage"], "timings": n["timings"],
            "records": [_unsettled(r, qs, answers) for r in recs],
            "questions": [{"mention_id": qq["mention_id"], "type": qq["type"], "name_said": qq["name_said"],
                           "candidates": qq["candidates"], "answer": a} for qq, a in zip(qs, answers)],
        })
        print(f"  questions: {[(q['name_said'], a) for q, a in zip(qs, answers)]}  usage: {n['usage']}")

    print(f"\n== brief for {today}")
    jobs.make_brief(cid, today.isoformat())
    b = store.get_brief(cid, today.isoformat())
    print(b["status"], b.get("error"))
    print(json.dumps(b["brief"], ensure_ascii=False, indent=1))
    audio_rel = None
    if b.get("audio_file"):
        audio_rel = "samples/synthetic/audio/demo_brief" + Path(b["audio_file"]).suffix
        shutil.copy(store.VAR / "audio" / b["audio_file"], ROOT / audio_rel)
    fixture = {"label": LABEL, "notes": out_notes,
               "brief": {"picture": b["picture"], "brief": b["brief"], "problems": b.get("problems") or [],
                         "usage": b.get("usage"), "audio_file": audio_rel} if b["brief"] else None}
    (ROOT / "samples/synthetic/demo_history.json").write_text(json.dumps(fixture, ensure_ascii=False, indent=1))
    total = sum((n["usage"] or {}).get("usd", 0) for n in out_notes) + ((b.get("usage") or {}).get("usd", 0))
    print(f"\nwrote samples/synthetic/demo_history.json; Claude spend ≈ ${total:.2f}")


def _unsettled(r: dict, qs: list[dict], answers: list) -> dict:
    """Store records as Claude + code first produced them; the clone re-applies the teacher's taps."""
    asked = {q["mention_id"] for q, a in zip(qs, answers) if a}
    r = dict(r)
    if r["mention_id"] in asked:
        r.update(child_id=None, attribution="none", confidence=0.0, status="unattributed")
    return {k: r[k] for k in store.RECORD_FIELDS}


if __name__ == "__main__":
    main()
