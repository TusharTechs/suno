"""Planner (Silence Ledger, listening list, naming rule) and the brief checks. No model calls."""

import json
from datetime import date
from pathlib import Path

from server.pipeline import planner
from server.pipeline.brief import check_brief

ROOT = Path(__file__).resolve().parents[1]
DEMO = json.loads((ROOT / "samples/synthetic/demo_class.json").read_text())
ROSTER, LESSON = DEMO["roster"], DEMO["lesson"]
TODAY = date(2026, 10, 28)  # a Wednesday
DAYS = planner.school_days_before(TODAY, 5)


def rec(child, day, skill="hi.blend_no_matra", outcome="incorrect", status="evidence", kind="observation",
        conf=0.95, item="कमल", when="today", **kw):
    return {"child_id": child, "day": day.isoformat(), "skill_code": skill, "outcome": outcome, "status": status,
            "kind": kind, "confidence": conf, "item": item, "when": when, "home_language": "none",
            "teacher_quote": "", "feedback": None, **kw}


def test_school_days_skip_sunday():
    assert date(2026, 10, 25) not in planner.school_days_before(TODAY, 6)  # Sunday 25 Oct
    assert planner.next_school_day(date(2026, 10, 24)) == date(2026, 10, 26)


def test_naming_needs_three_moments_over_two_days():
    two = [rec("c04", DAYS[-1]), rec("c04", DAYS[-1])]
    assert planner.picture(ROSTER, LESSON, two, TODAY)["needs_support"] == []
    three = two + [rec("c04", DAYS[-2])]
    ns = planner.picture(ROSTER, LESSON, three, TODAY)["needs_support"]
    assert [(x["child_id"], x["skill_code"]) for x in ns] == [("c04", "hi.blend_no_matra")]


def test_teacher_rejection_removes_evidence():
    three = [rec("c04", DAYS[-1]), rec("c04", DAYS[-1]), rec("c04", DAYS[-2], feedback="down")]
    assert planner.picture(ROSTER, LESSON, three, TODAY)["needs_support"] == []


def test_below_gate_records_never_count():
    recs = [rec("c04", d, status="check_tomorrow", conf=0.5) for d in DAYS]
    assert planner.picture(ROSTER, LESSON, recs, TODAY)["needs_support"] == []


def test_silence_ledger_is_everyone_not_described_today_style():
    recs = [rec("c04", DAYS[-1]), rec("c06", DAYS[-1], when="general")]
    silent = planner.picture(ROSTER, LESSON, recs, TODAY)["silent"]
    assert "c04" not in silent and "c06" in silent and len(silent) == len(ROSTER) - 1


def test_absent_all_week_is_not_silent():
    recs = [rec("c07", d, status="absent", kind="absent", skill=None, conf=None) for d in DAYS] + \
           [rec("c04", d) for d in DAYS]
    assert "c07" not in planner.picture(ROSTER, LESSON, recs, TODAY)["silent"]


def test_listening_list_confirms_first_and_skips_yesterday():
    recs = [rec("c15", DAYS[-1], status="check_tomorrow", conf=0.4, item="", skill="hi.matras",
                teacher_quote="काजल अक्सर मात्रा में गलती करती है")]
    plan = planner.picture(ROSTER, LESSON, recs, TODAY, yesterday_list={"c01", "c02"})["listen_today"]
    assert plan[0]["child_id"] == "c15" and plan[0]["reason"] == "confirm" and plan[0]["item"]
    assert {"c01", "c02"}.isdisjoint({p["child_id"] for p in plan[1:]})
    assert len(plan) == planner.LISTEN_PER_DAY
    every_item = {i for items in LESSON["items"].values() for i in items}
    assert all(p["item"] in every_item for p in plan)


def test_language_flag():
    recs = [rec("c11", DAYS[-1], skill="hi.comprehension", home_language="helped")]
    assert planner.picture(ROSTER, LESSON, recs, TODAY)["language_flags"][0]["child_id"] == "c11"


# ---- brief checks ------------------------------------------------------------

def pic_with_pinki():
    recs = [rec("c04", DAYS[-1]), rec("c04", DAYS[-1]), rec("c04", DAYS[-2])]
    return planner.picture(ROSTER, LESSON, recs, TODAY)


def good_brief(pic):
    return {"class_plan": [], "needs_support": [{"child_id": "c04", "skill_code": "hi.blend_no_matra"}],
            "stuck_where": [{"skill_code": "hi.blend_no_matra", "child_ids": ["c04"], "what_hi": "क-म-ल जोड़ नहीं पाती"}],
            "today": [{"group": "A", "child_ids": ["c04"], "activity_id": "act-blend-slide", "minutes": 10}],
            "listen_today": [{"child_id": x["child_id"], "item": x["item"]} for x in pic["listen_today"]],
            "silent": list(pic["silent"]), "text_hi": "नमस्ते।", "summary_en": "Good morning."}


IDS = {c["child_id"] for c in ROSTER}


def test_good_brief_passes():
    pic = pic_with_pinki()
    assert check_brief(good_brief(pic), IDS, pic) == []


