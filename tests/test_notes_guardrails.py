"""Guardrails for v1 (teacher voice notes). No model calls: Claude's output is written by hand,
including the adversarial cases code must catch on its own. Roster: the SYNTHETIC demo class."""

import json
from pathlib import Path

import pytest

from server.pipeline import names
from server.pipeline.asr import sentences
from server.pipeline.confidence import GATE, note_confidence, note_signals
from server.pipeline.guardrails import check_mentions, erased_misreading, has_banned_words, settle_attribution

ROOT = Path(__file__).resolve().parents[1]
DEMO = json.loads((ROOT / "samples/synthetic/demo_class.json").read_text())
ROSTER, LESSON = DEMO["roster"], DEMO["lesson"]


def mention(**kw):
    base = {"mention_id": "m1", "sent_ids": ["s1"], "name_said": "", "child_id": None, "kind": "observation",
            "skill_code": "hi.blend_no_matra", "item": "", "outcome": "incorrect",
            "error_type": "segments_without_blending", "when": "today", "home_language": "none",
            "teacher_quote": "", "rationale": "read it without blending"}
    return base | kw


def run(note: str, *ms):
    return check_mentions(list(ms), sentences(note), ROSTER, LESSON)


# ---- names -------------------------------------------------------------------

@pytest.mark.parametrize("said,child", [
    ("पिंकी", "c04"), ("Pinki", "c04"), ("फातिमा", "c11"), ("फ़ातिमा", "c11"), ("सुरेस", "c07"),
    ("सोनु", "c08"), ("गुड्डू", "c05"), ("Guddu", "c05"), ("सिमरन", "c02"), ("इमरान", "c25"),
    ("रानी", "c26"), ("रीना", "c10"),
])
def test_names_resolve_across_spellings(said, child):
    assert names.resolve(said, ROSTER) == {"status": "unique", "child_id": child, "candidates": [child]}


def test_similar_names_stay_apart():
    # simaran vs imaran are 92% alike as strings; a close match must start with the same sound.
    assert names.resolve("इमरान", ROSTER)["child_id"] == "c25"
    assert names.resolve("सिमरन", ROSTER)["child_id"] == "c02"


def test_shared_name_needs_roll_number():
    assert names.resolve("प्रिया", ROSTER)["status"] == "ambiguous"
    assert names.resolve("प्रिया, बारह नंबर वाली", ROSTER)["child_id"] == "c12"
    assert names.resolve("प्रिया 27", ROSTER)["child_id"] == "c27"
    assert names.resolve("प्रिया सत्ताईस नंबर", ROSTER)["child_id"] == "c27"
    assert names.resolve("प्रिया २७", ROSTER)["child_id"] == "c27"


def test_unknown_and_no_name():
    assert names.resolve("राजू", ROSTER)["status"] == "unknown"
    assert names.resolve("", ROSTER)["status"] == "no_name"


def test_hindi_number_words():
    assert names.numbers_in("सैंतालीस को चौहत्तर") == {47, 74}
    assert names.numbers_in("संतालीस") == {47}
    assert names.numbers_in("नब्बे और सौ") == {90, 100}


# ---- check_mentions ----------------------------------------------------------------

def test_specific_observation_passes_the_gate():
    note = "आज पिंकी ने कमल को क म ल पढ़ा, जोड़ नहीं पाई।"
    recs, qs, probs = run(note, mention(name_said="पिंकी", child_id="c04", item="कमल",
                                        teacher_quote="पिंकी ने कमल को क म ल पढ़ा"))
    r = recs[0]
    assert r["child_id"] == "c04" and r["attribution"] == "unique"
    assert r["confidence"] >= GATE and r["status"] == "evidence" and not qs and not probs


def test_citing_a_sentence_that_does_not_exist_is_dropped():
    recs, _, probs = run("पिंकी ने कमल पढ़ा।", mention(name_said="पिंकी", child_id="c04", sent_ids=["s9"]))
    assert recs == [] and probs[0][1] == "dropped"


def test_name_not_in_her_words_is_dropped():
    recs, _, probs = run("पिंकी ने कमल पढ़ा।", mention(name_said="अमन", child_id="c06"))
    assert recs == [] and "name_said" in probs[0][2]


def test_invented_quote_is_removed():
    recs, _, probs = run("पिंकी ने कमल पढ़ा।", mention(name_said="पिंकी", child_id="c04",
                                                    teacher_quote="पिंकी ने बहुत अच्छा पढ़ा"))
    assert recs[0]["teacher_quote"] == "" and probs[0][1] == "quote removed"


def test_invented_item_is_removed_and_confidence_drops():
    recs, _, probs = run("पिंकी ने आज जोड़कर नहीं पढ़ा।", mention(name_said="पिंकी", child_id="c04", item="कमल"))
    assert recs[0]["item"] == "" and probs[0][1] == "item removed"
    assert recs[0]["confidence"] < 0.95


def test_claude_picking_a_different_child_is_overruled():
    recs, qs, probs = run("पिंकी ने कमल को क म ल पढ़ा।", mention(name_said="पिंकी", child_id="c06", item="कमल"))
    assert recs[0]["child_id"] is None and recs[0]["status"] == "unattributed"
    assert qs and qs[0]["candidates"] == ["c04"] and probs[0][1] == "unattributed"


def test_two_priyas_without_roll_number_becomes_a_question():
    recs, qs, _ = run("प्रिया ने मछली को मछल पढ़ा।",
                      mention(name_said="प्रिया", child_id="c12", skill_code="hi.words_with_matras", item="मछली",
                              error_type="matra_omitted"))
    assert recs[0]["child_id"] is None
    assert qs == [{"mention_id": "m1", "name_said": "प्रिया", "type": "which_child", "candidates": ["c12", "c27"]}]


