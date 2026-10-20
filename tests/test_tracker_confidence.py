from datetime import date, timedelta

from server.pipeline.confidence import answer_match, confidence, passes_gate
from server.pipeline.tracker import Evidence, plan_call_ons, silence_ledger, track

D = date(2026, 10, 20)


def test_clear_correct_answer_with_tap_passes_gate():
    c = confidence("tap_confirm", "correct", answer_match("पेड़", "पेड़"), "praise", False)
    assert passes_gate(c)


def test_teacher_praising_a_wrong_answer_does_not_pass_as_correct():
    c = confidence("name_call", "correct", answer_match("बादर", "बादल"), "praise", True)
    assert not passes_gate(c)


def test_echo_of_teacher_is_weaker_than_independent_answer():
    a = confidence("tap_confirm", "correct", 1.0, "praise", False)
    b = confidence("tap_confirm", "correct", 1.0, "praise", True)
    assert b < a


def test_no_attribution_never_passes():
    assert confidence("none", "correct", 1.0, "praise", False) == 0.0


def test_naming_rule_needs_three_moments_over_two_days():
    ev = [Evidence("c1", "blend", "incorrect", 0.9, D)] * 3
    assert track(ev, D)[("c1", "blend")].status == "not enough evidence"
    ev = ev + [Evidence("c1", "blend", "incorrect", 0.9, D + timedelta(days=1))]
    assert track(ev, D + timedelta(days=1))[("c1", "blend")].status == "needs support"


def test_silence_ledger_lists_unheard_present_children():
    days = [D + timedelta(days=i) for i in range(5)]
    heard = [("c1", days[0]), ("c2", days[4])]
    absent = {d: {"c4"} for d in days}  # c4 absent all week: not listed
    assert silence_ledger(["c1", "c2", "c3", "c4"], heard, days, absent) == ["c3"]


def test_planner_skips_yesterday_and_prefers_least_heard():
    st = track([Evidence("c1", "blend", "correct", 0.9, D)] * 2, D)
    assert plan_call_ons(["c1", "c2", "c3"], st, ["blend"], called_yesterday={"c2"}, k=2) == ["c3", "c1"]


def test_brief_check_rejects_unbacked_label_and_banned_word():
    from server.pipeline.claude_brief import check_brief
    b = {"needs_support": [{"child_id": "c1", "skill_code": "hi.matras"}], "stuck_where": [], "today": [],
         "call_on": ["c2"], "silent": [], "check_tomorrow": [], "text_hi": "रवि कमज़ोर है"}
    problems = check_brief(b, {"c1", "c2"}, needs_support=set(), call_on=["c2"], silent=[], activity_ids=set())
    assert any("tracker does not back" in p for p in problems)
    assert any("banned" in p for p in problems)