def test_brief_cannot_name_a_child_the_tracker_does_not_back():
    pic = pic_with_pinki()
    b = good_brief(pic)
    b["needs_support"].append({"child_id": "c06", "skill_code": "hi.blend_no_matra"})
    assert any("does not back" in p for p in check_brief(b, IDS, pic))


def test_brief_cannot_change_the_listening_list_or_ledger():
    pic = pic_with_pinki()
    b = good_brief(pic)
    b["listen_today"] = b["listen_today"][::-1]
    b["silent"] = b["silent"][1:]
    probs = check_brief(b, IDS, pic)
    assert any("listen_today" in p for p in probs) and any("Silence Ledger" in p for p in probs)


def test_brief_group_must_match_the_activity_skill():
    pic = pic_with_pinki()
    b = good_brief(pic)
    b["today"][0]["activity_id"] = "act-number-cards"
    assert any("do not need support" in p for p in check_brief(b, IDS, pic))


def test_brief_banned_words_rejected():
    pic = pic_with_pinki()
    b = good_brief(pic)
    b["text_hi"] = "पिंकी पढ़ने में कमज़ोर है।"
    assert any("banned" in p for p in check_brief(b, IDS, pic))


def test_class_remark_drives_reteach_or_move_on():
    recs = [rec(None, DAYS[-1], skill="hi.matras", outcome="incorrect", status="class", kind="class", conf=None, share="most")]
    view = planner.picture(ROSTER, LESSON, recs, TODAY)["class_view"]
    assert view and view[0]["skill_code"] == "hi.matras" and view[0]["decision"] == "reteach"
    recs.append(rec(None, DAYS[-1], skill="hi.sentence", outcome="correct", status="class", kind="class", conf=None, share="some"))
    view = planner.picture(ROSTER, LESSON, recs, TODAY)["class_view"]
    assert "hi.sentence" not in {v["skill_code"] for v in view}  # "some" managed is not enough to move on


def test_brief_class_plan_must_be_codes_decision():
    recs = [rec(None, DAYS[-1], skill="hi.matras", outcome="incorrect", status="class", kind="class", conf=None, share="most")]
    pic = planner.picture(ROSTER, LESSON, recs, TODAY)
    b = good_brief(pic) | {"needs_support": [], "stuck_where": [], "today": []}
    b["class_plan"] = [{"skill_code": "hi.matras", "decision": "reteach", "activity_id": "act-matra-ladder"}]
    assert check_brief(b, IDS, pic) == []
    b["class_plan"] = [{"skill_code": "hi.matras", "decision": "move_on", "activity_id": None}]
    assert any("not a decision code made" in p for p in check_brief(b, IDS, pic))


def test_baseline_seeds_the_ladder_and_fades():
    roster = [dict(ROSTER[3], baseline={"hindi": 1, "day": DAYS[-1].isoformat()})] + ROSTER[4:6]
    pic = planner.picture(roster, LESSON, [], TODAY)
    assert pic["levels"]["c04"]["hindi"]["moments"] == 2
    # one note on another day makes the level decided: baseline (2) + 1 observation over 2 days
    recs = [rec("c04", TODAY, skill="hi.blend_no_matra", outcome="incorrect", error_type="segments_without_blending")]
    pic = planner.picture(roster, LESSON, recs, TODAY)
    assert pic["levels"]["c04"]["hindi"]["level"] == 1
    assert ("c04", "hi.blend_no_matra") in {(x["child_id"], x["skill_code"]) for x in pic["needs_support"]}


def test_progress_over_time():
    from datetime import timedelta
    ch = ROSTER[3]
    early = [rec("c04", TODAY - timedelta(days=d), skill="hi.blend_no_matra", outcome="incorrect", error_type="segments_without_blending") for d in (36, 35, 34)]
    late = [rec("c04", TODAY - timedelta(days=d), skill="hi.sentence", outcome="correct") for d in (6, 5, 4, 3, 2)]
    prog = planner.progress(early + late, TODAY, ch)
    levels = [p["hindi"] for p in prog if p["hindi"] is not None]
    assert levels and levels[0] < levels[-1]  # moved up the ladder


def test_next_step_above_this_weeks_lesson_is_not_needs_support():
    # Baseline at "words with vowel signs" (3): next rung is joined letters (4), above this week's focus (max 3).
    roster = [dict(ROSTER[5], baseline={"hindi": 3, "day": DAYS[-2].isoformat()})]
    recs = [rec("c06", DAYS[-1], skill="hi.words_with_matras", outcome="correct"),
            rec("c06", TODAY, skill="hi.words_with_matras", outcome="correct")]
    pic = planner.picture(roster, LESSON, recs, TODAY)
    assert pic["levels"]["c06"]["hindi"]["level"] is not None
    assert pic["needs_support"] == []


def test_class_view_is_capped_and_teacher_remarks_first():
    recs = [rec(None, DAYS[-1], skill=s, outcome="incorrect", status="class", kind="class", conf=None, share="most")
            for s in ("hi.matras", "hi.blend_no_matra", "hi.words_with_matras")]
    view = planner.picture(ROSTER, LESSON, recs, TODAY)["class_view"]
    assert len([v for v in view if v["decision"] == "reteach"]) == planner.MAX_RETEACH