def test_roll_number_elsewhere_in_the_sentence_settles_it():
    recs, qs, _ = run("प्रिया ने पूरा वाक्य पढ़ा, सत्ताईस नंबर वाली।",
                      mention(name_said="प्रिया", child_id="c27", skill_code="hi.sentence", outcome="correct",
                              error_type="none"))
    assert recs[0]["child_id"] == "c27" and recs[0]["attribution"] == "roll_number" and not qs


def test_unknown_child_becomes_a_who_question():
    recs, qs, _ = run("राजू ने नाव सही पढ़ा।", mention(name_said="राजू", child_id=None, item="नाव", outcome="correct",
                                                    error_type="none", skill_code="hi.words_with_matras"))
    assert recs[0]["status"] == "unattributed" and qs[0]["type"] == "who_is_this"


def test_no_name_observation_asks_who():
    recs, qs, _ = run("एक बच्चा नाव नहीं पढ़ पाया।", mention(name_said="", item="नाव", skill_code="hi.words_with_matras"))
    assert recs[0]["status"] == "unattributed" and qs[0]["type"] == "who_is_this"


def test_opinion_never_becomes_evidence():
    recs, _, _ = run("रवि अच्छा बच्चा है।", mention(name_said="रवि", child_id="c03", kind="opinion", skill_code=None,
                                                 outcome="unclear", error_type="not_stated", when="general"))
    assert recs[0]["status"] == "check_tomorrow" and recs[0]["confidence"] < GATE


def test_opinion_with_an_item_still_is_not_evidence():
    # Even if Claude mislabels the fields, kind=opinion can never pass.
    recs, _, _ = run("रवि ने कमल सही पढ़ा, होशियार है।",
                     mention(name_said="रवि", child_id="c03", kind="opinion", item="कमल", outcome="correct",
                             error_type="none"))
    assert recs[0]["status"] == "check_tomorrow"


def test_label_in_quote_is_masked():
    recs, _, probs = run("सोनू तो कमज़ोर है, उसने घर को गर पढ़ा।",
                         mention(name_said="सोनू", child_id="c08", item="घर", error_type="letter_confusion",
                                 teacher_quote="सोनू तो कमज़ोर है, उसने घर को गर पढ़ा"))
    assert not has_banned_words(recs[0]["teacher_quote"]) and "•••" in recs[0]["teacher_quote"]
    assert any(p[1] == "label masked" for p in probs)
    assert recs[0]["status"] == "evidence"  # the observation itself is still evidence


def test_label_in_rationale_is_removed():
    recs, _, probs = run("सोनू ने घर को गर पढ़ा।", mention(name_said="सोनू", child_id="c08", item="घर",
                                                       rationale="weak reader, read घर as गर"))
    assert recs[0]["rationale"] == "" and any(p[1] == "rationale removed" for p in probs)


def test_speech_to_text_erasing_the_misreading_cannot_show_correct():
    # The teacher said "किताब को कताब"; speech-to-text returned "किताब को किताब".
    recs, _, probs = run("प्रिया, बारह नंबर, ने किताब को किताब पढ़ा।",
                         mention(name_said="प्रिया, बारह नंबर", child_id="c12", skill_code="hi.words_with_matras",
                                 item="किताब", outcome="correct", error_type="none"))
    assert recs[0]["outcome"] == "unclear" and recs[0]["status"] == "check_tomorrow"
    assert probs[0][1] == "outcome set to unclear"


def test_echo_with_explicit_praise_is_kept():
    recs, _, _ = run("अमन ने पानी को पानी पढ़ा, सही।", mention(name_said="अमन", child_id="c06", item="पानी",
                                                           outcome="correct", error_type="none",
                                                           skill_code="hi.words_with_matras"))
    assert recs[0]["outcome"] == "correct" and recs[0]["status"] == "evidence"


def test_erased_misreading_pattern():
    assert erased_misreading("गीता ने sun को sun पढ़ा")
    assert erased_misreading("सोनू ने पानी को पनी पढ़ा") is None


def test_number_item_said_as_a_word_counts_as_in_her_words():
    recs, _, probs = run("गोलू ने बत्तीस को तेईस पढ़ा।",
                         mention(name_said="गोलू", child_id="c28", skill_code="math.number_recognition", item="32",
                                 error_type="number_reversal"))
    assert recs[0]["item"] == "32" and not probs and recs[0]["signals"]["specificity"] == 1.0


def test_absent_is_recorded_without_confidence():
    recs, _, _ = run("सुरेश आज नहीं आया।", mention(name_said="सुरेश", child_id="c07", kind="absent", skill_code=None,
                                                 outcome="unclear", error_type="not_stated"))
    assert recs[0]["status"] == "absent" and recs[0]["confidence"] is None


def test_teacher_tap_rescores_in_code():
    recs, qs, _ = run("प्रिया ने मछली को मछल पढ़ा।",
                      mention(name_said="प्रिया", child_id=None, skill_code="hi.words_with_matras", item="मछली",
                              error_type="matra_omitted"))
    r = settle_attribution(recs[0], "c27")
    assert r["child_id"] == "c27" and r["attribution"] == "teacher_confirmed" and r["status"] == "evidence"


# ---- confidence --------------------------------------------------------------------

def test_vague_general_statement_stays_below_gate():
    m = mention(item="", outcome="incorrect", error_type="not_stated", when="general")
    assert note_confidence("unique", note_signals(m, False, False)) < GATE


def test_confidence_is_zero_without_a_child():
    m = mention(item="कमल")
    assert note_confidence("none", note_signals(m, True, True)) == 0.0
